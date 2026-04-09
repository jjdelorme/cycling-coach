#!/usr/bin/env bash
# Run the cycling-coach E2E test suite.
#
# Usage:
#   ./scripts/run_e2e_tests.sh              # all tests
#   ./scripts/run_e2e_tests.sh 02-dashboard # single file
#   ./scripts/run_e2e_tests.sh --headed     # show browser
#
# Assumes:
#   - venv activated (or uses system uvicorn)
#   - frontend already built (frontend/dist/ exists)
#   - Neon DB credentials in .env

set -e
cd "$(dirname "$0")/.."

PORT=8080
BASE_URL="http://localhost:${PORT}"

# ── 1. Build frontend if dist is missing ────────────────────────────────────
if [ ! -d "frontend/dist" ]; then
  echo "→ Building frontend..."
  (cd frontend && npm run build)
fi

# ── 2. Start backend if not already running ─────────────────────────────────
if ! curl -sf "${BASE_URL}/api/health" > /dev/null 2>&1; then
  echo "→ Starting backend on port ${PORT}..."
  source venv/bin/activate 2>/dev/null || true
  uvicorn server.main:app --host 0.0.0.0 --port "${PORT}" > /tmp/e2e-server.log 2>&1 &
  SERVER_PID=$!
  echo "  PID: ${SERVER_PID}"

  # Wait up to 15s for the server to be ready
  for i in $(seq 1 15); do
    sleep 1
    if curl -sf "${BASE_URL}/api/health" > /dev/null 2>&1; then
      echo "  Server ready."
      break
    fi
    if [ "$i" -eq 15 ]; then
      echo "ERROR: Server failed to start. Check /tmp/e2e-server.log"
      exit 1
    fi
  done

  trap "kill ${SERVER_PID} 2>/dev/null" EXIT
fi

# ── 3. Run tests ─────────────────────────────────────────────────────────────
echo "→ Running E2E tests against ${BASE_URL}"
export BASE_URL

cd tests/e2e
npx playwright test --config playwright.config.ts "$@"
