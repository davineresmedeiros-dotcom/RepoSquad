#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python >/dev/null 2>&1; then
  echo "Python not found. In Termux run: pkg install python"
  exit 1
fi

# Use Termux's native cryptography package instead of building Rust code with pip.
if command -v pkg >/dev/null 2>&1; then
  pkg install -y python-cryptography
else
  echo "Termux package manager not found; install python-cryptography using your system package manager."
fi

# Ensure the venv can see Termux's native Python packages.
if [ -d .venv ] && ! grep -q '^include-system-site-packages = true$' .venv/pyvenv.cfg 2>/dev/null; then
  echo "Recreating the old RepoSquad virtual environment for Termux compatibility..."
  rm -rf .venv
fi
if [ ! -d .venv ]; then
  python -m venv --system-site-packages .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip

# PyPI does not provide a standard Android/Termux pydantic-core wheel.
# Use the Android wheel index so pip does not try to compile it with maturin.
python -m pip install --extra-index-url https://eutalix.github.io/android-pydantic-core/ -r requirements.txt

read -r -s -p "Gemini API key: " GEMINI_API_KEY; echo
read -r -s -p "GitHub token (repo contents + pull requests): " GITHUB_TOKEN; echo
read -r -s -p "RepoSquad access token (make a private random token): " REPOSQUAD_ACCESS_TOKEN; echo
export GEMINI_API_KEY GITHUB_TOKEN REPOSQUAD_ACCESS_TOKEN
export REPOSQUAD_DB="$PWD/reposquad.db"

printf '\nRepoSquad local backend starting at http://127.0.0.1:8000\n'
printf 'Keep this Termux session running. Ctrl+C stops the backend.\n\n'
exec uvicorn main:app --host 127.0.0.1 --port 8000
