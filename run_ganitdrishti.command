#!/bin/zsh

cd "$(dirname "$0")/braille_math_assistant" || exit 1
PORT="${1:-8000}"

python3 webapp.py --port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT INT TERM

open "http://localhost:${PORT}"
wait "$SERVER_PID"
