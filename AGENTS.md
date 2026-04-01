# Cycling Coaching Platform

## Project Overview
Scalable cycling coaching platform designed for multi-athlete support. Web app that ingests ride data, computes training metrics, and provides AI coaching insights at scale.

## Development Safety & Mandates

- **DATABASE PROTECTION:** NEVER write sample, test, or dummy data to the production database.
- **LOCAL DEVELOPMENT:** Always use the local Podman-managed PostgreSQL container (`podman run -d --name coach-db -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:16-alpine`) for development and testing.
- **ENVIRONMENT VERIFICATION:** Before running any script or command that modifies the database, verify that `DATABASE_URL` is pointing to `localhost` or the intended local development instance.

## Tech Stack
- **Backend**: Python 3.11+ / FastAPI / PostgreSQL (psycopg2)
- **Frontend**: React + TypeScript + Vite + Tailwind CSS + Chart.js
- **AI Coaching**: Google ADK with Gemini via Vertex AI (Application Default Credentials)
- **Testing**: pytest
- **Package management**: pip + requirements.txt
- **Containers**: Podman (not Docker) — use `podman` commands

## Data Sources
- Raw data in GCS: `gs://jasondel-coach-data` (fit/, json/, planned_workouts/)
- PostgreSQL DB is always rebuildable from GCS JSON files
- Local dev uses Podman-managed Postgres (`podman run -d --name coach-db -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:16-alpine`)
- Ride JSON files have: session, sport, user_profile, record (per-second data)

## Project Structure
- `server/` — FastAPI backend
- `frontend/` — React/Vite frontend SPA
- `tests/` — pytest tests (see Testing section below)
- `data/` — Local data files (gitignored)
- `scripts/` — One-off data processing scripts
- `analysis/` — Season analysis outputs
- `plans/` — Build plans

## Commands
- `source venv/bin/activate` — activate Python venv (**always do this first**)
- `podman run -d --name coach-db -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:16-alpine` — start local Postgres
- `pip install -r requirements.txt` — install backend deps
- `cd frontend && npm install` — install frontend deps
- `python -m server.ingest` — ingest data from JSON files into Postgres
- `./scripts/dev.sh` — start both backend and frontend dev servers (generates VERSION from git tags)
- `uvicorn server.main:app --reload` — run backend dev server only
- `cd frontend && npm run dev` — run frontend dev server only (Vite)
- `cd frontend && npm run build` — production frontend build

## Testing

Tests are split into **unit** and **integration** tests. Unit tests never touch a database. Integration tests require a dedicated test database container.

```
tests/
├── conftest.py          # Shared config (disables Google auth)
├── unit/                # Fast, no database, no external services
│   └── test_*.py
└── integration/         # Requires test database container
    └── test_*.py
```

### Running Tests

Activate the venv first: `source venv/bin/activate`

- `pytest` — run **unit tests only** (safe, no database needed)
- `./scripts/run_integration_tests.sh` — run **integration tests** (starts a disposable Postgres container on port 5433, runs tests, tears it down)
- `./scripts/run_integration_tests.sh -v` — verbose integration tests (extra args are passed to pytest)
- `pytest tests/integration/ tests/unit/` — run **all tests** (requires test DB to be running)

### Test Database

Integration tests use a dedicated Postgres container (`coach-test-db`) on **port 5433**, completely isolated from the dev database on port 5432. The container uses a tmpfs mount — data is disposable.

To manage the test database manually:
- `podman run -d --name coach-test-db -p 5433:5432 -e POSTGRES_DB=coach_test -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=dev -e POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql/data docker.io/library/postgres:16-alpine` — start test DB
- `podman rm -f coach-test-db` — stop and remove test DB

### Writing Tests

- **Unit tests** (`tests/unit/`): Pure logic, mocked dependencies. No imports from `server.database`.
- **Integration tests** (`tests/integration/`): Use the shared `client` and `db_conn` fixtures from `tests/integration/conftest.py`. Do NOT call `init_db()` (handled by session fixture). Do NOT use `TRUNCATE` or destructive cleanup — the test database is disposable.

### Versioning
The `VERSION` file is **not checked into git**. It is auto-generated from git tags:
- **Production**: Cloud Build reads `$TAG_NAME` and passes it as a Docker build-arg
- **Local dev**: `./scripts/dev.sh` generates it before starting servers
- **Without the script**: backend shows "dev", frontend shows "development"

## Deployment

Production deploys to Cloud Run via Cloud Build, triggered by **tag pushes** (not branch pushes).

### Deploy workflow

```bash
# 1. Merge work to main
# 2. Tag the release
git tag -a v1.5.0 -m "Release 1.5.0"
# 3. Push main and the tag — the tag push triggers Cloud Build
git push origin main --tags
```

### What happens on deploy
- Cloud Build reads the tag name (e.g. `v1.5.0`) and writes `1.5.0` to VERSION
- Container image is tagged `cycling-coach:v1.5.0` in Artifact Registry
- Cloud Run revision is named `cycling-coach-v1-5-0`
- `/api/version` and the frontend Settings page show `1.5.0`

### Infrastructure
- **GCP project**: `jasondel-cloudrun10`
- **Region**: `us-central1`
- **Service account**: `cycling-coach-deployer@jasondel-cloudrun10.iam.gserviceaccount.com`
- **Artifact Registry**: `us-central1-docker.pkg.dev/jasondel-cloudrun10/cloud-run-source-deploy/cycling-coach`
- **Build config**: `cloudbuild.yaml` (in repo root)

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

### Intervals.icu Activity Taxonomy
The system relies on Intervals.icu for external ride ingestion. When syncing, the `sport` type dictates how the ingestion engine processes streams (e.g., stripping power data for non-cycling sports to accurately fall back to `hrTSS`).

*   **Cycling (Power Allowed):** `Ride`, `VirtualRide`, `EBikeRide`, `EMountainBikeRide`, `GravelRide`, `MountainBikeRide`, `TrackRide`, `Velomobile`, `Handcycle`
*   **Running:** `Run`, `TrailRun`, `VirtualRun`
*   **Swimming:** `Swim`, `OpenWaterSwim`
*   **Winter Sports:** `AlpineSki`, `BackcountrySki`, `NordicSki`, `RollerSki`, `Snowboard`, `Snowshoe`, `VirtualSki`
*   **Water Sports:** `Canoeing`, `Kayaking`, `Rowing`, `Sail`, `StandUpPaddling`, `Surfing`, `VirtualRow`, `WaterSport`, `Windsurf`
*   **Gym, Fitness & Other:** `Crossfit`, `Elliptical`, `HighIntensityIntervalTraining`, `Pilates`, `StairStepper`, `WeightTraining`, `Workout`, `Yoga`, `Hike`, `Walk`, `RockClimbing`
