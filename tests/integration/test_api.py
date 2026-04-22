"""Tests for API endpoints using the real database."""

import pytest

from server.database import get_db


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["rides"] > 0


def test_list_rides(client):
    resp = client.get("/api/rides?limit=10")
    assert resp.status_code == 200
    rides = resp.json()
    assert len(rides) <= 10
    assert "date" in rides[0]
    assert "avg_power" in rides[0]


def test_filter_rides_by_date(client):
    resp = client.get("/api/rides?start_date=2025-08-01&end_date=2025-08-31")
    assert resp.status_code == 200
    rides = resp.json()
    assert all("2025-08" in r["date"] for r in rides)


# ---------------------------------------------------------------------------
# Free-text search (?q=)
# ---------------------------------------------------------------------------

def _ride_text_blob(ride: dict) -> str:
    """All free-text columns concatenated, lowercased — used to verify hits."""
    parts = [
        ride.get("title") or "",
        ride.get("post_ride_comments") or "",
        ride.get("coach_comments") or "",
    ]
    return " ".join(parts).lower()


# A magic phrase chosen to be vanishingly unlikely to collide with seed data.
# Each fixture row exercises one of the three searched columns.
_TEXT_FIXTURE_ROWS = [
    # (filename, title, post_ride_comments, coach_comments)
    ("textq_fixture_a.json", "Tuesday qsearchneedle1 Threshold", None, None),
    ("textq_fixture_b.json", "Sunday Long Ride", "felt strong, qsearchneedle2 in legs", None),
    ("textq_fixture_c.json", "Recovery Spin", None, "great qsearchneedle3 — well executed"),
    ("textq_fixture_d.json", "Wednesday Endurance qsearchneedle1 base", "easy qsearchneedle2 day", None),
    ("textq_fixture_e.json", "Saturday Group Ride", None, None),
]


def _install_text_search_fixtures(conn) -> set[int]:
    """Insert (or reuse) deterministic rides for free-text search tests.

    Returns the set of inserted ride ids so tests can clean up if needed.
    The fixtures use a fixed start_time in 2099 so they sort to the top of
    DESC ordering and never collide with real seed dates. All numeric columns
    that other endpoints aggregate (e.g. /summary/monthly) are populated with
    safe non-null values to avoid contaminating other tests in the session.
    """
    ids: set[int] = set()
    for i, (filename, title, post, coach) in enumerate(_TEXT_FIXTURE_ROWS):
        # Idempotent: skip if already present from a previous test run in the
        # same session (the test DB is disposable but session-scoped).
        existing = conn.execute(
            "SELECT id FROM rides WHERE filename = %s", (filename,)
        ).fetchone()
        if existing:
            ids.add(existing["id"])
            continue
        row = conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s, distance_m,"
            " tss, total_ascent, title, post_ride_comments, coach_comments)"
            f" VALUES ('2099-06-{i+1:02d}T10:00:00+00:00', %s, 'ride', 3600, 30000,"
            " 50, 100, %s, %s, %s) RETURNING id",
            (filename, title, post, coach),
        ).fetchone()
        ids.add(row["id"])
    conn.commit()
    return ids


def test_filter_rides_by_q_returns_matches(client, db_conn):
    _install_text_search_fixtures(db_conn)
    resp = client.get("/api/rides?q=qsearchneedle1")
    assert resp.status_code == 200
    rides = resp.json()
    titles = {r.get("title") for r in rides}
    assert "Tuesday qsearchneedle1 Threshold" in titles
    assert "Wednesday Endurance qsearchneedle1 base" in titles
    # Every returned ride must contain the needle in at least one searched column.
    for r in rides:
        assert "qsearchneedle1" in _ride_text_blob(r)


def test_filter_rides_by_q_searches_post_ride_comments(client, db_conn):
    _install_text_search_fixtures(db_conn)
    resp = client.get("/api/rides?q=qsearchneedle2")
    assert resp.status_code == 200
    titles = {r.get("title") for r in resp.json()}
    assert "Sunday Long Ride" in titles
    assert "Wednesday Endurance qsearchneedle1 base" in titles


def test_filter_rides_by_q_searches_coach_comments(client, db_conn):
    _install_text_search_fixtures(db_conn)
    resp = client.get("/api/rides?q=qsearchneedle3")
    assert resp.status_code == 200
    titles = {r.get("title") for r in resp.json()}
    assert titles == {"Recovery Spin"}


