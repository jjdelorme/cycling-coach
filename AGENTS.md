# Cycling Coaching Platform

## Project Overview
Cycling coaching platform. Currently single-athlete, but designed for multi-user support in the future. Web app that ingests ride data, computes training metrics, and provides AI coaching insights. 

## Tech Stack
- **Backend**: Python 3.11+ / FastAPI / PostgreSQL (psycopg2)
- **Frontend**: React + TypeScript + Vite + Tailwind CSS + Chart.js
- **AI Coaching**: Google ADK with Gemini via Vertex AI (Application Default Credentials)
- **Testing**: pytest
- **Package management**: pip + requirements.txt
- **Containers**: Podman (not Docker) — use `podman` and `podman-compose` commands

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
- On login, the Google ID token is exchanged for an app-issued JWT (24h expiry) via `POST /api/auth/login`
- Subsequent API calls use the app JWT (no per-request Google verification)
- Roles: `none` (no access, default for new users), `read`, `readwrite`, `admin`
- `GOOGLE_AUTH_ENABLED=false` disables auth for local dev (returns admin dev user)

### Environment Variables
| Variable | Where | Purpose |
|----------|-------|---------|
| `GOOGLE_CLIENT_ID` | `.env` (local), Secret Manager (prod) | Backend token verification |
| `VITE_GOOGLE_CLIENT_ID` | `.env` (local), GitHub Actions secret (CI) | Frontend build-time injection |
| `GOOGLE_AUTH_ENABLED` | `.env` (local), Cloud Run env var (prod) | Set `false` to disable auth |
| `CORS_ALLOWED_ORIGIN` | Cloud Run env var (prod) | Production frontend URL for CORS |
| `JWT_SECRET` | `.env` (local), Secret Manager (prod) | Signs app session JWTs. **Required** when auth enabled. Must be stable across restarts and replicas. |
| `JWT_EXPIRY_HOURS` | `.env` (local), Cloud Run env var (prod) | Session duration in hours (default: 24) |

- The Client ID is not a secret — it's public in the JS bundle. Stored in GitHub Secrets for convenience.
- `VITE_*` vars are inlined by Vite at build time, not read at runtime.
- Vite's `envDir` is set to `..` (repo root) so both backend and frontend read from the same `.env`.
- `.env` is gitignored and contains `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `VITE_GOOGLE_CLIENT_ID`, `JWT_SECRET`.
- Tests set `GOOGLE_AUTH_ENABLED=false` in `conftest.py` to bypass auth.

### Setting up JWT_SECRET in Secret Manager

```bash
# Generate a cryptographically secure secret
JWT_VALUE=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Create the secret in Secret Manager
gcloud secrets create JWT_SECRET --project=jasondel-cloudrun10

# Add the secret value
echo -n "$JWT_VALUE" | gcloud secrets versions add JWT_SECRET --data-file=- --project=jasondel-cloudrun10

# Grant the Cloud Run service account access
gcloud secrets add-iam-policy-binding JWT_SECRET \
  --member="serviceAccount:cycling-coach-deployer@jasondel-cloudrun10.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=jasondel-cloudrun10

# Also grant the Cloud Run runtime service account (if different from deployer)
gcloud secrets add-iam-policy-binding JWT_SECRET \
  --member="serviceAccount:$(gcloud iam service-accounts list --project=jasondel-cloudrun10 --filter='email:compute@developer' --format='value(email)')" \
  --role="roles/secretmanager.secretAccessor" \
  --project=jasondel-cloudrun10

# For local dev, add to .env
echo "JWT_SECRET=$JWT_VALUE" >> .env
```

## Glossary

| Term | Full Name | Description |
|------|-----------|-------------|
| **PMC** | Performance Management Chart | Plot of CTL, ATL, and TSB over time; the core training analytics model |
| **CTL** | Chronic Training Load | Rolling ~42-day weighted average of daily TSS; represents "fitness" |
| **ATL** | Acute Training Load | Rolling ~7-day weighted average of daily TSS; represents "fatigue" |
| **TSB** | Training Stress Balance | CTL minus ATL; represents "form" (positive = fresh, negative = fatigued) |
| **TSS** | Training Stress Score | Normalized measure of training load for a single ride, relative to FTP |
| **FTP** | Functional Threshold Power | Maximum sustainable power for ~1 hour (watts); primary fitness benchmark |
| **NP** | Normalized Power | Weighted average power that accounts for variability in effort |
| **IF** | Intensity Factor | Ratio of NP to FTP; 1.0 = threshold effort |
| **EF** | Efficiency Factor | NP divided by average HR; rising EF = improving aerobic fitness |
| **W/kg** | Watts per Kilogram | Power-to-weight ratio; critical metric for climbing performance |
| **FIT** | Flexible and Interoperable Data Transfer | Garmin's binary file format for recording ride data |
| **ZWO** | Zwift Workout | XML file format defining structured workout intervals |
| **Z0-Z5** | Power Zones 0-5 | Training intensity zones based on percentage of FTP (Z0=recovery through Z5=VO2max+) |
| **ADC** | Application Default Credentials | GCP authentication method; no API keys needed |
