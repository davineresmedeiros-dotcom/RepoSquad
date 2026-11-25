# RepoSquad

AI coding agents working on GitHub repositories, controlled from an Android app.

## Project layout

- `app/`: Android Compose control panel
- `backend/`: FastAPI service and Gemini coding agents
- `.github/workflows/android-build.yml`: backend syntax check and Android debug APK build

## What it does

1. The Android app sends a coding task to the hosted backend.
2. The backend starts 1–5 Gemini agents, each on a separate branch.
3. Agents inspect, create, and edit repository files and commit their changes.
4. When an agent finishes, it opens a pull request. If it reaches the 80-step cap, it opens a draft PR.
5. RepoSquad does **not** merge pull requests automatically. Review and test changes before merging.

The agents work on the server; the Android app is the remote control. Closing the app does not stop a backend job.

## Stage 6: reconnect after closing the app

The Android app now remembers the backend URL, repository, task, agent count, and last job ID on the device. After reopening the app, enter the API access token again and tap **Reconnect to last job** to check the saved job and resume log polling if it is still running.

The API token is deliberately not saved by this feature.

## Stage 7: connection test and token privacy

The app has a **Test connection** button that calls the protected `GET /auth/check` endpoint. It confirms both backend reachability and that the API bearer token is valid. The API token field is masked while typing and is not persisted.

## Backend deployment

The API requires `REPOSQUAD_ACCESS_TOKEN` for job endpoints. `GET /health` remains public. Enter the same access token in the Android app; it is sent as a Bearer token. Use a long random token and keep it private.

### Docker on a persistent VPS

1. Install Docker Engine and the Docker Compose plugin.
2. Clone this repository and enter its directory.
3. Copy `backend/.env.example` to `backend/.env`; set `GEMINI_API_KEY`, `GITHUB_TOKEN`, and `REPOSQUAD_ACCESS_TOKEN`. Set `REPOSQUAD_DB=/data/reposquad.db`.
4. Run `docker compose up -d --build`.
5. Put a reverse proxy with TLS (for example Caddy) in front of port 8000. Expose only HTTPS publicly; do not expose the backend port directly.
6. Set the app's Backend URL to the HTTPS URL and enter the same API access token.

Compose persists SQLite at `./data`. Keep the VPS running and configure backups. Docker does not provide free hosting or a domain/TLS automatically; continuous work requires a persistent server.

## Required server secrets

- `GEMINI_API_KEY`: Gemini API key
- `GITHUB_TOKEN`: GitHub token with repository Contents read/write and Pull requests read/write permissions
- `REPOSQUAD_ACCESS_TOKEN`: private API bearer token shared with the Android app

Optional settings: `GEMINI_MODEL` (default `gemini-2.5-flash`) and `REPOSQUAD_DB` (SQLite file path). Use persistent storage; ephemeral disks can lose the database on redeploy. Never commit secrets or put Gemini/GitHub keys in the APK.

## Run backend locally

```bash
cd backend
python -m venv .venv
# activate the virtual environment
pip install -r requirements.txt
export GEMINI_API_KEY=your_key
export GITHUB_TOKEN=your_token
export REPOSQUAD_ACCESS_TOKEN=your_private_token
uvicorn main:app --host 0.0.0.0 --port 8000
```

Endpoints: `GET /health`, `GET /auth/check` (requires bearer token), `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/stop`, and `GET /jobs/{id}/logs`.

## Android build

Requires JDK 17 and Gradle 8.11.1:

```bash
gradle assembleDebug
```

GitHub Actions builds the debug APK on pushes to `main`, pull requests, and manual workflow dispatch. It also checks the backend Python syntax.

## License

MIT