def test_filter_rides_by_q_no_matches_returns_empty(client):
    resp = client.get("/api/rides?q=zzznotatitleanywhereinseed")
    assert resp.status_code == 200
    assert resp.json() == []


def test_filter_rides_by_q_is_case_insensitive(client, db_conn):
    _install_text_search_fixtures(db_conn)
    lower = client.get("/api/rides?q=qsearchneedle1").json()
    upper = client.get("/api/rides?q=QSEARCHNEEDLE1").json()
    mixed = client.get("/api/rides?q=QsEaRcHnEeDlE1").json()
    assert len(lower) == len(upper) == len(mixed) >= 2
    assert {r["id"] for r in lower} == {r["id"] for r in upper} == {r["id"] for r in mixed}


def test_filter_rides_by_q_multi_word_ands_terms(client, db_conn):
    """Multi-word search ANDs each word with OR-across-columns per word."""
    _install_text_search_fixtures(db_conn)
    # 'qsearchneedle1 qsearchneedle2' should match only fixture_d (the only
    # row where both needles appear, even though they are in different columns).
    both = client.get("/api/rides?q=qsearchneedle1+qsearchneedle2").json()
    titles = {r.get("title") for r in both}
    assert titles == {"Wednesday Endurance qsearchneedle1 base"}

    # Pairing one real needle with a non-existent word must yield zero results.
    none = client.get("/api/rides?q=qsearchneedle1+xyznoexistword").json()
    assert none == []


def test_filter_rides_by_q_composes_with_date_range(client, db_conn):
    _install_text_search_fixtures(db_conn)
    # The fixtures all start in 2099-06; the date filter excludes them.
    pre = client.get(
        "/api/rides?q=qsearchneedle1&start_date=2025-01-01&end_date=2025-12-31"
    ).json()
    assert pre == []

    # And includes them when the range covers 2099-06.
    inside = client.get(
        "/api/rides?q=qsearchneedle1&start_date=2099-01-01&end_date=2099-12-31"
    ).json()
    assert len(inside) == 2


# ---------------------------------------------------------------------------
# Location radius (?near_lat=&near_lon=&radius_km=)
# ---------------------------------------------------------------------------

# Magic centre well outside the seed area so we can place fixtures at known
# distances without colliding with anything in seed_data.json.gz.
_GEO_CENTER_LAT = 35.6870
_GEO_CENTER_LON = -105.9378  # Santa Fe, NM

_GEO_FIXTURE_ROWS = [
    # (filename, lat_offset_km, lon_offset_km, distance_label)
    # Offsets are converted to degrees using the same 111.32 km/° constant
    # the SQL uses, then placed via the helper below. We deliberately
    # straddle the radius=10km boundary so the Haversine post-filter is
    # exercised.
    ("georadius_at_center", 0.0, 0.0),       # exactly on centre
    ("georadius_5km_north", 5.0, 0.0),       # 5 km north
    ("georadius_25km_east", 0.0, 25.0),      # 25 km east — outside 10km
    ("georadius_500km_far", 500.0, 0.0),     # very far away
]


def _install_geo_fixtures(conn):
    """Insert fixture rides at known (lat, lon) offsets from the centre."""
    from math import cos, radians

    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * cos(radians(_GEO_CENTER_LAT))

    for i, (filename, north_km, east_km) in enumerate(_GEO_FIXTURE_ROWS):
        existing = conn.execute(
            "SELECT id FROM rides WHERE filename = %s", (filename,)
        ).fetchone()
        if existing:
            continue
        lat = _GEO_CENTER_LAT + north_km / km_per_deg_lat
        lon = _GEO_CENTER_LON + east_km / km_per_deg_lon
        conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s,"
            " distance_m, tss, total_ascent, start_lat, start_lon)"
            f" VALUES ('2099-08-{i+1:02d}T10:00:00+00:00', %s, 'ride',"
            " 3600, 30000, 50, 100, %s, %s)",
            (filename, lat, lon),
        )
    conn.commit()


