"""Standalone migration runner.

Usage:
    python -m server.migrate

Applies all pending migrations in migrations/ to the database tracked in
schema_migrations. Safe to run multiple times — already-applied migrations
are skipped.
"""

import hashlib
import os
import sys
from pathlib import Path

import psycopg2

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

_DEFAULT_URL = "postgresql://postgres:dev@localhost:5432/coach"


def run_migrations(conn) -> int:
    """Apply all pending .sql migrations. Returns the count of applied migrations."""
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

    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        applied = {row[0] for row in cur.fetchall()}

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    pending = [f for f in migration_files if f.name not in applied]

    if not pending:
        print("No pending migrations.", flush=True)
        return 0

    count = 0
    for path in pending:
        sql = path.read_text()
        checksum = hashlib.sha256(sql.encode()).hexdigest()[:16]
        print(f"Applying {path.name} ...", flush=True)
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
                (path.name, checksum),
            )
        conn.commit()
        print(f"  Done: {path.name}", flush=True)
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
        applied = run_migrations(conn)
        print(f"\nMigrations applied: {applied}", flush=True)
    finally:
        conn.close()
    sys.exit(0)
