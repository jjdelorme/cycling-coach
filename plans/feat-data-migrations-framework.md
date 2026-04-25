# Feature Implementation Plan: Data Migrations Framework

## 🔍 Analysis & Context

*   **Objective:** Mirror the existing `schema_migrations` pattern for *data* (Python) migrations, so one-shot data backfills auto-run on deploy in numbered, idempotent, tracked-in-DB units. The geo backfill that's been pending operator action since v1.12.3 becomes the first one to run through this system.

*   **Why we need it (concrete):**
    1.  `scripts/backfill_ride_start_geo.py` has been "Pending operator action" for over a day post-v1.12.3 release. Operator follow-up steps are fragile — easy to forget, easy to skip, no audit trail.
    2.  Future Campaigns (e.g. Campaign 22 ADK serialization) may also need post-deploy data work that can't be pure SQL (calls to external APIs, complex Python logic, GCS reads).
    3.  Past pattern proven: SQL data ops live in `migrations/` and are tracked in `schema_migrations`. We have 4+ examples (`0001`, `0002`, `0004`, `0006`, `0007`). Mirroring that structure for Python is a small lift.

*   **What's already built (don't rebuild):**
    *   `server/migrate.py` — SQL migration runner + `schema_migrations` tracking table. `run_migrations(conn)` reads `migrations/*.sql`, skips already-applied, applies in order, records filename + checksum. Reference implementation.
    *   `cloudbuild.yaml:84` — runs `python -m server.migrate` via Cloud SQL Proxy before the deploy step. We mirror this for data migrations.
    *   `cloudbuild-test.yaml` — mirrors prod's migrate step. Same treatment.
    *   `scripts/backfill_ride_start_geo.py` — already idempotent (`WHERE start_lat IS NULL`), already self-protecting (refuses non-localhost without `--allow-remote`). The logic is sound; we're just promoting it to first-class status.
    *   `server/main.py` startup hook — calls `run_migrations()` for local dev. We extend this to also call `run_data_migrations()` so local dev gets the same auto-apply.

*   **Affected files (high level):**
    *   `server/data_migrate.py` — **NEW** — runner mirroring `server/migrate.py` for `data_migrations/*.py` scripts.
    *   `data_migrations/` — **NEW directory** — numbered Python files, each exporting a `run(conn) -> dict` function.
    *   `data_migrations/0001_backfill_ride_start_geo.py` — **NEW** — extracted from `scripts/backfill_ride_start_geo.py`. Becomes the first data migration.
    *   `scripts/backfill_ride_start_geo.py` — **DELETE** (logic moves to `data_migrations/`). The migration script lives in one place; no operator script to forget.
    *   `server/main.py` — extend startup hook to call `run_data_migrations()` after `run_migrations()`. Same behavior for local dev as for prod.
    *   `cloudbuild.yaml` — add a `data-migrate` step after `migrate`. Same image, same Cloud SQL Proxy.
    *   `cloudbuild-test.yaml` — mirror change.
    *   `tests/integration/test_data_migrate.py` — **NEW** — verify the runner skips already-applied scripts, records new ones, surfaces script errors.
    *   `AGENTS.md` — add a "Data Migrations" subsection mirroring "Database Migrations" so the convention is documented.

*   **Key design decisions:**

    1.  **One Python module per migration, with a `run(conn) -> dict` contract.** Mirrors `0001_*.sql` naming, returns a counts dict for logging. Importing rather than subprocessing means we share the DB connection and logger.
    2.  **Tracking table `data_migrations`** — same shape as `schema_migrations` (`filename` PK, `applied_at`, `checksum`). Separate table so the two systems don't entangle. Different filename prefix space (`data_` vs SQL filenames) means there's no possible collision.
    3.  **Run order: SQL first, then data.** Schema must exist before data ops can read/write it.
    4.  **Failure behavior: hard-fail the deploy.** Same as schema migrations — if a data migration errors, the deploy step exits non-zero and no traffic is routed to the new revision. Better to roll back than to ship with half-applied data.
    5.  **No `--dry-run` flag in the auto-apply path.** That's a developer affordance for the script itself; the runner just runs. (We can add `python -m server.data_migrate --dry-run` later if useful.)
    6.  **Idempotence is a contract, not enforced.** The runner records applied scripts so they don't run twice — but if a developer writes a non-idempotent script and a previous deploy crashed mid-run, the partial state has to be reasoned about manually. Same caveat as SQL migrations.

