#!/usr/bin/env bash
# Build the frontend and serve it via the FastAPI backend on port 8000.

set -e
cd "$(dirname "$0")/.."

# Build frontend into frontend/dist (where the backend expects it)
echo "Building frontend..."
cd frontend
if [ ! -d "node_modules" ] || [ ! -f "node_modules/.bin/tsc" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi
npm run build
cd ..

# Ensure Python venv exists and deps are installed
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
fi

if [ ! -f "venv/bin/uvicorn" ]; then
  echo "Installing Python dependencies..."
  venv/bin/pip install -r requirements.txt
fi

echo "Starting server on http://localhost:3000"
if [ -n "$TMUX" ]; then
  tmux set pane-border-status top
  tmux select-pane -T "Serving Cycling Coach on port 3000"
fi
venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 3000
