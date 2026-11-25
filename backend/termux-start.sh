#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python >/dev/null 2>&1; then
  echo "Python not found. In Termux run: pkg install python"
  exit 1
fi

if [ ! -d .venv ]; then
  python -m venv .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

read -r -s -p "Gemini API key: " GEMINI_API_KEY; echo
read -r -s -p "GitHub token (repo contents + pull requests): " GITHUB_TOKEN; echo
read -r -s -p "RepoSquad access token (make a private random token): " REPOSQUAD_ACCESS_TOKEN; echo
export GEMINI_API_KEY GITHUB_TOKEN REPOSQUAD_ACCESS_TOKEN
export REPOSQUAD_DB="$PWD/reposquad.db"

printf '\nRepoSquad local backend starting at http://127.0.0.1:8000\n'
printf 'Keep this Termux session running. Ctrl+C stops the backend.\n\n'
exec uvicorn main:app --host 127.0.0.1 --port 8000