*   **Risks / edge cases:**
    *   **Script execution time.** The geo backfill makes external HTTP calls to intervals.icu rate-limited at ~0.5s/request. With ~few hundred rides on first run, this could take 5–10 min. Cloud Build has a 60-min build timeout per build (default), so we have plenty of headroom — but we need to make sure the step itself doesn't time out (default 10 min per step). Set an explicit `timeout: '1200s'` (20 min) on the data-migrate step.
    *   **Outbound internet from Cloud Build.** The data-migrate step runs in a Docker container on Cloud Build's network. Outbound HTTPS to intervals.icu is needed. Cloud Build runners have outbound internet by default; confirm by inspecting whether other CI steps make external calls (they don't today, so this is the first).
    *   **ICU credentials.** The script reads `intervals_icu_api_key` from the `athlete_settings` DB table (not env vars), so once the Cloud SQL Proxy is up, the script has what it needs. No new secrets required.
    *   **Local dev surprise.** Adding `run_data_migrations()` to `server/main.py` startup means every `uvicorn server.main:app --reload` triggers data migrations on the local DB. The geo backfill specifically is `WHERE start_lat IS NULL` and would call out to intervals.icu — slow on first run, no-op afterward. Mitigate by checking a `INTERVALS_ICU_DISABLED` env var (already exists per `server/services/intervals_icu.py:38`) — if disabled, the migration logs "skipped" and records itself as applied, so it doesn't repeatedly try.
    *   **Re-running a migration after the row recovers via a different path.** If a user re-syncs all rides (which would re-run the now-fixed parser and populate `start_lat`/`start_lon` correctly), and *then* the data migration runs, it'll find no rows matching `WHERE start_lat IS NULL` and be a no-op. Good — idempotent.
    *   **First-deploy bootstrap.** The `data_migrations` table itself has to exist before tracking can begin. Runner creates it with `CREATE TABLE IF NOT EXISTS` on each invocation, same as `schema_migrations`.
    *   **Don't mix SQL into the data migrations directory.** Keep the seam clean: `migrations/` = SQL, `data_migrations/` = Python. Reviewers should reject SQL files in `data_migrations/`.

## 📋 Micro-Step Checklist

- [x] **Phase 1: Build the runner**
  - [x] 1.A: Create `data_migrations/` directory with a placeholder `__init__.py` so it's a proper Python package.
  - [x] 1.B: Create `server/data_migrate.py` with `run_data_migrations(conn) -> int` mirroring `server/migrate.py`.
  - [x] 1.C: Make the module runnable: `python -m server.data_migrate` (same UX as `python -m server.migrate`).
  - [x] 1.D: Wire `run_data_migrations()` into `server/main.py`'s startup hook. (Note: `run_migrations()` is NOT currently called in startup; the plan assumed it was. Added only the data-migrate hook to keep scope minimal — operator still runs `python -m server.migrate` explicitly. Cloud Build runs both.)
  - [x] 1.E: Add unit tests for the runner contract: filename ordering, skip-already-applied, record-on-success, surface-error-on-failure (`tests/unit/test_data_migrate.py`).
  - [x] 1.F: Add an integration test (`tests/integration/test_data_migrate.py`) that creates a fake migration in a tmp dir, runs the runner, asserts the row appears in `data_migrations`.
- [x] **Phase 2: Migrate the geo backfill**
  - [x] 2.A: Create `data_migrations/0001_backfill_ride_start_geo.py` exporting `run(conn) -> dict`.
  - [x] 2.B: Inline the logic from `scripts/backfill_ride_start_geo.py`. Drop the `--allow-remote` / `--dry-run` argparse machinery — the runner doesn't need it.
  - [x] 2.C: Wrap the ICU-disabled case: honors both `INTERVALS_ICU_DISABLED` and `INTERVALS_ICU_DISABLE` (the existing `server/config.py` constant uses the latter spelling); returns `{"skipped": True, "reason": "icu_disabled"}`.
  - [x] 2.D: Delete `scripts/backfill_ride_start_geo.py` and its unit + integration tests (`tests/{unit,integration}/test_backfill_ride_start_geo.py`).
  - [x] 2.E: Update `plans/00_MASTER_ROADMAP.md` Campaign 17 archived entry: removed the "Pending operator action" note.
  - [x] 2.F: Add `tests/integration/test_data_migration_0001_geo.py` covering backfill, idempotence, and the ICU-disabled short-circuit.
