# RepoSquad

AI coding agents working on GitHub repositories.

## Project layout

- `app/`: native Android Compose control panel (currently UI prototype)
- `backend/`: FastAPI service and Gemini coding workers
- `.github/workflows/android-build.yml`: builds the debug APK

## Backend worker (Stage 2)

The API now persists jobs and logs in SQLite, resumes jobs marked running after a process restart, runs 1–5 Gemini workers, creates a separate branch per worker, and supports repository file listing, reading, writing/committing, status, logs, and stop requests.

Each worker can take up to 80 model steps before its safety cap. Workers finish when Gemini reports the task complete; they are not an endless polling loop. Each agent branch is separate and is not automatically merged or turned into a pull request yet. The Android UI is not connected to this API in this stage.

### Required server secrets

Set these in the hosting provider's environment settings:

- `GEMINI_API_KEY`: Gemini API key
- `GITHUB_TOKEN`: GitHub token with access to the target repository and Contents read/write permission

Optional settings: `GEMINI_MODEL` (default `gemini-2.5-flash`) and `REPOSQUAD_DB` (SQLite file path). Use a host with persistent disk; ephemeral storage will lose the SQLite database on redeploy. Do not commit secrets or place them in the Android app.

### Run locally

```bash
cd backend
python -m venv .venv
# activate the virtual environment
pip install -r requirements.txt
export GEMINI_API_KEY=your_key
export GITHUB_TOKEN=your_token
uvicorn main:app --host 0.0.0.0 --port 8000
```

Endpoints: `GET /health`, `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/stop`, and `GET /jobs/{id}/logs`.

## Android build

Requires JDK 17 and Gradle 8.11.1:

```bash
gradle assembleDebug
```

GitHub Actions builds the debug APK on pushes to `main`, pull requests, and manual workflow dispatch.

## License

MIT
