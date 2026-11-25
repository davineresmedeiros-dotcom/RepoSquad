import asyncio,base64,json,os,sqlite3,uuid,secrets
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
import httpx
from fastapi import FastAPI,HTTPException,Header,Depends
from pydantic import BaseModel,Field
from google import genai
from google.genai import types

DB=Path(os.getenv("REPOSQUAD_DB",str(Path(__file__).parent/"reposquad.db")))
MODEL=os.getenv("GEMINI_MODEL","gemini-3.8-flash")
API="https://api.github.com"
app=FastAPI(title="RepoSquad API",version="0.2.0")
events={}; tasks={}
def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def conn():
 c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row
 try:
  yield c
  c.commit()
 except Exception:
  c.rollback()
  raise
 finally:
  c.close()
def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with conn() as c:
  c.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,repository TEXT,task TEXT,agents INTEGER,status TEXT,created_at TEXT,updated_at TEXT,error TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,agent INTEGER,created_at TEXT,message TEXT)")
  c.execute("CREATE INDEX IF NOT EXISTS log_job ON logs(job_id,id)")
def log(j,a,m):
 with conn() as c:
  c.execute("INSERT INTO logs(job_id,agent,created_at,message) VALUES(?,?,?,?)",(j,a,now(),str(m)[:3500]))
  c.execute("UPDATE jobs SET updated_at=? WHERE id=?",(now(),j))
def dto(r): return {k:r[k] for k in ("id","repository","task","agents","status","created_at","updated_at","error")}
class Start(BaseModel):
 repository:str=Field(pattern=r"^(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|new:[A-Za-z0-9_.-]+)$")
 task:str=Field(min_length=1,max_length=12000)
 agents:int=Field(ge=1,le=5)
class Job(BaseModel):
 id:str; repository:str; task:str; agents:int; status:str; created_at:str; updated_at:str; error:str|None=None
def verify_access(authorization: str | None = Header(default=None)):
 token=os.getenv("REPOSQUAD_ACCESS_TOKEN")
 if not token: raise HTTPException(503,"REPOSQUAD_ACCESS_TOKEN missing on server")
 supplied=(authorization or "").removeprefix("Bearer ").strip()
 if not secrets.compare_digest(supplied,token): raise HTTPException(401,"Invalid or missing API token")

