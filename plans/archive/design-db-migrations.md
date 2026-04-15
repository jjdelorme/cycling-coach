# Database Migration System — Design Overview

**Branch:** `refactor/db-migrations`  
**Status:** Decisions finalized — ready for implementation  
**Date:** 2026-04-10

---

## Problem Statement

The application currently manages all schema changes through `init_db()` in `server/database.py`. This function runs synchronously at every FastAPI startup and has accumulated significant technical debt:

### What `init_db()` Does Today

1. Executes the entire `_SCHEMA` blob (~40 DDL statements) via `split(";")` on every boot
2. Runs three hardcoded migration groups inline:
   - `planned_workouts` sync columns (`icu_event_id`, `sync_hash`, `synced_at`) — bare `ALTER TABLE` **without `IF NOT EXISTS`**, wrapped in a silent `except Exception: conn.rollback()`
   - v1.5.2 migrations — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (safer, but still replayed every boot)
   - Withings `body_measurements` table + `measured_at` column — `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
3. Seeds `workout_templates` and `macro_targets` if empty
4. Closes the connection and returns — no record of what ran

### Why This Is a Problem

| Issue | Impact |
|-------|--------|
| Bare `ALTER TABLE` without `IF NOT EXISTS` (group 1) | Throws `DuplicateColumn` on every non-first startup; swallowed silently but pollutes logs with `migration_skipped` warnings |
| No migration tracking table | No way to know which migrations have run vs. which are pending |
| Schema and migrations mixed in one 750-line file | Every schema change requires editing `database.py`; the file has 56 DDL statements and growing |
| Runs on every boot | Adds 100–300ms to Cloud Run cold start; replays idempotent DDL on every request that hits a cold instance |
| `conn.rollback()` on `autocommit=True` connection | Is a no-op — the rollback does nothing if the connection is in autocommit mode |
| No ordering guarantee between migration groups | Groups 1, 2, and 3 run unconditionally in fixed source order; there is no way to insert a migration "between" existing ones without renumbering or risking ordering bugs |
| Impossible to run migrations without starting the app | There is no standalone migration CLI; schema changes can only be applied by restarting the server |
| Seed data coupled to schema migrations | `_seed_workout_templates()` and `_seed_macro_targets()` run inside `init_db()`; changing seed data requires a full restart |

---

## Options Analysis

### Option A — Alembic (REJECTED)

Alembic is the de facto Python migration tool (SQLAlchemy ecosystem). It supports autogenerate, branches, and downgrades.

**Why rejected:**
- Requires SQLAlchemy ORM or at minimum a SQLAlchemy engine; this project uses raw `psycopg2` connections
- Adds a heavyweight dependency with its own configuration file (`alembic.ini`), `env.py`, and `versions/` directory with Python migration files
- Autogenerate is unreliable without a fully declared ORM model — would need manual migrations anyway
- High switching cost for minimal benefit vs. a simple numbered SQL approach

### Option B — Numbered SQL Files + Custom Runner (RECOMMENDED)

A `migrations/` directory of numbered `.sql` files, a lightweight `server/migrate.py` runner, and a `schema_migrations` tracking table.

```
migrations/
  0001_baseline.sql          # Full schema snapshot as of v1.6.0
  0002_v152_power_bests.sql  # avg_hr, avg_cadence, start_offset_s columns
  0003_withings.sql          # body_measurements table + measured_at
  0004_...sql                # Future migrations
server/migrate.py            # Runner: applies pending migrations, records applied
```

**How it works:**
1. On startup (or CLI invocation), `migrate.py` reads `schema_migrations` to find applied migrations
2. For each `.sql` file in `migrations/` not yet recorded, it executes the file in a transaction
3. On success, inserts a row into `schema_migrations` with filename and timestamp
4. If a migration fails, the transaction rolls back and the error surfaces immediately (no silent swallowing)

**Pros:**
- Zero new dependencies
- Pure SQL — reviewable, diffable, copy-pasteable into psql
- Migrations run exactly once — no replaying idempotent DDL on every boot
- `schema_migrations` table provides an audit trail
- `migrate.py` can be invoked as a standalone CLI: `python -m server.migrate`
- Cloud Build can run migrations as a pre-deploy step before routing traffic to the new revision

**Cons:**
- No autogenerate — schema changes must be written manually
- No downgrade support — rollback requires writing a reversal migration
- Must maintain a coherent baseline snapshot

### Option C — Fix in Place (NOT RECOMMENDED)

Add `IF NOT EXISTS` to the bare `ALTER TABLE` in group 1, accept the current architecture.

**Why not recommended:**
- Solves only the `DuplicateColumn` noise; does not address lack of tracking, cold-start overhead, or the unmaintainable monolithic file
- The problem will recur — every new migration added to `init_db()` continues to replay on every boot
- This is a deferral, not a solution

### Option D — yoyo-migrations

A lightweight migration library that uses numbered SQL files with a tracking table.

**Why deferred:**
- Adds an external dependency for functionality achievable with ~100 lines of Python
- The project's existing toolchain (pip + requirements.txt) already works; adding a library requires vetting and pinning
- Option B achieves the same result with less surface area

---

## Recommendation: Option B

Implement numbered SQL migrations + a custom runner. This is the lowest-risk, lowest-dependency path that solves all identified problems.

---

## Proposed Design

### `schema_migrations` Tracking Table

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum TEXT
);
```

