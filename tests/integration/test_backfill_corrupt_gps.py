"""Integration tests for ``scripts/backfill_corrupt_gps.py`` (Phase 9, C20).

The backfill walks every ride in the DB, detects the D4 corruption
signature on the per-record GPS, and re-syncs the records via the
Phase 6 ``_store_records_or_fallback`` helper. Tests cover the
detection thresholds, the dry-run vs write paths, error handling, and
the ``--limit`` knob — all driven in-process so we do not need to fork
the script or hit the real ICU API.
"""

from __future__ import annotations

import pytest

from scripts.backfill_corrupt_gps import detect_corruption, run_backfill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_corrupt_ride(db_conn, *, icu_id: str, n_records: int, lat: float, lon: float) -> int:
    """Insert one ``rides`` row + ``n_records`` ``ride_records`` rows with
    the D4 lat==lon corruption signature, return the ride id."""
    res = db_conn.execute(
        """INSERT INTO rides (start_time, filename, sport, duration_s, distance_m)
           VALUES ('2026-04-13T14:30:00', %s, 'ride', %s, 0)
           RETURNING id""",
        (f"icu_{icu_id}", n_records),
    ).fetchone()
    ride_id = res["id"]
    db_conn.executemany(
        "INSERT INTO ride_records (ride_id, lat, lon) VALUES (%s, %s, %s)",
        [(ride_id, lat, lon)] * n_records,
    )
    db_conn.commit()
    return ride_id


def _seed_clean_ride(db_conn, *, icu_id: str, n_records: int, lat: float, lon: float) -> int:
    """Insert one clean (non-corrupt) ride for control."""
    res = db_conn.execute(
        """INSERT INTO rides (start_time, filename, sport, duration_s, distance_m)
           VALUES ('2026-04-13T14:30:00', %s, 'ride', %s, 0)
           RETURNING id""",
        (f"icu_{icu_id}", n_records),
    ).fetchone()
    ride_id = res["id"]
    db_conn.executemany(
        "INSERT INTO ride_records (ride_id, lat, lon) VALUES (%s, %s, %s)",
        [(ride_id, lat, lon)] * n_records,
    )
    db_conn.commit()
    return ride_id


def _cleanup(db_conn, ride_ids: list[int]):
    if not ride_ids:
        return
    placeholders = ", ".join(["%s"] * len(ride_ids))
    db_conn.execute(
        f"DELETE FROM ride_records WHERE ride_id IN ({placeholders})", tuple(ride_ids)
    )
    db_conn.execute(
        f"DELETE FROM rides WHERE id IN ({placeholders})", tuple(ride_ids)
    )
    db_conn.commit()


# ---------------------------------------------------------------------------
# detect_corruption — pure function (no DB)
# ---------------------------------------------------------------------------


def test_detect_corruption_flags_lat_lat_pairs():
    """100 records with lat == lon trip the D4 corruption signature."""
    records = [{"lat": 39.75, "lon": 39.75}] * 100
    result = detect_corruption(records)
    assert result["total"] == 100
    assert result["suspect"] == 100
    assert result["corrupt"] is True


def test_detect_corruption_passes_real_us_ride():
    """100 records of a real US ride (negative lon) are NOT corrupt."""
    records = [{"lat": 39.75, "lon": -105.3}] * 100
    result = detect_corruption(records)
    assert result["total"] == 100
    assert result["suspect"] == 0
    assert result["corrupt"] is False


def test_detect_corruption_passes_short_ride():
    """30 records is below MIN_GPS_RECORDS_FOR_DETECTION (60), so even a
    full-corrupt sample is NOT flagged. Avoids false positives on tiny
    test fixtures and very short rides."""
    records = [{"lat": 39.75, "lon": 39.75}] * 30
    result = detect_corruption(records)
    assert result["total"] == 30
    assert result["corrupt"] is False


# ---------------------------------------------------------------------------
# run_backfill — drives detection + re-sync against the test DB
# ---------------------------------------------------------------------------


def test_run_backfill_dry_run_makes_no_writes(db_conn, monkeypatch):
    """dry_run=True emits the WOULD-resync log but issues no UPDATEs."""
    from server.services import sync as sync_module

    ride_id = _seed_corrupt_ride(db_conn, icu_id="i_dry_1", n_records=100, lat=39.75, lon=39.75)
    try:
        # Confirm seed: ride is corrupt right now.
        rows_before = db_conn.execute(
            "SELECT lat, lon FROM ride_records WHERE ride_id = %s", (ride_id,)
        ).fetchall()
        assert all(abs(r["lat"] - r["lon"]) < 1.0 for r in rows_before)

        # Monkeypatch FIT to a healthy US ride. Dry-run must NOT call this,
        # so a side-effect counter doubles as a guard.
        call_count = {"n": 0}

        def fake_fit_all(_):
            call_count["n"] += 1
            return {"laps": [], "records": [
                {"timestamp_utc": f"2026-04-13T14:30:{i % 60:02d}+00:00",
                 "power": 200, "heart_rate": 140, "cadence": 85,
                 "speed": 7.5, "altitude": 1500.0, "distance": float(i),
                 "lat": 39.75, "lon": -108.71, "temperature": 22}
                for i in range(100)
            ]}

        monkeypatch.setattr(sync_module, "fetch_activity_fit_all", fake_fit_all)

        counts = run_backfill(dry_run=True, sleep_seconds=0.0)

        assert counts["total_corrupt"] >= 1
        assert counts["fixed"] == 0
        assert call_count["n"] == 0, "dry-run must not invoke ICU fetches"
        # Rows unchanged.
        rows_after = db_conn.execute(
            "SELECT lat, lon FROM ride_records WHERE ride_id = %s", (ride_id,)
        ).fetchall()
        assert all(abs(r["lat"] - r["lon"]) < 1.0 for r in rows_after)
    finally:
        _cleanup(db_conn, [ride_id])