def test_radius_returns_only_rides_within_circle(client, db_conn):
    _install_geo_fixtures(db_conn)
    resp = client.get(
        f"/api/rides?near_lat={_GEO_CENTER_LAT}&near_lon={_GEO_CENTER_LON}&radius_km=10"
    )
    assert resp.status_code == 200
    filenames = {r["filename"] for r in resp.json()}
    # The 0km and 5km fixtures must be in; the 25km and 500km fixtures must not.
    assert "georadius_at_center" in filenames
    assert "georadius_5km_north" in filenames
    assert "georadius_25km_east" not in filenames
    assert "georadius_500km_far" not in filenames


def test_radius_excludes_everything_when_centred_on_null_island(client, db_conn):
    _install_geo_fixtures(db_conn)
    resp = client.get("/api/rides?near_lat=0.0&near_lon=0.0&radius_km=1")
    assert resp.status_code == 200
    filenames = {r["filename"] for r in resp.json()}
    assert not any(f.startswith("georadius_") for f in filenames)


def test_radius_without_near_returns_400(client):
    resp = client.get("/api/rides?radius_km=10")
    assert resp.status_code == 400


def test_huge_radius_returns_every_geo_fixture(client, db_conn):
    _install_geo_fixtures(db_conn)
    resp = client.get(
        f"/api/rides?near_lat={_GEO_CENTER_LAT}&near_lon={_GEO_CENTER_LON}&radius_km=500"
    )
    assert resp.status_code == 200
    filenames = {r["filename"] for r in resp.json()}
    # All fixtures within 500 km show up; the 500km-due-north one is right at
    # the boundary so we don't insist on it specifically.
    assert "georadius_at_center" in filenames
    assert "georadius_5km_north" in filenames
    assert "georadius_25km_east" in filenames


def test_radius_composes_with_q_filter(client, db_conn):
    """Radius + q must AND together — both filters apply."""
    _install_geo_fixtures(db_conn)
    # Insert a radius-fixture row that ALSO contains a free-text needle.
    existing = db_conn.execute(
        "SELECT id FROM rides WHERE filename = %s", ("georadius_with_q",)
    ).fetchone()
    if not existing:
        db_conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s,"
            " distance_m, tss, total_ascent, start_lat, start_lon, title)"
            " VALUES ('2099-08-15T10:00:00+00:00', %s, 'ride',"
            " 3600, 30000, 50, 100, %s, %s, %s)",
            ("georadius_with_q", _GEO_CENTER_LAT, _GEO_CENTER_LON, "georadiusqnedle"),
        )
        db_conn.commit()
    resp = client.get(
        f"/api/rides?near_lat={_GEO_CENTER_LAT}&near_lon={_GEO_CENTER_LON}"
        "&radius_km=10&q=georadiusqnedle"
    )
    assert resp.status_code == 200
    rides = resp.json()
    assert len(rides) == 1
    assert rides[0]["filename"] == "georadius_with_q"