Applied once by `migrate.py` itself (bootstraps the tracker). The `checksum` column (SHA-256 of the file content) allows detecting modified-after-applied migrations.

### Migration File Format

Plain SQL. Each file is executed as a single transaction. No special syntax.

```sql
-- migrations/0003_withings.sql
CREATE TABLE IF NOT EXISTS body_measurements (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'withings',
    weight_kg REAL,
    fat_percent REAL,
    measured_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, source)
);

CREATE INDEX IF NOT EXISTS idx_body_measurements_date ON body_measurements(date);
CREATE INDEX IF NOT EXISTS idx_body_measurements_source ON body_measurements(source);
```

### `server/migrate.py` Runner (Sketch)

```python
"""Standalone migration runner. Usage: python -m server.migrate"""

import os
import hashlib
from pathlib import Path
import psycopg2
import psycopg2.extras

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def run_migrations(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                checksum TEXT
            )
        """)
        conn.commit()

        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        applied = {row[0] for row in cur.fetchall()}

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    pending = [f for f in migration_files if f.name not in applied]

    if not pending:
        print("No pending migrations.")
        return

    for path in pending:
        sql = path.read_text()
        checksum = hashlib.sha256(sql.encode()).hexdigest()[:16]
        print(f"Applying {path.name} ...")
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
                (path.name, checksum),
            )
        conn.commit()
        print(f"  Done: {path.name}")


if __name__ == "__main__":
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    psycopg2.extras.register_dict(conn)
    run_migrations(conn)
    conn.close()
```

### `init_db()` After Migration

`init_db()` is removed entirely. `server/database.py` no longer contains any DDL or seeding logic. The app startup path no longer calls it.

The `_SCHEMA` blob, all migration groups, `_seed_workout_templates()`, and `_seed_macro_targets()` are removed from `database.py`. All of that content moves to `migrations/0001_baseline.sql`.

### Cloud Build Integration

Add a migration step to **both** `cloudbuild.yaml` (prod) and `cloudbuild-test.yaml` (beta) immediately before the Cloud Run deploy step. The step runs the already-built image against the database before any traffic is routed to the new revision.

```yaml
  # Run database migrations before deploying
  - name: 'gcr.io/cloud-builders/docker'
    id: 'migrate'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        docker run --rm \
          -e DATABASE_URL=$$CYCLING_COACH_DATABASE_URL \
          ${_REGION}-docker.pkg.dev/${PROJECT_ID}/${_REPO}/${_SERVICE_NAME}:$$(cat /workspace/TAG_VERSION) \
          python -m server.migrate
    secretEnv: ['CYCLING_COACH_DATABASE_URL']
```

The secret must also be declared in the `availableSecrets` block of each file (it is already present for the deploy step — verify it is accessible here too).

A migration failure causes a non-zero exit, which aborts the Cloud Build pipeline before `gcloud run deploy` runs. No partial deploy.

### Baseline Migration Strategy

`0001_baseline.sql` is derived from the existing `_SCHEMA` blob in `server/database.py`, not from a prod dump. This makes the schema reproducible from scratch and allows replaying migrations to any point in time without prod-specific artifacts.

Steps:
1. Extract `_SCHEMA` from `database.py` verbatim — it already uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` throughout
2. Append the three migration groups currently inline in `init_db()` (they represent schema that already exists in prod, so they must be in the baseline, not as separate migrations)
3. Append seed data as `INSERT ... ON CONFLICT DO NOTHING` for `workout_templates` and `macro_targets` (replaces `_seed_workout_templates` / `_seed_macro_targets`)
4. Add `CREATE TABLE IF NOT EXISTS schema_migrations (...)` at the top so the baseline is self-bootstrapping
5. Review, test against a clean Postgres container, commit

All subsequent migrations (0002+) represent schema changes made after this baseline is established.

---

## Decisions

1. **`migrate.py` runs only in Cloud Build — not at startup.** Removes startup latency entirely. For local dev, developers run `python -m server.migrate` manually when pulling branches with new migration files. The Cloud Build pipeline applies migrations as a pre-deploy step before routing traffic.

2. **Baseline from `_SCHEMA`, not `pg_dump`.** Deriving `0001_baseline.sql` from the existing `_SCHEMA` blob makes the schema reproducible from scratch and allows replaying migrations to any point in time. A prod dump is environment-specific and not suitable as a canonical baseline.

3. **Test fixture calls `run_migrations()` (idempotent).** `tests/integration/conftest.py` replaces its `init_db()` call with `run_migrations(conn)`. Since every migration is guarded by `schema_migrations` tracking, this is safe to call on every test suite invocation against the disposable test container.

4. **Seed data lives in the baseline migration.** `_seed_workout_templates` and `_seed_macro_targets` are only needed in new dev environments and integration tests. Seed inserts belong in `migrations/0001_baseline.sql` as `INSERT ... ON CONFLICT DO NOTHING` statements, removing the Python seeding functions entirely.

5. **The `/release` skill is updated to be migration-aware.** The skill gains a pre-tag check: if any `migrations/*.sql` files are new or modified and not yet committed, the release is blocked until they are staged. For prod releases, the skill notes that Cloud Build applies pending migrations automatically before traffic shifts. See `.claude/commands/release.md`.

6. **Rollback is roll-forward only.** No downgrade support. To revert a schema change, write a new forward migration that reverses it. Acceptable trade-off given the additive nature of schema changes so far.

7. **`plans/bug-fix-integration-test-failures.md` deleted.** Dated and irrelevant; removed from the repo.
