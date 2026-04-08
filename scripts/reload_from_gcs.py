"""
Reload all data from GCS bucket gs://jasondel-coach-data from scratch.

Steps:
  1. Download JSON ride files and ZWO workout files from GCS to temp dirs
  2. Nuke all ride/workout/PMC data from the database (keep athlete_settings,
     periodization_phases, users, coach data)
  3. Run the existing ingest pipeline unchanged (ingest_rides → ingest_workouts
     → backfill_laps → backfill_hr_tss → compute_daily_pmc → seed_periodization)

Run with: source venv/bin/activate && python -m scripts.reload_from_gcs
"""

import logging
import os
import sys
import tempfile
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

GCS_BUCKET = "jasondel-coach-data"
GCS_JSON_PREFIX = "json/"
GCS_WORKOUTS_PREFIX = "planned_workouts/"


def download_from_gcs(bucket, prefix, dest_dir, ext_filter=None):
    """Download all blobs with prefix to dest_dir. Returns count."""
    blobs = list(bucket.list_blobs(prefix=prefix))
    downloaded = 0
    skipped = 0
    for blob in blobs:
        fname = os.path.basename(blob.name)
        if not fname:
            continue
        if ext_filter and not fname.lower().endswith(ext_filter):
            continue
        dest = os.path.join(dest_dir, fname)
        if os.path.exists(dest):
            skipped += 1
            continue
        blob.download_to_filename(dest)
        downloaded += 1
    logger.info("  Downloaded %d, skipped %d already-present from gs://%s/%s",
                downloaded, skipped, GCS_BUCKET, prefix)
    return downloaded + skipped


def nuke_ride_data(conn):
    """Truncate all ride and workout data. Preserve athlete_settings,
    periodization_phases, users, coach_memory, coach_settings, workout_templates,
    sync_runs, sync_watermarks."""
    logger.info("Nuking existing ride/workout/PMC data...")
    # Order matters — FK children before parents
    conn.execute("TRUNCATE TABLE ride_records CASCADE")
    conn.execute("TRUNCATE TABLE ride_laps CASCADE")
    conn.execute("TRUNCATE TABLE power_bests CASCADE")
    conn.execute("DELETE FROM rides")
    conn.execute("TRUNCATE TABLE daily_metrics")
    conn.execute("TRUNCATE TABLE planned_workouts")
    logger.info("  Tables cleared.")


def main():
    from google.cloud import storage
    from server.database import init_db, get_db

    # Verify DATABASE_URL target before touching anything
    db_url = os.environ.get("CYCLING_COACH_DATABASE_URL", "")
    if not db_url:
        logger.error("CYCLING_COACH_DATABASE_URL not set — aborting.")
        sys.exit(1)
    if "localhost" in db_url or "127.0.0.1" in db_url:
        logger.error("DATABASE_URL points to localhost — this script is for the Neon test DB. Aborting.")
        sys.exit(1)
    logger.info("Target DB: %s", db_url.split("@")[-1])  # log host only, not credentials

    # Create temp dirs for downloaded files
    tmp_root = tempfile.mkdtemp(prefix="coach_gcs_")
    rides_dir = os.path.join(tmp_root, "rides")
    workouts_dir = os.path.join(tmp_root, "workouts")
    os.makedirs(rides_dir, exist_ok=True)
    os.makedirs(workouts_dir, exist_ok=True)
    logger.info("Temp dirs: %s", tmp_root)

    # ── Step 1: Download from GCS ─────────────────────────────────────────
    logger.info("=== Step 1: Downloading from gs://%s ===", GCS_BUCKET)
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    logger.info("Downloading JSON ride files...")
    t0 = time.perf_counter()
    ride_count = download_from_gcs(bucket, GCS_JSON_PREFIX, rides_dir, ext_filter=".json")
    logger.info("  %d ride JSON files ready (%.1fs)", ride_count, time.perf_counter() - t0)

    logger.info("Downloading ZWO workout files...")
    t0 = time.perf_counter()
    workout_count = download_from_gcs(bucket, GCS_WORKOUTS_PREFIX, workouts_dir, ext_filter=".zwo")
    logger.info("  %d ZWO workout files ready (%.1fs)", workout_count, time.perf_counter() - t0)

    # ── Step 2: Nuke & re-init schema ────────────────────────────────────
    logger.info("=== Step 2: Resetting database ===")
    init_db()  # Ensures schema and migrations are current
    with get_db() as conn:
        nuke_ride_data(conn)

    # ── Step 3: Run the existing ingest pipeline ──────────────────────────
    logger.info("=== Step 3: Running ingest pipeline ===")
    from server.ingest import (
        ingest_rides,
        ingest_workouts,
        backfill_laps,
        backfill_hr_tss,
        compute_daily_pmc,
        seed_periodization,
    )

    with get_db() as conn:
        logger.info("Ingesting rides (%d JSON files)...", ride_count)
        t0 = time.perf_counter()
        ingested_rides = ingest_rides(conn, rides_dir=rides_dir)
        logger.info("  Ingested %d rides (%.1fs)", ingested_rides, time.perf_counter() - t0)

        logger.info("Ingesting planned workouts (%d ZWO files)...", workout_count)
        t0 = time.perf_counter()
        ingested_workouts = ingest_workouts(conn, workouts_dir=workouts_dir)
        logger.info("  Ingested %d workouts (%.1fs)", ingested_workouts, time.perf_counter() - t0)

        logger.info("Backfilling laps...")
        t0 = time.perf_counter()
        backfill_laps(conn, rides_dir=rides_dir)
        logger.info("  Done (%.1fs)", time.perf_counter() - t0)

        logger.info("Backfilling hrTSS for rides without power...")
        t0 = time.perf_counter()
        backfill_hr_tss(conn)
        logger.info("  Done (%.1fs)", time.perf_counter() - t0)

        logger.info("Computing PMC (CTL/ATL/TSB)...")
        t0 = time.perf_counter()
        compute_daily_pmc(conn)
        logger.info("  Done (%.1fs)", time.perf_counter() - t0)

        logger.info("Seeding periodization phases (if empty)...")
        seed_periodization(conn)

        # ── Final summary ─────────────────────────────────────────────────
        logger.info("=== Summary ===")
        for table, label in [
            ("rides", "Rides"),
            ("ride_records", "Ride records"),
            ("ride_laps", "Laps"),
            ("power_bests", "Power bests"),
            ("planned_workouts", "Planned workouts"),
            ("daily_metrics", "PMC days"),
            ("periodization_phases", "Phases"),
        ]:
            cnt = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()["cnt"]
            logger.info("  %-20s %d", label, cnt)

    logger.info("=== Done. Temp files at %s (safe to delete) ===", tmp_root)


if __name__ == "__main__":
    main()
