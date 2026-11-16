#!/usr/bin/env sh
# Zəka — one-command demo (macOS / Linux): fresh demo data, server on http://127.0.0.1:5070, browser opens the 3-minute script.
#   ./demo.sh            # port 5070
#   PORT=8080 ./demo.sh  # another port
set -e
cd "$(dirname "$0")"
PORT="${PORT:-5070}"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then echo "Python 3.10+ tapılmadı / Python 3.10+ not found: https://www.python.org/downloads/"; exit 1; fi
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10+ lazımdır / Python 3.10+ required"; exit 1; }
URL="http://127.0.0.1:$PORT/?demo=1"
( sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1
  else echo "Brauzerdə açın / open in a browser: $URL"; fi ) &
echo "Zəka demo: $URL  (Ctrl+C — dayandır / stop)"
exec "$PY" run.py --reset --port "$PORT"
