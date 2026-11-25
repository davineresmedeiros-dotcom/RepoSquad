#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python >/dev/null 2>&1; then
  echo "Python not found. In Termux run: pkg install python"
  exit 1
fi

if command -v pkg >/dev/null 2>&1; then
  pkg install -y python-cryptography curl
fi

if [ -d .venv ] && ! grep -q '^include-system-site-packages = true$' .venv/pyvenv.cfg 2>/dev/null; then
  echo "Recreating the old RepoSquad virtual environment for Termux compatibility..."
  rm -rf .venv
fi
if [ ! -d .venv ]; then
  python -m venv --system-site-packages .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip

# Install the exact Android wheel directly. The PEP 503 extra-index route can
# still fall back to the PyPI source archive and invoke maturin on Termux.
PY_TAG=$(python -c 'import sys; print("cp%d%d" % sys.version_info[:2])')
case "$(uname -m)" in
  aarch64) ABI_TAG="arm64_v8a" ;;
  arm|armv7l|armv8l) ABI_TAG="armeabi_v7a" ;;
  x86_64) ABI_TAG="x86_64" ;;
  i686|i386) ABI_TAG="x86" ;;
  *) echo "Unsupported Termux architecture: $(uname -m)"; exit 1 ;;
esac

RELEASE_JSON=$(curl -fsSL https://api.github.com/repos/Eutalix/android-pydantic-core/releases/latest)
WHEEL_URL=$(printf '%s' "$RELEASE_JSON" | python -c '
import json, sys
tag = sys.argv[1]
abi = sys.argv[2]
data = json.load(sys.stdin)
suffix = f"-{tag}-{tag}-android_24_{abi}.whl"
for asset in data.get("assets", []):
    if asset.get("name", "").startswith("pydantic_core-") and asset["name"].endswith(suffix):
        print(asset["browser_download_url"])
        break
' "$PY_TAG" "$ABI_TAG")

if [ -z "$WHEEL_URL" ]; then
  echo "No matching pydantic-core Android wheel found for $PY_TAG / $ABI_TAG."
  echo "Update Termux packages with: pkg upgrade"
  exit 1
fi

WHEEL_FILE="${WHEEL_URL##*/}"
echo "Installing Android wheel: $WHEEL_FILE"
curl -fL "$WHEEL_URL" -o "$WHEEL_FILE"
python -m pip install --no-deps "./$WHEEL_FILE"
rm -f "$WHEEL_FILE"
python -c 'import pydantic_core; print("pydantic-core:", pydantic_core.__version__)'

printf 'pydantic==2.14.0\\n' > termux-constraints.txt
python -m pip install -c termux-constraints.txt -r requirements.txt

read -r -s -p "OpenRouter API key: " OPENROUTER_API_KEY; echo
read -r -s -p "GitHub token (repo contents + pull requests): " GITHUB_TOKEN; echo
read -r -s -p "RepoSquad access token (make a private random token): " REPOSQUAD_ACCESS_TOKEN; echo
export OPENROUTER_API_KEY GITHUB_TOKEN REPOSQUAD_ACCESS_TOKEN
export OPENROUTER_MODEL="${OPENROUTER_MODEL:-openrouter/free}"
export REPOSQUAD_DB="$PWD/reposquad.db"

printf '\\nRepoSquad local backend starting at http://127.0.0.1:8000\\n'
printf 'Keep this Termux session running. Ctrl+C stops the backend.\\n\\n'
exec uvicorn main:app --host 127.0.0.1 --port 8000