def test_get_single_ride(client):
    # Find a ride that has records
    with get_db() as conn:
        row = conn.execute(
            "SELECT ride_id FROM ride_records LIMIT 1"
        ).fetchone()
    if not row:
        pytest.skip("No ride records in test DB")
    ride_id = row["ride_id"]

    resp = client.get(f"/api/rides/{ride_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert "records" in detail
    assert len(detail["records"]) > 0


def test_ride_not_found(client):
    resp = client.get("/api/rides/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Per-record GPS shape on /api/rides/{id} (Campaign 20: Ride Map)
#
# The Ride Map feature consumes records[].lat / records[].lon directly from
# this endpoint. These tests lock in that contract:
#   - outdoor rides surface non-null lat/lon coordinates
#   - indoor / no-GPS rides surface null lat/lon for every record
#
# Both are first-class states in the frontend (the map card hides itself for
# indoor rides), so any future change that drops the lat/lon columns from the
# SELECT — or that returns half-coords — must fail loudly here.
# ---------------------------------------------------------------------------

# Magic filenames so fixture rides do not collide with seed data.
_GPS_OUTDOOR_FIXTURE = "ridemap_outdoor_fixture.json"
_GPS_INDOOR_FIXTURE = "ridemap_indoor_fixture.json"


def _install_ridemap_gps_fixtures(conn) -> dict[str, int]:
    """Install one outdoor (GPS-bearing) and one indoor (no-GPS) fixture ride.

    Returns a mapping {"outdoor": ride_id, "indoor": ride_id}.
    Idempotent — re-uses existing rows on rerun.
    """
    ids: dict[str, int] = {}

    # Outdoor ride with a small synthetic polyline ---------------------------
    # NOTE: deliberately seated in 2098 (not 2099) to avoid collision with
    # other tests in this file that DELETE FROM rides WHERE start_time >=
    # '2099-01-01' without cleaning up child ride_records first.
    existing = conn.execute(
        "SELECT id FROM rides WHERE filename = %s", (_GPS_OUTDOOR_FIXTURE,)
    ).fetchone()
    if existing:
        ids["outdoor"] = existing["id"]
    else:
        row = conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s,"
            " distance_m, tss, total_ascent, start_lat, start_lon, title)"
            " VALUES ('2098-09-01T10:00:00+00:00', %s, 'ride', 600, 5000,"
            " 25, 50, %s, %s, %s) RETURNING id",
            (_GPS_OUTDOOR_FIXTURE, 44.166893, -71.164314, "Ridemap outdoor fixture"),
        ).fetchone()
        ids["outdoor"] = row["id"]
        # Synthetic 10-point polyline marching a hair north-east.
        for i in range(10):
            conn.execute(
                "INSERT INTO ride_records (ride_id, timestamp_utc, power, lat, lon)"
                " VALUES (%s, %s, %s, %s, %s)",
                (
                    ids["outdoor"],
                    f"2098-09-01T10:00:{i:02d}+00:00",
                    150 + i,
                    44.166893 + i * 0.0001,
                    -71.164314 + i * 0.0001,
                ),
            )

    # Indoor ride: records exist but lat/lon are NULL for every row ----------
    existing = conn.execute(
        "SELECT id FROM rides WHERE filename = %s", (_GPS_INDOOR_FIXTURE,)
    ).fetchone()
    if existing:
        ids["indoor"] = existing["id"]
    else:
        row = conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s,"
            " distance_m, tss, total_ascent, title)"
            " VALUES ('2098-09-02T10:00:00+00:00', %s, 'VirtualRide', 600,"
            " 5000, 25, 0, %s) RETURNING id",
            (_GPS_INDOOR_FIXTURE, "Ridemap indoor fixture"),
        ).fetchone()
        ids["indoor"] = row["id"]
        for i in range(10):
            conn.execute(
                "INSERT INTO ride_records (ride_id, timestamp_utc, power, lat, lon)"
                " VALUES (%s, %s, %s, NULL, NULL)",
                (ids["indoor"], f"2098-09-02T10:00:{i:02d}+00:00", 150 + i),
            )

    conn.commit()
    return ids


def test_ride_detail_includes_per_record_gps(client, db_conn):
    """Outdoor rides expose non-null lat/lon on every record."""
    ids = _install_ridemap_gps_fixtures(db_conn)
    resp = client.get(f"/api/rides/{ids['outdoor']}")
    assert resp.status_code == 200
    detail = resp.json()
    records = detail["records"]
    assert len(records) > 0

    gps_records = [r for r in records if r["lat"] is not None]
    assert len(gps_records) >= 2, "outdoor fixture must surface ≥ 2 GPS points"

    for r in records:
        # No half-coords: lat and lon must agree on null-ness.
        if r["lat"] is None:
            assert r["lon"] is None, f"half-coord (lon set, lat null): {r}"
        else:
            assert r["lon"] is not None, f"half-coord (lat set, lon null): {r}"
            assert -90 <= r["lat"] <= 90, f"lat out of range: {r['lat']}"
            assert -180 <= r["lon"] <= 180, f"lon out of range: {r['lon']}"


def test_ride_detail_indoor_returns_no_gps_records(client, db_conn):
    """Indoor / no-GPS rides surface null lat/lon for every record.

    The frontend map card is hidden when no usable GPS exists; this contract
    is what the placeholder logic depends on.
    """
    ids = _install_ridemap_gps_fixtures(db_conn)
    resp = client.get(f"/api/rides/{ids['indoor']}")
    assert resp.status_code == 200
    detail = resp.json()
    records = detail["records"]
    assert len(records) > 0
    for r in records:
        assert r["lat"] is None, f"indoor record unexpectedly has lat: {r}"
        assert r["lon"] is None, f"indoor record unexpectedly has lon: {r}"


