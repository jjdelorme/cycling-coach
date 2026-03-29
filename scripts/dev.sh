#!/usr/bin/env bash
# Start local dev servers (backend + frontend).
# Generates VERSION from git tags so /api/version and the UI show the real version.

set -e
cd "$(dirname "$0")/.."

# Generate VERSION from git tags
git describe --tags --always | sed 's/^v//' > VERSION
echo "VERSION: $(cat VERSION)"

# Start backend
uvicorn server.main:app --reload &
BACKEND_PID=$!

# Start frontend
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Clean up on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; rm -f VERSION" EXIT

echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop"
wait
