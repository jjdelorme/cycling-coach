# Cycling Coaching Platform

## Project Overview
Single-athlete cycling coaching platform. Web app that ingests ride data, computes training metrics, and provides AI coaching insights. Target: Big Sky Biggie (late August 2026, ~50mi MTB, ~6000ft climbing).

## Tech Stack
- **Backend**: Python 3.11+ / FastAPI / PostgreSQL (psycopg2)
- **Frontend**: React + TypeScript + Vite + Tailwind CSS + Chart.js
- **AI Coaching**: Google ADK with Gemini via Vertex AI (Application Default Credentials)
- **Testing**: pytest
- **Package management**: pip + requirements.txt
- **Containers**: Podman (not Docker) — use `podman` and `podman-compose` commands

## Athlete Profile
- 50yo male, ~163 lbs (goal: 160 race weight), 5'10"
- FTP: peaked 287w (Oct 2025), currently ~261w
- W/kg: peaked 3.62, currently ~3.45
- 291 rides, 581 hours over the past year
- Power meter broken since ~Feb 25, 2026

## Key Coaching Principles
- 12-14h/week sweet spot (not 15-19)
- 3-week build / 1-week recovery cycles
- Structured intervals needed (not just terrain-driven intensity)
- 48-72h recovery after hard efforts
- Polarized: easy days easy, hard days hard
- Weight is a lever: every pound matters on climbs
- Graceful handling of missed days — adjust the week, protect key workouts

## Periodization (March 2026 - Race Day)
| Phase | Dates | Focus | Hours/wk | TSS Target |
|-------|-------|-------|----------|------------|
| Base Rebuild | Mar 23 - Apr 27 | Aerobic base, CTL 21→50 | 10-12h | 350-500 |
| Build 1 | Apr 28 - Jun 1 | Add threshold, CTL 50→70 | 12-14h | 500-650 |
| Build 2 | Jun 2 - Jul 6 | Add VO2max, CTL 70→85 | 13-15h | 600-750 |
| Peak | Jul 7 - Aug 10 | Race-sim, CTL 85-90 | 12-14h | 550-700 |
| Taper | Aug 11 - Race Day | Volume -40%, keep intensity | 7-9h | 300-400 |

## Data Sources
- Raw data in GCS: `gs://jasondel-coach-data` (fit/, json/, planned_workouts/)
- PostgreSQL DB is always rebuildable from GCS JSON files
- Local dev uses Podman-managed Postgres (`podman-compose up -d`)
- Ride JSON files have: session, sport, user_profile, record (per-second data)

## Project Structure
- `server/` — FastAPI backend
- `frontend/` — React/Vite frontend SPA
- `tests/` — pytest tests
- `data/` — Local data files (gitignored)
- `scripts/` — One-off data processing scripts
- `analysis/` — Season analysis outputs
- `plans/` — Build plans

## Commands
- `podman-compose up -d` — start local Postgres
- `pip install -r requirements.txt` — install backend deps
- `cd frontend && npm install` — install frontend deps
- `python -m server.ingest` — ingest data from JSON files into Postgres
- `uvicorn server.main:app --reload` — run backend dev server
- `cd frontend && npm run dev` — run frontend dev server (Vite)
- `cd frontend && npm run build` — production frontend build
- `pytest` — run all tests
- `pytest tests/test_database.py -v` — run specific test file

## Authentication

### AI / Vertex AI
Uses GCP Application Default Credentials. Run `gcloud auth application-default login` before starting.

### Google Sign-In (RBAC)
- Frontend uses `@react-oauth/google` with the Google Identity Services credential (JWT) flow
- Backend verifies Google ID tokens via `google.oauth2.id_token.verify_oauth2_token()`
- Roles: `none` (no access, default for new users), `read`, `readwrite`, `admin`
- `GOOGLE_AUTH_ENABLED=false` disables auth for local dev (returns admin dev user)

### Environment Variables
| Variable | Where | Purpose |
|----------|-------|---------|
| `GOOGLE_CLIENT_ID` | `.env` (local), Cloud Run env var (prod) | Backend token verification |
| `VITE_GOOGLE_CLIENT_ID` | `.env` (local), GitHub Actions secret (CI) | Frontend build-time injection |
| `GOOGLE_AUTH_ENABLED` | `.env` (local), Cloud Run env var (prod) | Set `false` to disable auth |
| `CORS_ALLOWED_ORIGIN` | Cloud Run env var (prod) | Production frontend URL for CORS |

- The Client ID is not a secret — it's public in the JS bundle. Stored in GitHub Secrets for convenience.
- `VITE_*` vars are inlined by Vite at build time, not read at runtime.
- Vite's `envDir` is set to `..` (repo root) so both backend and frontend read from the same `.env`.
- `.env` is gitignored and contains `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `VITE_GOOGLE_CLIENT_ID`.
- Tests set `GOOGLE_AUTH_ENABLED=false` in `conftest.py` to bypass auth.