def test_weekly_summary(client):
    resp = client.get("/api/rides/summary/weekly")
    assert resp.status_code == 200
    weeks = resp.json()
    assert len(weeks) > 0
    assert "week" in weeks[0]
    assert "tss" in weeks[0]


def test_monthly_summary(client):
    resp = client.get("/api/rides/summary/monthly")
    assert resp.status_code == 200
    months = resp.json()
    assert len(months) > 0


def test_pmc(client):
    resp = client.get("/api/pmc")
    assert resp.status_code == 200
    pmc = resp.json()
    assert len(pmc) > 0
    assert "ctl" in pmc[0]


def test_pmc_current(client):
    resp = client.get("/api/pmc/current")
    assert resp.status_code == 200
    data = resp.json()
    assert "ctl" in data
    assert "tsb" in data


def test_power_curve(client):
    resp = client.get("/api/analysis/power-curve")
    assert resp.status_code == 200
    curve = resp.json()
    assert len(curve) > 0
    durations = [c["duration_s"] for c in curve]
    assert 60 in durations  # 1min
    assert 300 in durations  # 5min
    # Campaign 4: avg_hr is now included in power curve response
    assert "avg_hr" in curve[0]
    # Each duration should appear exactly once (DISTINCT ON)
    assert len(durations) == len(set(durations))


def test_power_curve_history(client):
    resp = client.get("/api/analysis/power-curve/history")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) > 0


def test_efficiency(client):
    resp = client.get("/api/analysis/efficiency")
    assert resp.status_code == 200
    ef = resp.json()
    if len(ef) > 0:
        assert "ef" in ef[0]
        # Campaign 4: rolling_ef is now included
        assert "rolling_ef" in ef[0]


def test_zones_spike_filter(client):
    """Test /api/analysis/zones ignores power spikes (>2000W or >5x FTP)."""
    with get_db() as conn:
        # Create a mock ride with FTP = 200
        row = conn.execute(
            "INSERT INTO rides (start_time, filename, sport, ftp) VALUES ('2099-01-01T10:00:00+00:00', 'mock_spike.json', 'ride', 200) RETURNING id"
        ).fetchone()
        ride_id = row["id"]

        # Insert records: 100W (valid), 2001W (too high), 1001W (> 5x 200)
        conn.execute("INSERT INTO ride_records (ride_id, power) VALUES (?, ?)", (ride_id, 100))
        conn.execute("INSERT INTO ride_records (ride_id, power) VALUES (?, ?)", (ride_id, 2001))
        conn.execute("INSERT INTO ride_records (ride_id, power) VALUES (?, ?)", (ride_id, 1001))
        conn.commit()

    try:
        # Fetch zones for that date
        resp = client.get("/api/analysis/zones?start_date=2099-01-01&end_date=2099-01-01")
        assert resp.status_code == 200
        data = resp.json()
        # Should only have 1 sample (the 100W one) because other two are spikes
        assert data["total_samples"] == 1
    finally:
        with get_db() as conn:
            conn.execute("DELETE FROM ride_records WHERE ride_id = ?", (ride_id,))
            conn.execute("DELETE FROM rides WHERE id = ?", (ride_id,))
            conn.commit()


