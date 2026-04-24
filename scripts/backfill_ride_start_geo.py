"""Backfill ``rides.start_lat`` / ``rides.start_lon`` for ICU-synced rides.

KNOWN BUG (do not use against prod until fixed): when the ICU
``/api/v1/activity/{id}/streams`` endpoint returns the typed-entry shape
(``[{"type": "latlng", "data": [...lats...], "data2": [...lons...]}]``),
``server.services.sync._extract_streams`` reads ``data`` only and drops
``data2``. Downstream, ``_backfill_start_location`` then writes
``(lat, lat)`` — the Syria-bug signature. Detected during svc-pgdb
testing of the data-migrations framework PR; tracked for fix in the
follow-up branch (see roadmap Campaign 23 / 17 follow-up).

Background
----------
Until the ``server.services.sync._normalize_latlng`` parser was fixed, every
intervals.icu-synced outdoor ride landed in the database with
``start_lat IS NULL`` because the parser only handled the nested-pair shape
of the ``latlng`` stream and silently dropped the flat-floats shape ICU
actually returns. Existing rides therefore need a one-time backfill: this
script walks every ride with ``start_lat IS NULL`` whose filename looks
like ``icu_<icu_id>``, re-fetches the streams from intervals.icu, and lets
the (now-fixed) ``_backfill_start_location`` helper update the row.

Safety
------
The script refuses to run unless ``DATABASE_URL`` points at a localhost
host (``localhost`` / ``127.0.0.1`` / ``::1``) **or** ``--allow-remote``
is passed explicitly. ``--dry-run`` shows what would happen without
issuing any UPDATEs. The underlying ``_backfill_start_location`` SQL is
guarded by ``WHERE start_lat IS NULL`` so re-running the script is a
no-op once the backfill has succeeded.

Usage
-----
    python scripts/backfill_ride_start_geo.py            # local DB
    python scripts/backfill_ride_start_geo.py --dry-run  # preview only
    python scripts/backfill_ride_start_geo.py --allow-remote  # explicit opt-in
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Make `server` importable when this script is run directly (not via `python -m`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("backfill_ride_start_geo")

LOCALHOST_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def _is_localhost_database_url(database_url: str) -> bool:
    """Return True iff DATABASE_URL's host is on the localhost allow-list.

    Uses ``urllib.parse`` to extract the hostname so substrings like
    ``localhost.example.com`` (false positive) and ``127.0.0.1`` URLs that
    embed credentials in the userinfo (potential false negative) are handled
    correctly.
    """
    try:
        parsed = urlparse(database_url)
    except ValueError:
        return False
    hostname = parsed.hostname
    return bool(hostname) and hostname.lower() in LOCALHOST_HOSTNAMES


def _icu_id_from_filename(filename: str) -> str:
    """Extract the intervals.icu activity id from the local filename.

    Filenames in the wild look like ``icu_i137210941`` — the ``i`` prefix
    belongs to the ICU id itself, so we only strip the leading ``icu_``.
    Mirrors the convention already used by ``scripts/backfill_icu_streams.py``.
    """
    if filename.startswith("icu_"):
        return filename[len("icu_"):]
    return filename


def run_backfill(*, dry_run: bool, sleep_seconds: float = 0.5) -> dict:
    """Walk ``rides`` with ``start_lat IS NULL`` and re-fetch GPS from ICU.

    Returns a counts dict with keys ``total``, ``backfilled``, ``no_streams``,
    ``no_gps_in_streams``, ``already_populated``, and ``errors``. Wrapped in
    a function so integration tests can drive it in-process.
    """
    # Imports are local so module import time stays cheap and so that test
    # fixtures can monkeypatch ``fetch_activity_streams`` on the sync
    # module before the script does any work.
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

    with get_db() as conn:
        rides = conn.execute(
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
            except Exception as exc:  # noqa: BLE001 — broad on purpose
                counts["errors"] += 1
                logger.warning("ride %s (%s) stream fetch failed: %s", ride_id, filename, exc)
                continue

            if not streams:
                counts["no_streams"] += 1
                logger.info("ride %s (%s) has no streams (indoor?)", ride_id, filename)
                continue

            if dry_run:
                # Quickly check whether the streams contain any GPS so the
                # dry-run summary is meaningful. We do not call the helper
                # so no UPDATE is issued.
                stream_map = sync_module._extract_streams(streams)
                if not stream_map.get("latlng"):
                    counts["no_gps_in_streams"] += 1
                    logger.info("ride %s (%s) streams have no latlng", ride_id, filename)
                else:
                    counts["backfilled"] += 1
                    logger.info("ride %s (%s) WOULD be backfilled", ride_id, filename)
            else:
                # Snapshot before/after so we can distinguish an empty-latlng
                # ride from a successful update without re-querying.
                before = conn.execute(
                    "SELECT start_lat FROM rides WHERE id = ?", (ride_id,)
                ).fetchone()
                _backfill_start_location(ride_id, streams, conn=conn)
                after = conn.execute(
                    "SELECT start_lat FROM rides WHERE id = ?", (ride_id,)
                ).fetchone()
                before_val = (dict(before) if before else {}).get("start_lat")
                after_val = (dict(after) if after else {}).get("start_lat")
                if before_val is None and after_val is not None:
                    counts["backfilled"] += 1
                    logger.info("ride %s (%s) backfilled to (%s, ...)", ride_id, filename, after_val)
                else:
                    counts["no_gps_in_streams"] += 1
                    logger.info("ride %s (%s) streams contained no usable GPS", ride_id, filename)

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if not dry_run:
            conn.commit()

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only; do not write.")
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
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Load .env so the script honours the same config the app uses.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Match the app's convention: server.database/config read CYCLING_COACH_DATABASE_URL.
    # Fall back to DATABASE_URL for legacy callers.
    database_url = os.environ.get("CYCLING_COACH_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not database_url:
        logger.error("CYCLING_COACH_DATABASE_URL is not set; refusing to run.")
        return 2

    is_local = _is_localhost_database_url(database_url)
    parsed_host = urlparse(database_url).hostname or "<unknown>"
    logger.info("DATABASE_URL host=%s (local=%s)", parsed_host, is_local)

    if not is_local and not args.allow_remote:
        logger.error(
            "Refusing to run against non-localhost DATABASE_URL without --allow-remote."
        )
        return 2

    try:
        counts = run_backfill(dry_run=args.dry_run, sleep_seconds=args.sleep)
    except Exception as exc:  # noqa: BLE001
        logger.exception("backfill failed: %s", exc)
        return 1

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
