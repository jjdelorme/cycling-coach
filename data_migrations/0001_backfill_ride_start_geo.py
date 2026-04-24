"""Backfill rides.start_lat / rides.start_lon for ICU-synced rides.

Recovers GPS coordinates that were silently dropped by the pre-fix
``server.services.sync._normalize_latlng`` parser. Walks every ride with
``start_lat IS NULL`` whose filename looks like ``icu_<icu_id>``, re-fetches
streams from intervals.icu, and lets ``_backfill_start_location`` populate
the row.

Idempotent: ``WHERE start_lat IS NULL`` guard means re-runs are no-ops.
Skipped (and recorded as applied) when ``INTERVALS_ICU_DISABLED`` /
``INTERVALS_ICU_DISABLE`` is set so local-dev boots stay fast.
"""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)


def _icu_id_from_filename(filename: str) -> str:
    if filename.startswith("icu_"):
        return filename[len("icu_"):]
    return filename


def _icu_disabled() -> bool:
    for var in ("INTERVALS_ICU_DISABLED", "INTERVALS_ICU_DISABLE"):
        val = os.environ.get(var, "")
        if val.lower() in ("1", "true", "yes"):
            return True
    return False


def run(conn, *, sleep_seconds: float = 0.5) -> dict:
    if _icu_disabled():
        logger.info("INTERVALS_ICU disabled — skipping backfill")
        return {"skipped": True, "reason": "icu_disabled"}

    from server.database import get_db
    from server.services import sync as sync_module
    from server.services.sync import _backfill_start_location

    counts = {
        "total": 0,
        "backfilled": 0,
        "no_streams": 0,
        "no_gps_in_streams": 0,
        "already_populated": 0,
        "errors": 0,
    }

    with get_db() as db:
        rides = db.execute(
            "SELECT id, filename FROM rides "
            "WHERE start_lat IS NULL AND filename LIKE 'icu_%' "
            "ORDER BY start_time DESC"
        ).fetchall()
        counts["total"] = len(rides)
        logger.info("found %d candidate rides", counts["total"])

        for ride in rides:
            ride_row = dict(ride)
            ride_id = ride_row["id"]
            filename = ride_row["filename"]
            icu_id = _icu_id_from_filename(filename)

            try:
                streams = sync_module.fetch_activity_streams(icu_id)
            except Exception as exc:  # noqa: BLE001
                counts["errors"] += 1
                logger.warning(
                    "ride %s (%s) stream fetch failed: %s", ride_id, filename, exc
                )
                continue

            if not streams:
                counts["no_streams"] += 1
                logger.info(
                    "ride %s (%s) has no streams (indoor?)", ride_id, filename
                )
                continue

            before = db.execute(
                "SELECT start_lat FROM rides WHERE id = ?", (ride_id,)
            ).fetchone()
            _backfill_start_location(ride_id, streams, conn=db)
            after = db.execute(
                "SELECT start_lat FROM rides WHERE id = ?", (ride_id,)
            ).fetchone()
            before_val = (dict(before) if before else {}).get("start_lat")
            after_val = (dict(after) if after else {}).get("start_lat")
            if before_val is None and after_val is not None:
                counts["backfilled"] += 1
                logger.info(
                    "ride %s (%s) backfilled to (%s, ...)",
                    ride_id,
                    filename,
                    after_val,
                )
            else:
                counts["no_gps_in_streams"] += 1
                logger.info(
                    "ride %s (%s) streams contained no usable GPS",
                    ride_id,
                    filename,
                )

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        db.commit()

    logger.info(
        "summary: total=%d backfilled=%d no_streams=%d no_gps_in_streams=%d "
        "already_populated=%d errors=%d",
        counts["total"],
        counts["backfilled"],
        counts["no_streams"],
        counts["no_gps_in_streams"],
        counts["already_populated"],
        counts["errors"],
    )
    return counts
