#!/usr/bin/env bash
# Start local dev servers (backend + frontend).

set -e
cd "$(dirname "$0")/.."

# Start backend
if [ -f "venv/bin/uvicorn" ]; then
  UVICORN="venv/bin/uvicorn"
else
  UVICORN="uvicorn"
fi
$UVICORN server.main:app --reload &
BACKEND_PID=$!

# Start frontend
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Clean up on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop"
wait