- [x] **Phase 3: Wire into Cloud Build**
  - [x] 3.A: Edited `cloudbuild.yaml` — chose the merged-step refactor the plan endorses ("cleaner refactor") rather than two adjacent steps. `migrate` now runs `python -m server.migrate && python -m server.data_migrate` under one Cloud SQL Proxy. `timeout: '1200s'`. Avoids a second proxy startup race and shares the container pull.
  - [x] 3.B: Mirror in `cloudbuild-test.yaml`.
  - [x] 3.C: Cloud Run secret bindings are unchanged (ICU creds come from the DB, not Secret Manager).
- [x] **Phase 4: Documentation**
  - [x] 4.A: Added a "Data Migrations" subsection to `AGENTS.md` mirroring "Database Migrations".
  - [ ] 4.B: Update `plans/00_MASTER_ROADMAP.md` to add Campaign 23 to Archived once shipped — deferred to release-time per repo convention (Archived entries get added after merge + release tag).

## 📝 Step-by-Step Implementation Details

### Phase 1: Runner

`server/data_migrate.py` shape (model after `server/migrate.py`):

```python
"""Data migration runner for one-off Python data backfills.

Usage:
    python -m server.data_migrate

Applies all pending data_migrations/*.py modules to the database tracked in
the data_migrations table. Each module must export a `run(conn) -> dict`
function. Safe to run multiple times — already-applied modules are skipped.
"""
import hashlib, importlib.util, os, sys
from pathlib import Path
import psycopg2

DATA_MIGRATIONS_DIR = Path(__file__).parent.parent / "data_migrations"


def run_data_migrations(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                checksum TEXT,
                result JSONB
            )
        """)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM data_migrations ORDER BY filename")
        applied = {row[0] for row in cur.fetchall()}

    files = sorted(p for p in DATA_MIGRATIONS_DIR.glob("*.py") if not p.name.startswith("__"))
    pending = [f for f in files if f.name not in applied]
    if not pending:
        print("No pending data migrations.", flush=True)
        return 0

    count = 0
    for path in pending:
        src = path.read_text()
        checksum = hashlib.sha256(src.encode()).hexdigest()[:16]
        print(f"Applying {path.name} ...", flush=True)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "run"):
            raise RuntimeError(f"{path.name} does not export a `run(conn)` function")
        result = module.run(conn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO data_migrations (filename, checksum, result) VALUES (%s, %s, %s)",
                (path.name, checksum, psycopg2.extras.Json(result) if result else None),
            )
        conn.commit()
        print(f"  Done: {path.name} -> {result}", flush=True)
        count += 1
    return count


if __name__ == "__main__":
    url = os.environ.get("CYCLING_COACH_DATABASE_URL", "postgresql://postgres:dev@localhost:5432/coach")
    conn = psycopg2.connect(url)
    try:
        run_data_migrations(conn)
    finally:
        conn.close()
```

### Phase 2: Geo backfill

`data_migrations/0001_backfill_ride_start_geo.py`:

```python
"""Backfill rides.start_lat / rides.start_lon for ICU-synced rides.

Recovers GPS coordinates that were silently dropped by the pre-fix latlng
parser. Walks every ride with start_lat IS NULL whose filename looks like
icu_<icu_id>, re-fetches streams from intervals.icu, and lets
_backfill_start_location populate the row.

Idempotent: WHERE start_lat IS NULL guard; re-runs are no-ops.

Skips with INTERVALS_ICU_DISABLED env var set (local dev affordance).
"""
import logging, os, time

logger = logging.getLogger(__name__)


def run(conn) -> dict:
    if os.environ.get("INTERVALS_ICU_DISABLED"):
        return {"skipped": True, "reason": "INTERVALS_ICU_DISABLED set"}

    # ... port the body of run_backfill() from the old script, using the
    # provided `conn` instead of get_db(). Return the same counts dict.
```

The tricky parts: importing `_backfill_start_location` and the ICU client. Both currently live under `server.services.*` — the data migration imports them just like the old script did.

### Phase 3: Cloud Build

Insert this step in `cloudbuild.yaml` after the `migrate` step (and mirror in `cloudbuild-test.yaml`). It re-uses the proxy from the migrate step because the proxy socket is on `/workspace/cloudsql` which is shared between steps:

