"""RepoSquad backend starter.

This first scaffold exposes health and job-control endpoints.
Persistent worker, GitHub App authorization, and Gemini tool execution
will be implemented in the next iteration.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="RepoSquad API", version="0.1.0")


class StartJob(BaseModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    task: str = Field(min_length=1, max_length=12000)
    agents: int = Field(ge=1, le=5)


class Job(BaseModel):
    id: str
    repository: str
    task: str
    agents: int
    status: Literal["queued", "running", "stopped"] = "queued"
    created_at: str


jobs: dict[str, Job] = {}


@app.get("/health")
def health():
    return {"status": "ok", "service": "reposquad-api"}


@app.post("/jobs", response_model=Job)
def start_job(payload: StartJob):
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(status_code=503, detail="Gemini API key is not configured on the server")
    job = Job(
        id=str(uuid.uuid4()),
        repository=payload.repository,
        task=payload.task,
        agents=payload.agents,
        status="queued",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    jobs[job.id] = job
    return job


@app.post("/jobs/{job_id}/stop", response_model=Job)
def stop_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = "stopped"
    return job


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
