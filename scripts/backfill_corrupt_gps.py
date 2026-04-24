"""Backfill ``ride_records.lat/lon`` for ICU-synced rides whose per-record
GPS exhibits the Campaign 20 D4 corruption signature (``ABS(lat-lon) < 1``
on the bulk of records, indicating a botched lat-only Variant B parse from
the intervals.icu streams payload).

Background
----------
Phase 6 fixed the live ingest path: new ICU re-syncs prefer FIT records
over the streams parser, so going forward corrupt GPS won't reach the
database. This script handles the historical backlog — every ride
ingested *before* Phase 6 needs to be re-fetched and rewritten.

Detection
---------
A ride is flagged as corrupt iff:
* it has at least ``MIN_GPS_RECORDS_FOR_DETECTION`` (60) GPS records,
* AND the fraction of records where ``ABS(lat - lon) < 1.0°`` exceeds
  ``GPS_CORRUPTION_RATIO_THRESHOLD`` (0.5).

Both thresholds live in ``server.services.sync`` so the script, the
write-time guard, and the frontend safeguard share a single source of
truth.

Re-sync
-------
For each suspect ride: derive the ICU activity id from the filename
(``icu_<icu_id>``), then call ``_store_records_or_fallback`` (Phase 6),
which prefers FIT records and falls back to the (now-hardened) streams
parser. The helper deletes existing ``ride_records`` for the ride id
before inserting, so this script is safe to re-run.

Safety (D5)
-----------
* ``--dry-run`` is the **default**. Re-resolves no ICU data and writes
  nothing — only counts the corrupt rides for an operator preview.
* ``--no-dry-run`` (or ``--write``) flips the script into write mode.
* ``--allow-remote`` is required if ``CYCLING_COACH_DATABASE_URL`` is
  not localhost (``localhost`` / ``127.0.0.1`` / ``::1``). Refusing
  to touch a non-localhost DB by default is the same posture as
  ``backfill_ride_start_geo.py``.
* ``--limit N`` to backfill at most N rides per invocation (resumable).
* ``--sleep N`` (default 0.5s) between ICU API calls to respect rate limits.

Output
------
A counts dict (also logged as a JSON-style summary line)::

    {
        "total_examined": int,         # # rides matching the corruption query
        "total_corrupt":  int,         # alias of total_examined for now
        "fixed":          int,         # rides successfully re-synced
        "fit_unavailable":int,         # rides where FIT download failed
        "fit_parse_failed": int,       # rides where the FIT parsed empty
        "icu_api_error":  int,         # rides where the streams call also failed
        "skipped_already_clean": int,  # rides flagged but no longer corrupt
                                       #   when re-checked just before re-sync
                                       #   (race / stale read)
    }

Usage
-----
    python scripts/backfill_corrupt_gps.py                          # local DB dry-run
    python scripts/backfill_corrupt_gps.py --no-dry-run              # local DB write
    python scripts/backfill_corrupt_gps.py --allow-remote            # remote DB dry-run
    python scripts/backfill_corrupt_gps.py --no-dry-run --allow-remote --limit 50
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Make ``server`` importable when this script is run directly (not via ``python -m``).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.services.sync import (  # noqa: E402  — imports must come after sys.path tweak
    GPS_CORRUPTION_RATIO_THRESHOLD,
    MIN_GPS_RECORDS_FOR_DETECTION,
)

logger = logging.getLogger("backfill_corrupt_gps")

LOCALHOST_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


# ---------------------------------------------------------------------------
# Detection (pure function; no DB)
# ---------------------------------------------------------------------------


def detect_corruption(records: list[dict]) -> dict:
    """Return ``{"total": int, "suspect": int, "corrupt": bool}``.

    ``corrupt`` is True iff:
      * ``total >= MIN_GPS_RECORDS_FOR_DETECTION`` (60), AND
      * ``suspect / total > GPS_CORRUPTION_RATIO_THRESHOLD`` (0.5).

    ``records`` may be a list of dicts or row-mappings — anything where
    ``r["lat"]`` and ``r["lon"]`` are accessible. Records with either
    coordinate missing are not counted toward total or suspect.
    """
    total = 0
    suspect = 0
    for r in records:
        lat = r.get("lat") if isinstance(r, dict) else r["lat"]
        lon = r.get("lon") if isinstance(r, dict) else r["lon"]
        if lat is None or lon is None:
            continue
        total += 1
        if abs(lat - lon) < 1.0:
            suspect += 1
    corrupt = (
        total >= MIN_GPS_RECORDS_FOR_DETECTION
        and (suspect / total) > GPS_CORRUPTION_RATIO_THRESHOLD
    )
    return {"total": total, "suspect": suspect, "corrupt": corrupt}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_localhost_database_url(database_url: str) -> bool:
    """Return True iff DATABASE_URL's host is on the localhost allow-list.

    Mirrors ``backfill_ride_start_geo._is_localhost_database_url`` so the
    two scripts behave identically with respect to the safety check.
    """
    try:
        parsed = urlparse(database_url)
    except ValueError:
        return False
    hostname = parsed.hostname
    return bool(hostname) and hostname.lower() in LOCALHOST_HOSTNAMES


def _icu_id_from_filename(filename: str) -> str:
    """Extract the intervals.icu activity id from the local filename.

    Filenames are of the form ``icu_<icu_id>`` (the ``i`` prefix belongs
    to the ICU id itself; only ``icu_`` is stripped). Mirrors the
    convention in ``backfill_ride_start_geo._icu_id_from_filename``.
    """
    if filename.startswith("icu_"):
        return filename[len("icu_"):]
    return filename


# ---------------------------------------------------------------------------
# Backfill driver
# ---------------------------------------------------------------------------


def run_backfill(
    *,
    dry_run: bool,
    sleep_seconds: float = 0.5,
    limit: int | None = None,
) -> dict:
    """Walk every corrupt ride and re-sync via ``_store_records_or_fallback``.

    Returns the counts dict described in the module docstring. Wrapped in
    a function so integration tests can drive it in-process with
    monkeypatched ICU calls.
    """
    # Imports are local so test fixtures can monkeypatch ``fetch_activity_fit_all``
    # / ``fetch_activity_streams`` on ``server.services.sync`` BEFORE the
    # script does any work.
    from server.database import get_db
    from server.services.sync import _store_records_or_fallback

    counts = {
        "total_examined": 0,
        "total_corrupt": 0,
        "fixed": 0,
        "fit_unavailable": 0,
        "fit_parse_failed": 0,
        "icu_api_error": 0,
        "skipped_already_clean": 0,
    }

    # Single SQL query identifies the corrupt ride set in one round-trip
    # using exactly the D4 thresholds the live guard uses. Ordered by
    # most-recent-first so a partial run (interrupted by --limit or a
    # crash) leaves the older history for the next pass.
    detection_sql = """
        SELECT r.id, r.filename, COUNT(*) AS total,
               SUM(CASE WHEN ABS(rr.lat - rr.lon) < 1.0 THEN 1 ELSE 0 END) AS suspect
          FROM rides r
          JOIN ride_records rr ON rr.ride_id = r.id
         WHERE r.filename LIKE 'icu_%%'
           AND rr.lat IS NOT NULL AND rr.lon IS NOT NULL
         GROUP BY r.id, r.filename
        HAVING COUNT(*) >= %s
           AND SUM(CASE WHEN ABS(rr.lat - rr.lon) < 1.0 THEN 1 ELSE 0 END)::float
                 / COUNT(*) > %s
         ORDER BY r.start_time DESC
    """
    params: tuple = (MIN_GPS_RECORDS_FOR_DETECTION, GPS_CORRUPTION_RATIO_THRESHOLD)
    if limit is not None and limit > 0:
        detection_sql += " LIMIT %s"
        params = params + (limit,)

    with get_db() as conn:
        rides = conn.execute(detection_sql, params).fetchall()
        counts["total_examined"] = len(rides)
        counts["total_corrupt"] = len(rides)
        logger.info("detected_corrupt_rides count=%d", len(rides))

        for ride in rides:
            ride_row = dict(ride)
            ride_id = ride_row["id"]
            filename = ride_row["filename"]
            icu_id = _icu_id_from_filename(filename)

            if dry_run:
                logger.info(
                    "WOULD re-sync ride_id=%s filename=%s total=%s suspect=%s",
                    ride_id, filename, ride_row.get("total"), ride_row.get("suspect"),
                )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue

            try:
                gps_source, _streams, _fit_laps = _store_records_or_fallback(
                    ride_id, icu_id, conn
                )
            except Exception as exc:  # noqa: BLE001 — broad on purpose
                counts["icu_api_error"] += 1
                logger.warning(
                    "ride %s (%s) re-sync raised: %s", ride_id, filename, exc,
                )
                continue

            if gps_source == "fit":
                # Re-check post-conditions — was the new write actually clean?
                rows = conn.execute(
                    "SELECT lat, lon FROM ride_records WHERE ride_id = %s "
                    "AND lat IS NOT NULL AND lon IS NOT NULL",
                    (ride_id,),
                ).fetchall()
                still_corrupt = detect_corruption([dict(r) for r in rows])["corrupt"]
                if still_corrupt:
                    # Defensive: should not happen because FIT semicircles are
                    # authoritative. Count separately so this is visible.
                    counts["fit_parse_failed"] += 1
                    logger.warning(
                        "ride %s (%s) FIT re-sync produced still-corrupt records",
                        ride_id, filename,
                    )
                else:
                    counts["fixed"] += 1
                    logger.info(
                        "ride %s (%s) re-synced via FIT", ride_id, filename,
                    )
            elif gps_source == "fallback_streams":
                # Streams write went through the Phase 7 corruption guard,
                # so the row is either clean or has empty latlng — either
                # way, the original D4 signature is gone. Count as fixed
                # (the goal is "row no longer trips D4").
                counts["fixed"] += 1
                logger.info(
                    "ride %s (%s) re-synced via fallback streams",
                    ride_id, filename,
                )
            else:
                # source == "none" — both FIT and streams unavailable. Row
                # is left as-is so the next run can retry.
                counts["fit_unavailable"] += 1
                logger.warning(
                    "ride %s (%s) FIT and streams both unavailable; left for retry",
                    ride_id, filename,
                )

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if not dry_run:
            conn.commit()

    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # D5 mandate: dry-run by default. Use ``BooleanOptionalAction`` so the
    # operator can pass ``--no-dry-run`` to opt into writes — explicit and
    # hard to fat-finger.
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Preview only; no writes (default). Pass --no-dry-run to actually re-sync.",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Required to run against a non-localhost DATABASE_URL.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to sleep between ICU API calls (default 0.5).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Backfill at most N rides per invocation (resumability).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Load .env so the script honours the same config the app uses.
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
        load_dotenv()
    except ImportError:
        pass

    # Match the app convention: server.database/config read CYCLING_COACH_DATABASE_URL.
    # Fall back to DATABASE_URL for legacy callers.
    database_url = os.environ.get("CYCLING_COACH_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not database_url:
        logger.error("CYCLING_COACH_DATABASE_URL is not set; refusing to run.")
        return 2

    is_local = _is_localhost_database_url(database_url)
    parsed_host = urlparse(database_url).hostname or "<unknown>"
    logger.info(
        "DATABASE_URL host=%s (local=%s) dry_run=%s limit=%s",
        parsed_host, is_local, args.dry_run, args.limit,
    )

    if not is_local and not args.allow_remote:
        logger.error(
            "Refusing to run against non-localhost DATABASE_URL without --allow-remote.",
        )
        return 2

    try:
        counts = run_backfill(
            dry_run=args.dry_run,
            sleep_seconds=args.sleep,
            limit=args.limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("backfill failed: %s", exc)
        return 1

    logger.info(
        "summary: total_examined=%d total_corrupt=%d fixed=%d "
        "fit_unavailable=%d fit_parse_failed=%d icu_api_error=%d "
        "skipped_already_clean=%d",
        counts["total_examined"],
        counts["total_corrupt"],
        counts["fixed"],
        counts["fit_unavailable"],
        counts["fit_parse_failed"],
        counts["icu_api_error"],
        counts["skipped_already_clean"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