```yaml
  - name: 'gcr.io/cloud-builders/docker'
    id: 'data-migrate'
    timeout: '1200s'
    waitFor: ['migrate']
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        CLOUD_SQL_INSTANCE=$$(cat /workspace/CLOUD_SQL_INSTANCE)
        chmod +x /workspace/cloud-sql-proxy
        /workspace/cloud-sql-proxy "$$CLOUD_SQL_INSTANCE" \
          --unix-socket /workspace/cloudsql &
        PROXY_PID=$$!
        for i in $$(seq 1 30); do
          if [ -S "/workspace/cloudsql/$$CLOUD_SQL_INSTANCE/.s.PGSQL.5432" ]; then
            break
          fi
          sleep 1
        done
        docker run --rm \
          -v /workspace/cloudsql:/cloudsql \
          -e CYCLING_COACH_DATABASE_URL="$$CYCLING_COACH_DATABASE_URL" \
          ${_REGION}-docker.pkg.dev/${PROJECT_ID}/${_REPO}/${_SERVICE_NAME}:$$(cat /workspace/TAG_VERSION) \
          python -m server.data_migrate
        EXIT_CODE=$$?
        kill $$PROXY_PID 2>/dev/null
        exit $$EXIT_CODE
    secretEnv: ['CYCLING_COACH_DATABASE_URL']
```

If wiring two separate proxy instances feels brittle, the cleaner refactor is to merge `migrate` + `data-migrate` into a single step that runs both commands under one proxy. Engineer's call — both shapes work.

## 🧪 Testing

*   **Unit tests** (no DB):
    *   `server/data_migrate.py` filename ordering, skip-applied, error-surfacing, missing-`run`-fn handling.
*   **Integration tests** (against `coach_test`):
    *   Create a fake migration in a tmpdir, run, assert row appears in `data_migrations`.
    *   Re-run, assert no-op.
    *   `0001_backfill_ride_start_geo`: seed a ride with `start_lat IS NULL`, mock ICU client to return a fixed stream, run, assert row got populated.
*   **No E2E:** This is a backend infrastructure change; the existing E2E suite already covers the surface that data backfills affect.

## ⚠️ Risks & Open Questions

1.  **Cloud Build outbound internet to intervals.icu.** First step in our build to call out. Validate by checking the build log on the test deploy after this lands.
2.  **`importlib.util.spec_from_file_location` vs `importlib.import_module` from a package.** Either works; the spec-based form sidesteps the `data_migrations/__init__.py` import-side-effects question. Engineer chooses.
3.  **Should data migrations be checksummed strictly?** SQL migrations record a checksum but never verify it on re-run (it's just metadata for forensics). We'll do the same — no enforcement.
4.  **What if a migration fails mid-run?** The `INSERT INTO data_migrations` happens *after* successful `run()`, so a crashed migration is *not* recorded — re-running will re-attempt it. The migration script itself must be idempotent enough to handle "I crashed last time partway through." For the geo backfill, the `WHERE start_lat IS NULL` guard handles this naturally.
5.  **Should we move pre-existing one-off scripts (`scripts/backfill_*.py`, `scripts/sync_*.py`) into `data_migrations/`?** No — most of those are admin tools meant to be invoked manually (e.g. `scripts/sync_intervals.py`), not one-shots that should auto-run. Only scripts that satisfy "run once, ever, on this codebase" become data migrations. The geo backfill is the canonical example.

## 🚫 Out of Scope

*   **A `--dry-run` flag.** Add later if needed.
*   **Migrating other backfill scripts.** Only `backfill_ride_start_geo.py` is genuinely a one-shot. Other scripts in `scripts/` (sync, ingest, recompute) are admin tools that stay where they are.
*   **A "rollback" or "undo" mechanism.** Schema migrations don't have one either; data migrations don't get one.
*   **Per-tenant or per-user data migrations.** Single-tenant app today; the runner walks the whole DB.

## 🎯 Success Criteria

*   `python -m server.data_migrate` applies pending data migrations against the local DB and is a no-op on re-run.
*   `cloudbuild.yaml` runs `data-migrate` automatically after `migrate` on every deploy.
*   The geo backfill is no longer an "operator follow-up" — it auto-applies once on the next prod deploy and never appears in operator notes again.
*   `data_migrations` tracking table shows `0001_backfill_ride_start_geo.py` with an `applied_at` timestamp on prod after the next deploy.
*   `AGENTS.md` documents the new pattern so future contributors don't reinvent it.
*   All existing tests still pass; new tests cover the runner + geo migration.

## 🌿 Branch

`feat/data-migrations-framework` (worktree at `.claude/worktrees/data-migrations`, branched from `main` at `6c7c6fb`).

## 📦 Deliverables

1.  Implementation per the checklist.
2.  No commits — leave the worktree dirty for review.
3.  Audit report at `plans/reports/AUDIT_data-migrations-framework.md`.
