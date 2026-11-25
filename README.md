# RepoSquad

AI coding agents working on GitHub repositories.

## Project layout

- `app/`: native Android Compose control panel (currently UI prototype)
- `backend/`: FastAPI service and Gemini coding workers
- `.github/workflows/android-build.yml`: builds the debug APK

## Backend deployment (Stage 4)

The API requires `REPOSQUAD_ACCESS_TOKEN` for all job endpoints. `/health` remains public for health checks. Enter the same token in the Android app; it is sent as a Bearer token over HTTPS. Use a long random token and keep it private.

### Docker on a persistent VPS

1. Install Docker Engine and the Docker Compose plugin on your VPS.
2. Clone this repository and enter its directory.
3. Copy `backend/.env.example` to `backend/.env`; fill in `GEMINI_API_KEY`, `GITHUB_TOKEN`, and `REPOSQUAD_ACCESS_TOKEN` with secrets. Set `REPOSQUAD_DB=/data/reposquad.db`.
4. Run `docker compose up -d --build`.
5. Put a reverse proxy with TLS (for example Caddy) in front of port 8000; expose only HTTPS publicly. Do not expose the backend port directly to the internet.
6. Set the app's Backend URL to the HTTPS URL and its API access token to the exact same token.

Compose persists SQLite at `./data`. Keep the VPS running and configure backups. This Docker setup does not provide a free host or domain/TLS automatically; a persistent server is required for continuous work.

## Backend worker (Stage 2)

The API now persists jobs and logs in SQLite, resumes jobs marked running after a process restart, runs 1–5 Gemini workers, creates a separate branch per worker, and supports repository file listing, reading, writing/committing, status, logs, and stop requests.

Each worker can take up to 80 model steps before its safety cap. Workers finish when Gemini reports the task complete; they are not an endless polling loop. Each agent branch is separate and is not automatically merged or turned into a pull request yet. The Android UI is not connected to this API in this stage.

### Required server secrets

Set these in the hosting provider's environment settings:

- `GEMINI_API_KEY`: Gemini API key
- `GITHUB_TOKEN`: GitHub token with access to the target repository, Contents read/write permission, and Pull requests read/write permission (needed to open PRs)

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

## Stage 5: automatic pull requests\n\nWhen an agent finishes, it opens a PR from its own branch into the repository's default branch. If it reaches the 80-step cap, it opens a draft PR instead. RepoSquad never merges automatically. Give the server's GitHub token Contents and Pull requests read/write permissions.\n\n## Android build

Requires JDK 17 and Gradle 8.11.1:

```bash
gradle assembleDebug
```

GitHub Actions builds the debug APK on pushes to `main`, pull requests, and manual workflow dispatch.

## License

MIT