def test_efficiency_enhanced(client):
    """Test /api/analysis/efficiency filtering and rolling average."""
    with get_db() as conn:
        # Clear any existing data on our test dates
        conn.execute("DELETE FROM rides WHERE start_time >= '2099-01-01T00:00:00+00:00'")

        # Ride 1: Jan 1, 31min, IF 0.7, sport 'ride', EF = 200/100 = 2.0
        conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s, intensity_factor, normalized_power, avg_hr) "
            "VALUES ('2099-01-01T10:00:00+00:00', 'ef1.json', 'ride', 1860, 0.7, 200, 100)"
        )
        # Ride 2: Jan 2, 31min, IF 0.7, sport 'ride', EF = 300/100 = 3.0. Rolling EF = (2+3)/2 = 2.5
        conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s, intensity_factor, normalized_power, avg_hr) "
            "VALUES ('2099-01-02T10:00:00+00:00', 'ef2.json', 'ride', 1860, 0.7, 300, 100)"
        )
        # Ride 3: Too short (29min) - should be excluded
        conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s, intensity_factor, normalized_power, avg_hr) "
            "VALUES ('2099-01-03T10:00:00+00:00', 'ef3.json', 'ride', 1740, 0.7, 200, 100)"
        )
        # Ride 4: Too intense (IF 0.85) - should be excluded
        conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s, intensity_factor, normalized_power, avg_hr) "
            "VALUES ('2099-01-04T10:00:00+00:00', 'ef4.json', 'ride', 1860, 0.85, 200, 100)"
        )
        # Ride 5: Wrong sport ('run') - should be excluded
        conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s, intensity_factor, normalized_power, avg_hr) "
            "VALUES ('2099-01-05T10:00:00+00:00', 'ef5.json', 'run', 1860, 0.7, 200, 100)"
        )
        # Ride 6: Feb 15 (45 days later), 31min, IF 0.7, sport 'ride', EF = 400/100 = 4.0.
        # Rolling EF = 4.0 because Jan rides are out of range.
        conn.execute(
            "INSERT INTO rides (start_time, filename, sport, duration_s, intensity_factor, normalized_power, avg_hr) "
            "VALUES ('2099-02-15T10:00:00+00:00', 'ef6.json', 'ride', 1860, 0.7, 400, 100)"
        )
        conn.commit()

    try:
        resp = client.get("/api/analysis/efficiency?start_date=2099-01-01")
        assert resp.status_code == 200
        data = resp.json()

        # Sort results for easier verification
        mock_efs = sorted([r for r in data if r["date"] >= '2099-01-01'], key=lambda x: x["date"])

        # Only Ride 1, 2, and 6 should be included
        assert len(mock_efs) == 3

        # Ride 1
        assert mock_efs[0]["date"] == '2099-01-01'
        assert mock_efs[0]["ef"] == 2.0
        assert mock_efs[0]["rolling_ef"] == 2.0

        # Ride 2
        assert mock_efs[1]["date"] == '2099-01-02'
        assert mock_efs[1]["ef"] == 3.0
        assert mock_efs[1]["rolling_ef"] == 2.5

        # Ride 6
        assert mock_efs[2]["date"] == '2099-02-15'
        assert mock_efs[2]["ef"] == 4.0
        assert mock_efs[2]["rolling_ef"] == 4.0

    finally:
        with get_db() as conn:
            conn.execute("DELETE FROM rides WHERE start_time >= '2099-01-01T00:00:00+00:00'")
            conn.commit()


def test_ftp_history(client):
    resp = client.get("/api/analysis/ftp-history")
    assert resp.status_code == 200
    ftp = resp.json()
    assert len(ftp) > 0
    assert "ftp" in ftp[0]


def test_macro_plan(client):
    resp = client.get("/api/plan/macro")
    assert resp.status_code == 200
    phases = resp.json()
    assert len(phases) == 5
    assert phases[0]["name"] == "Base Rebuild"


def test_week_plan(client):
    resp = client.get("/api/plan/week/2025-08-15")
    assert resp.status_code == 200
    data = resp.json()
    assert "planned" in data
    assert "actual" in data


def test_compliance(client):
    resp = client.get("/api/plan/compliance")
    assert resp.status_code == 200
    data = resp.json()
    assert "planned" in data
    assert "compliance_pct" in data


def test_integration_status(client):
    resp = client.get("/api/plan/integrations/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "intervals_icu" in data


def test_workout_detail(client):
    """Test workout detail endpoint returns steps."""
    from server.routers.planning import _parse_zwo_steps
    with get_db() as conn:
        rows = conn.execute("SELECT id, workout_xml FROM planned_workouts WHERE workout_xml IS NOT NULL").fetchall()
    
    # Find a workout that actually has parseable steps
    target_id = None
    for r in rows:
        if len(_parse_zwo_steps(r["workout_xml"])) > 0:
            target_id = r["id"]
            break
            
    if not target_id:
        pytest.skip("No workouts with XML containing valid steps")
        
    resp = client.get(f"/api/plan/workouts/{target_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "steps" in data
    assert len(data["steps"]) > 0
    assert "ftp" in data


def test_workout_download_tcx(client):
    """Test TCX download."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM planned_workouts WHERE workout_xml IS NOT NULL LIMIT 1").fetchone()
    if not row:
        pytest.skip("No workouts with XML")
    resp = client.get(f"/api/plan/workouts/{row['id']}/download?fmt=tcx")
    assert resp.status_code == 200
    assert "TrainingCenterDatabase" in resp.text
