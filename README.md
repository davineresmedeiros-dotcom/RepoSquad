# RepoSquad

AI agents working together on your GitHub repository.

RepoSquad is a native Android app (Kotlin + Jetpack Compose) planned to let users
select 1–5 Gemini coding agents and assign work to a GitHub repository.

## Project layout

- `app/`: native Android application
- `backend/`: Python FastAPI service starter
- `.github/workflows/android-build.yml`: builds the debug APK on GitHub Actions

## Current status

Initial scaffold. The Android screen is a UI prototype and does not yet connect
to the backend. The backend provides basic health and job-control endpoints
with in-memory job storage. The persistent 24/7 worker, Gemini execution loop,
GitHub App authorization, secure per-user credentials, and task cancellation
are not implemented yet.

## Android build

Requires JDK 17 and Gradle 8.11.1:

```bash
gradle assembleDebug
```

GitHub Actions builds the debug APK on pushes to `main`, pull requests, and
manual workflow dispatch.

## Backend local setup

```bash
cd backend
python -m venv .venv
# activate the virtual environment, then:
pip install -r requirements.txt
cp .env.example .env
# Set GEMINI_API_KEY in your environment before starting:
uvicorn main:app --host 0.0.0.0 --port 8000
```

Never put API keys or GitHub tokens in the Android app or commit them to Git.

## License

MIT