def headers():
 t=os.getenv("GITHUB_TOKEN")
 if not t: raise RuntimeError("GITHUB_TOKEN missing on server")
 return {"Authorization":"Bearer "+t,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
async def gh(c,m,p,**kw):
 r=await c.request(m,API+p,headers=headers(),**kw)
 if r.status_code>=400: raise RuntimeError("GitHub "+str(r.status_code)+": "+r.text[:300])
 return r.json() if r.content else {}
async def branch(c,repo,b):
 info=await gh(c,"GET","/repos/"+repo)
 ref=await gh(c,"GET","/repos/"+repo+"/git/ref/heads/"+quote(info["default_branch"],safe=""))
 try: await gh(c,"POST","/repos/"+repo+"/git/refs",json={"ref":"refs/heads/"+b,"sha":ref["object"]["sha"]})
 except RuntimeError as e:
  if "422" not in str(e): raise
async def open_pr(c,repo,b,job_id,agent,summary,draft=False):
 info=await gh(c,"GET","/repos/"+repo)
 base=info["default_branch"]
 title=("RepoSquad agent "+str(agent)+": "+str(summary or "completed task"))[:240]
 body=("Automated contribution from RepoSquad.\n\n"
       +"Job: "+job_id+"\nAgent: "+str(agent)+"\nBranch: "+b+"\n\n"
       +"Please review the changes and run the project's tests before merging. "
       +"RepoSquad does not merge automatically.")
 try:
  d=await gh(c,"POST","/repos/"+repo+"/pulls",json={"title":title,"head":b,"base":base,"body":body,"draft":draft})
 except RuntimeError as e:
  if "422" in str(e) and "pull request" in str(e).lower():
   log(job_id,agent,"PR may already exist for branch "+b)
   return None
  raise
 url=d.get("html_url","")
 log(job_id,agent,("Draft PR created: " if draft else "PR created: ")+url)
 return url

async def action(c,repo,b,act,args):
 if act=="list_files":
  d=await gh(c,"GET","/repos/"+repo+"/git/trees/"+quote(b,safe=""),params={"recursive":"1"})
  return {"paths":[x["path"] for x in d.get("tree",[]) if x.get("type")=="blob"][:3000]}
 if act=="create_repo":
  name=str(args.get("name","")).strip()
  if not name or not __import__("re").fullmatch(r"[A-Za-z0-9_.-]{1,100}",name): raise RuntimeError("Invalid repository name")
  body={"name":name,"description":str(args.get("description","Created by RepoSquad"))[:350],"private":bool(args.get("private",True)),"auto_init":True}
  d=await gh(c,"POST","/user/repos",json=body)
  return {"created_repository":d.get("full_name"),"url":d.get("html_url"),"default_branch":d.get("default_branch")}
 if act=="create_workflow":
  name=str(args.get("name","reposquad.yml")).strip()
  if not name.endswith((".yml",".yaml")) or "/" in name or "\\" in name: raise RuntimeError("Workflow name must be a .yml or .yaml filename")
  content=args.get("content")
  if not isinstance(content,str) or len(content)>80000: raise RuntimeError("Workflow content too large")
  wp=".github/workflows/"+name
  wep="/repos/"+repo+"/contents/"+quote(wp,safe="/")
  old=None
  try: old=await gh(c,"GET",wep,params={"ref":b})
  except RuntimeError as e:
   if "404" not in str(e): raise
  body={"message":str(args.get("message","RepoSquad add workflow"))[:120],"content":base64.b64encode(content.encode()).decode(),"branch":b}
  if old: body["sha"]=old["sha"]
  d=await gh(c,"PUT",wep,json=body)
  return {"workflow":wp,"commit":d.get("commit",{}).get("sha","")}
 p=str(args.get("path","")).strip()
 if not p or p.startswith("/") or "\\" in p or "\x00" in p or ".." in Path(p).parts: raise RuntimeError("Invalid file path")
 ep="/repos/"+repo+"/contents/"+quote(p,safe="/")
 if act=="read_file":
  d=await gh(c,"GET",ep,params={"ref":b})
  return {"path":p,"content":base64.b64decode(d.get("content","").replace("\n","")).decode("utf-8",errors="replace")[:20000]}
 if act=="write_file":
  content=args.get("content")
  if not isinstance(content,str) or len(content)>80000: raise RuntimeError("File too large")
  old=None
  try: old=await gh(c,"GET",ep,params={"ref":b})
  except RuntimeError as e:
   if "404" not in str(e): raise
  body={"message":str(args.get("message","RepoSquad edit"))[:120],"content":base64.b64encode(content.encode()).decode(),"branch":b}
  if old: body["sha"]=old["sha"]
  d=await gh(c,"PUT",ep,json=body)
  return {"path":p,"commit":d.get("commit",{}).get("sha","")}
 if act=="delete_file":
  old=await gh(c,"GET",ep,params={"ref":b})
  d=await gh(c,"DELETE",ep,json={"message":str(args.get("message","RepoSquad remove file"))[:120],"sha":old["sha"],"branch":b})
  return {"path":p,"deleted":True,"commit":d.get("commit",{}).get("sha","")}
 if act=="rename_file":
  newp=str(args.get("new_path","")).strip()
  if not newp or newp.startswith("/") or "\\" in newp or "\x00" in newp or ".." in Path(newp).parts: raise RuntimeError("Invalid destination path")
  old=await gh(c,"GET",ep,params={"ref":b})
  content=base64.b64decode(old.get("content","").replace("\n","")).decode("utf-8",errors="replace")
  dest="/repos/"+repo+"/contents/"+quote(newp,safe="/")
  try:
   await gh(c,"GET",dest,params={"ref":b})
   raise RuntimeError("Destination already exists: "+newp)
  except RuntimeError as e:
   if "404" not in str(e): raise
  put=await gh(c,"PUT",dest,json={"message":str(args.get("message","RepoSquad rename file"))[:120],"content":base64.b64encode(content.encode()).decode(),"branch":b})
  delete=await gh(c,"DELETE",ep,json={"message":str(args.get("message","RepoSquad rename file"))[:120],"sha":old["sha"],"branch":b})
  return {"old_path":p,"new_path":newp,"commit":delete.get("commit",{}).get("sha") or put.get("commit",{}).get("sha","")}
 raise RuntimeError("Unknown action")
RULES="""You are an autonomous coding agent working on the user's GitHub project. Make concrete progress.
Return exactly one JSON object, no markdown. Available actions:
{"action":"list_files","args":{}}
{"action":"read_file","args":{"path":"relative/file"}}
{"action":"write_file","args":{"path":"relative/file","content":"complete file text","message":"commit message"}}
{"action":"delete_file","args":{"path":"relative/file","message":"why remove it"}}
{"action":"rename_file","args":{"path":"old/path","new_path":"new/path","message":"why rename it"}}
{"action":"create_workflow","args":{"name":"ci.yml","content":"complete GitHub Actions YAML","message":"add CI workflow"}}
{"action":"create_repo","args":{"name":"new-repo","description":"project purpose","private":true}}
{"action":"finish","args":{"summary":"completed task"}}
Inspect before editing. Use relative paths. For rename, ensure destination does not exist. Delete only files clearly required by the task, never remove unrelated data. Create a new repository only when the user explicitly requested one; default it to private. After create_repo, continue work in the newly created repository. Workflows belong in .github/workflows and require the GitHub token's workflow permission. Do not claim tests ran unless actually run. Never reveal secrets. Work only on your branch. If not finished, choose next useful action."""
async def choose(model,repo,task,b,h):
 prompt="Repository: "+repo+"\nBranch: "+b+"\nTask: "+task+"\nRecent results: "+json.dumps(h[-5:],ensure_ascii=False)+"\nChoose next action."
 r=await asyncio.to_thread(model.models.generate_content,model=MODEL,contents=prompt,config=types.GenerateContentConfig(system_instruction=RULES,temperature=0.2))
 text=(r.text or "").strip()
 try: d=json.loads(text)
 except json.JSONDecodeError:
  start=text.find("{")
  if start<0: raise RuntimeError("Gemini did not return a JSON action")
  d,_=json.JSONDecoder().raw_decode(text[start:])
 if d.get("action") not in ("list_files","read_file","write_file","delete_file","rename_file","create_workflow","create_repo","finish") or not isinstance(d.get("args",{}),dict): raise RuntimeError("Invalid Gemini action")
 return d
async def agent(j,repo,task,n,event):
 b="reposquad/"+j[:8]+"/agent-"+str(n); history=[]
 try:
  async with httpx.AsyncClient(timeout=45) as c:
   await branch(c,repo,b); log(j,n,"Started branch "+b)
   model=genai.Client(api_key=os.environ["GEMINI_API_KEY"]); changed=False
   for step in range(1,81):
    if event.is_set(): return "stopped"
    d=await choose(model,repo,task,b,history); act,args=d["action"],d.get("args",{})
    if act=="finish":
     summary=str(args.get("summary","completed task"))[:700]
     log(j,n,"Finished: "+summary)
     if changed:
      await open_pr(c,repo,b,j,n,summary,draft=False)
     else:
      log(j,n,"No file changes; skipped empty PR.")
     return "completed"
    result=await action(c,repo,b,act,args)
    if act=="create_repo":
     new_repo=result.get("created_repository")
     if not new_repo: raise RuntimeError("GitHub did not return the created repository name")
     repo=new_repo
     b="reposquad/"+j[:8]+"/agent-"+str(n)
     await branch(c,repo,b)
     log(j,n,"Created repository "+repo+" and switched work branch to "+b)
    elif act in ("write_file","delete_file","rename_file","create_workflow"):
     changed=True
    brief=json.dumps(result,ensure_ascii=False)[:3500]
    history.append({"action":act,"result":brief}); log(j,n,"Step "+str(step)+" "+act+": "+brief)
   log(j,n,"Safety cap reached: 80 model steps; opening a draft PR for review.")
   await open_pr(c,repo,b,j,n,"work in progress (step cap reached)",draft=True)
   return "draft"
 except Exception as e:
  log(j,n,"ERROR: "+str(e)[:900])
  return "failed"
async def worker(j):
 event=events.setdefault(j,asyncio.Event())
 with conn() as c:
  r=c.execute("SELECT * FROM jobs WHERE id=?",(j,)).fetchone()
  if not r or r["status"]=="stopped": return
  c.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?",(now(),j))
 log(j,0,"Running "+str(r["agents"])+" agents.")
 try:
  results=await asyncio.gather(*(agent(j,r["repository"],r["task"],n,event) for n in range(1,r["agents"]+1)))
  with conn() as c:
   s=c.execute("SELECT status FROM jobs WHERE id=?",(j,)).fetchone()
   if s and s["status"]!="stopped":
    failed=any(x=="failed" for x in results)
    status="failed" if failed else ("stopped" if event.is_set() else "completed")
    error="One or more agents failed. Check the activity logs." if failed else None
    c.execute("UPDATE jobs SET status=?,error=?,updated_at=? WHERE id=?",(status,error,now(),j))
  if not event.is_set():
   if any(x=="failed" for x in results): log(j,0,"Job finished with agent errors.")
   else: log(j,0,"All agents finished.")
 except Exception as e:
  with conn() as c: c.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?",(str(e)[:900],now(),j))
 finally: events.pop(j,None); tasks.pop(j,None)
def schedule(j): events[j]=asyncio.Event(); tasks[j]=asyncio.create_task(worker(j))
@app.on_event("startup")
async def startup():
 init()
 with conn() as c:
  c.execute("UPDATE jobs SET status='queued',updated_at=? WHERE status='running'",(now(),))
  rows=c.execute("SELECT id FROM jobs WHERE status='queued'").fetchall()
 for r in rows: schedule(r["id"])
@app.get("/health")
def health(): return {"status":"ok","service":"reposquad-api","worker":"enabled"}
@app.get("/auth/check")
def auth_check(_=Depends(verify_access)):
 return {"authorized":True,"service":"reposquad-api"}
@app.post("/jobs",response_model=Job)
async def start(p:Start,_=Depends(verify_access)):
 if not os.getenv("GEMINI_API_KEY"): raise HTTPException(503,"GEMINI_API_KEY missing on server")
 if not os.getenv("GITHUB_TOKEN"): raise HTTPException(503,"GITHUB_TOKEN missing on server")
 repo=p.repository
 if repo.startswith("new:"):
  name=repo[4:]
  if not __import__("re").fullmatch(r"[A-Za-z0-9_.-]{1,100}",name): raise HTTPException(422,"Invalid new repository name")
  try:
   async with httpx.AsyncClient(timeout=45) as client:
    created=await gh(client,"POST","/user/repos",json={"name":name,"private":True,"auto_init":True,"description":"Created by RepoSquad"})
   repo=created.get("full_name","")
   if not repo: raise RuntimeError("GitHub did not return the created repository name")
  except RuntimeError as e: raise HTTPException(400,str(e)[:300])
 j=str(uuid.uuid4()); t=now()
 with conn() as c:
  c.execute("INSERT INTO jobs(id,repository,task,agents,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(j,repo,p.task,p.agents,"queued",t,t))
  r=c.execute("SELECT * FROM jobs WHERE id=?",(j,)).fetchone()
 schedule(j); return dto(r)
@app.post("/jobs/{j}/stop",response_model=Job)
async def stop(j:str,_=Depends(verify_access)):
 with conn() as c:
  r=c.execute("SELECT * FROM jobs WHERE id=?",(j,)).fetchone()
  if not r: raise HTTPException(404,"Job not found")
  c.execute("UPDATE jobs SET status='stopped',updated_at=? WHERE id=?",(now(),j))
 if j in events: events[j].set()
 d=dto(r); d["status"]="stopped"; d["updated_at"]=now(); return d
@app.get("/jobs/{j}",response_model=Job)
def status(j:str,_=Depends(verify_access)):
 with conn() as c: r=c.execute("SELECT * FROM jobs WHERE id=?",(j,)).fetchone()
 if not r: raise HTTPException(404,"Job not found")
 return dto(r)
@app.get("/jobs/{j}/logs")
def logs(j:str,after:int=0,limit:int=100,_=Depends(verify_access)):
 with conn() as c:
  if not c.execute("SELECT 1 FROM jobs WHERE id=?",(j,)).fetchone(): raise HTTPException(404,"Job not found")
  rows=c.execute("SELECT id,agent,created_at,message FROM logs WHERE job_id=? AND id>? ORDER BY id LIMIT ?",(j,max(0,after),max(1,min(limit,400)))).fetchall()
 return {"logs":[dict(x) for x in rows]}