def test_run_backfill_writes_when_not_dry_run(db_conn, monkeypatch):
    """dry_run=False replaces corrupt records with the FIT-derived ones."""
    from server.services import sync as sync_module

    ride_id = _seed_corrupt_ride(db_conn, icu_id="i_wet_1", n_records=100, lat=39.75, lon=39.75)
    try:
        def fake_fit_all(_):
            return {"laps": [], "records": [
                {"timestamp_utc": f"2026-04-13T14:30:{i % 60:02d}+00:00",
                 "power": 200, "heart_rate": 140, "cadence": 85,
                 "speed": 7.5, "altitude": 1500.0, "distance": float(i),
                 "lat": 39.75, "lon": -108.71, "temperature": 22}
                for i in range(100)
            ]}

        # Streams call is exercised after a successful FIT records write
        # for the metric pipeline; return an empty dict so the streams
        # path is a no-op for this test.
        monkeypatch.setattr(sync_module, "fetch_activity_fit_all", fake_fit_all)
        monkeypatch.setattr(sync_module, "fetch_activity_streams", lambda i: {})

        counts = run_backfill(dry_run=False, sleep_seconds=0.0)

        assert counts["fixed"] >= 1
        rows_after = db_conn.execute(
            "SELECT lat, lon FROM ride_records WHERE ride_id = %s", (ride_id,)
        ).fetchall()
        # All 100 rows now reverse-geocode to the US (negative lon) and
        # have a real (lat, lon) pair, NOT the (lat, lat) corruption.
        assert len(rows_after) == 100
        assert all(r["lon"] < 0 for r in rows_after)
        assert all(abs(r["lat"] - r["lon"]) > 100 for r in rows_after)
    finally:
        _cleanup(db_conn, [ride_id])


def test_run_backfill_handles_no_fit_no_streams(db_conn, monkeypatch):
    """When BOTH FIT and streams fail, the row is left alone so the next
    run can retry. The summary counts the failure."""
    from server.services import sync as sync_module

    ride_id = _seed_corrupt_ride(db_conn, icu_id="i_fail_1", n_records=100, lat=39.75, lon=39.75)
    try:
        monkeypatch.setattr(
            sync_module, "fetch_activity_fit_all",
            lambda i: {"laps": [], "records": []},
        )
        monkeypatch.setattr(sync_module, "fetch_activity_streams", lambda i: {})

        counts = run_backfill(dry_run=False, sleep_seconds=0.0)

        # Failed = either fit_unavailable or icu_api_error; nothing fixed.
        assert counts["fixed"] == 0
        assert counts["fit_unavailable"] + counts["icu_api_error"] >= 1
        # Row still corrupt → next run can retry.
        rows_after = db_conn.execute(
            "SELECT lat, lon FROM ride_records WHERE ride_id = %s", (ride_id,)
        ).fetchall()
        assert len(rows_after) == 100
        assert all(abs(r["lat"] - r["lon"]) < 1.0 for r in rows_after)
    finally:
        _cleanup(db_conn, [ride_id])


def test_run_backfill_respects_limit(db_conn, monkeypatch):
    """With 5 corrupt rides seeded and limit=2, only 2 are fixed."""
    from server.services import sync as sync_module

    ride_ids = [
        _seed_corrupt_ride(db_conn, icu_id=f"i_limit_{i}", n_records=100, lat=39.75, lon=39.75)
        for i in range(5)
    ]
    try:
        monkeypatch.setattr(
            sync_module, "fetch_activity_fit_all",
            lambda i: {"laps": [], "records": [
                {"timestamp_utc": f"2026-04-13T14:30:{j % 60:02d}+00:00",
                 "power": 200, "heart_rate": 140, "cadence": 85,
                 "speed": 7.5, "altitude": 1500.0, "distance": float(j),
                 "lat": 39.75, "lon": -108.71, "temperature": 22}
                for j in range(100)
            ]},
        )
        monkeypatch.setattr(sync_module, "fetch_activity_streams", lambda i: {})

        counts = run_backfill(dry_run=False, sleep_seconds=0.0, limit=2)

        assert counts["fixed"] == 2
        # Pull the lat/lon for all 5 rides; exactly 2 should be repaired.
        repaired_count = 0
        for rid in ride_ids:
            rows = db_conn.execute(
                "SELECT lat, lon FROM ride_records WHERE ride_id = %s", (rid,)
            ).fetchall()
            if all(r["lon"] < 0 for r in rows):
                repaired_count += 1
        assert repaired_count == 2
    finally:
        _cleanup(db_conn, ride_ids)
