"""Standalone data migration runner.

Usage:
    python -m server.data_migrate

Applies all pending Python data migrations in data_migrations/ to the
database tracked in the data_migrations table. Each module must export a
``run(conn) -> dict`` function. Safe to run multiple times — already-applied
modules are skipped.
"""

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

DATA_MIGRATIONS_DIR = Path(__file__).parent.parent / "data_migrations"

_DEFAULT_URL = "postgresql://postgres:dev@localhost:5432/coach"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_data_migrations(conn, migrations_dir: Path = DATA_MIGRATIONS_DIR) -> int:
    """Apply all pending data migrations. Returns the count of applied migrations."""
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

    migration_files = sorted(
        p for p in migrations_dir.glob("*.py") if not p.name.startswith("__")
    )
    pending = [f for f in migration_files if f.name not in applied]

    if not pending:
        print("No pending data migrations.", flush=True)
        return 0

    count = 0
    for path in pending:
        src = path.read_text()
        checksum = hashlib.sha256(src.encode()).hexdigest()[:16]
        print(f"Applying {path.name} ...", flush=True)
        module = _load_module(path)
        if not hasattr(module, "run"):
            raise RuntimeError(
                f"{path.name} does not export a `run(conn) -> dict` function"
            )
        result = module.run(conn)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO data_migrations (filename, checksum, result)"
                " VALUES (%s, %s, %s)",
                (
                    path.name,
                    checksum,
                    psycopg2.extras.Json(result) if result is not None else None,
                ),
            )
        conn.commit()
        print(f"  Done: {path.name} -> {result}", flush=True)
        count += 1

    return count


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    db_url = os.environ.get("CYCLING_COACH_DATABASE_URL", _DEFAULT_URL)
    conn = psycopg2.connect(db_url)
    try:
        applied = run_data_migrations(conn)
        print(f"\nData migrations applied: {applied}", flush=True)
    finally:
        conn.close()
    sys.exit(0)
