"""Integration tests for nutrition endpoints."""


def test_get_targets(client):
    """GET /api/nutrition/targets returns default targets."""
    r = client.get("/api/nutrition/targets")
    assert r.status_code == 200
    data = r.json()
    assert "calories" in data
    assert data["calories"] > 0


def test_update_targets(client):
    """PUT /api/nutrition/targets updates and persists."""
    r = client.put("/api/nutrition/targets", json={
        "calories": 2800, "protein_g": 160, "carbs_g": 320, "fat_g": 85,
    })
    assert r.status_code == 200
    # Verify persistence
    r2 = client.get("/api/nutrition/targets")
    assert r2.json()["calories"] == 2800


def test_update_targets_validation(client):
    """PUT /api/nutrition/targets rejects invalid values."""
    r = client.put("/api/nutrition/targets", json={
        "calories": 0, "protein_g": 160, "carbs_g": 320, "fat_g": 85,
    })
    assert r.status_code == 400

    r = client.put("/api/nutrition/targets", json={
        "calories": 2500, "protein_g": -10, "carbs_g": 320, "fat_g": 85,
    })
    assert r.status_code == 400


def test_daily_summary_empty(client):
    """GET /api/nutrition/daily-summary works with no meals."""
    r = client.get("/api/nutrition/daily-summary?date=2026-01-01")
    assert r.status_code == 200
    data = r.json()
    assert data["total_calories_in"] == 0
    assert data["meal_count"] == 0


def test_daily_summary_has_structure(client):
    """GET /api/nutrition/daily-summary returns expected fields."""
    r = client.get("/api/nutrition/daily-summary?date=2026-01-01")
    assert r.status_code == 200
    data = r.json()
    assert "target_calories" in data
    assert "calories_out" in data
    assert "net_caloric_balance" in data
    assert "remaining_calories" in data


def test_list_meals_empty(client):
    """GET /api/nutrition/meals returns empty list initially."""
    r = client.get("/api/nutrition/meals?start_date=2099-01-01&end_date=2099-12-31")
    assert r.status_code == 200
    data = r.json()
    assert data["meals"] == []
    assert data["total"] == 0


def test_meal_not_found(client):
    """GET /api/nutrition/meals/999999 returns 404."""
    r = client.get("/api/nutrition/meals/999999")
    assert r.status_code == 404


def test_delete_meal_not_found(client):
    """DELETE /api/nutrition/meals/999999 returns 404."""
    r = client.delete("/api/nutrition/meals/999999")
    assert r.status_code == 404


def test_update_meal_not_found(client):
    """PUT /api/nutrition/meals/999999 returns 404."""
    r = client.put("/api/nutrition/meals/999999", json={
        "total_calories": 500,
    })
    assert r.status_code == 404


def test_weekly_summary(client):
    """GET /api/nutrition/weekly-summary returns structured weekly data."""
    r = client.get("/api/nutrition/weekly-summary?date=2026-01-05")
    assert r.status_code == 200
    data = r.json()
    assert "week_start" in data
    assert "week_end" in data
    assert "days" in data
    assert len(data["days"]) == 7
    assert "avg_daily_calories" in data


def test_meal_crud_flow(client, db_conn):
    """Create, read, update, delete a meal via direct DB insertion + API."""
    # Insert a meal directly (bypasses agent which we don't want in integration tests)
    db_conn.execute(
        "INSERT INTO meal_logs (user_id, date, logged_at, meal_type, description, "
        "total_calories, total_protein_g, total_carbs_g, total_fat_g, confidence) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("athlete", "2026-04-09", "2026-04-09T12:00:00", "lunch",
         "Test meal", 600, 40.0, 60.0, 20.0, "high"),
    )
    db_conn.commit()

    # Get the meal id
    row = db_conn.execute(
        "SELECT id FROM meal_logs WHERE description = 'Test meal' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    meal_id = row["id"]

    # Insert meal items
    db_conn.execute(
        "INSERT INTO meal_items (meal_id, name, serving_size, calories, protein_g, carbs_g, fat_g) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (meal_id, "Chicken breast", "6 oz", 300, 35.0, 0.0, 7.0),
    )
    db_conn.commit()

    # Read via API
    r = client.get(f"/api/nutrition/meals/{meal_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["description"] == "Test meal"
    assert data["total_calories"] == 600
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Chicken breast"

    # Update via API
    r = client.put(f"/api/nutrition/meals/{meal_id}", json={
        "total_calories": 650,
        "meal_type": "dinner",
    })
    assert r.status_code == 200

    # Verify update
    r = client.get(f"/api/nutrition/meals/{meal_id}")
    data = r.json()
    assert data["total_calories"] == 650
    assert data["meal_type"] == "dinner"
    assert data["edited_by_user"] is True

    # Delete via API
    r = client.delete(f"/api/nutrition/meals/{meal_id}")
    assert r.status_code == 200

    # Verify deletion
    r = client.get(f"/api/nutrition/meals/{meal_id}")
    assert r.status_code == 404


def test_nutrition_routes_registered(client):
    """Verify nutrition routes are present in the application."""
    r = client.get("/api/nutrition/targets")
    assert r.status_code == 200  # Route exists and responds


def test_coaching_nutrition_tool_exists():
    """Verify get_athlete_nutrition_status is importable from coaching tools."""
    from server.coaching.tools import get_athlete_nutrition_status
    assert callable(get_athlete_nutrition_status)


# ---------------------------------------------------------------------------
# Daily summary with rides (regression: rides.date column missing)
# ---------------------------------------------------------------------------

def test_daily_summary_with_rides(client, db_conn):
    """GET /api/nutrition/daily-summary works when rides exist for the date.

    Regression: the rides table might lack a 'date' column if it was created
    before the migration system. The query 'SELECT ... FROM rides WHERE date = %s'
    must not crash.
    """
    # Use a seed-data date that has rides, or insert one for a far-future date
    date = "2098-11-01"
    try:
        db_conn.execute(
            "INSERT INTO rides (date, filename, sport, sub_sport, duration_s, "
            "total_calories, tss) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (date, f"test_ride_{date}.fit", "cycling", "road", 3600, 800, 70),
        )
        db_conn.commit()

        r = client.get(f"/api/nutrition/daily-summary?date={date}")
        assert r.status_code == 200
        data = r.json()
        assert data["calories_out"]["rides"] == 800
        assert data["calories_out"]["total"] > 800  # rides + BMR
    finally:
        db_conn.execute("DELETE FROM rides WHERE filename = %s", (f"test_ride_{date}.fit",))
        db_conn.commit()


def test_weekly_summary_with_rides(client, db_conn):
    """GET /api/nutrition/weekly-summary includes ride calories when rides exist."""
    date = "2098-11-03"  # a Wednesday
    try:
        db_conn.execute(
            "INSERT INTO rides (date, filename, sport, sub_sport, duration_s, "
            "total_calories, tss) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (date, f"test_ride_{date}.fit", "cycling", "road", 5400, 1100, 95),
        )
        db_conn.commit()

        r = client.get(f"/api/nutrition/weekly-summary?date={date}")
        assert r.status_code == 200
        data = r.json()
        # Find the day with the ride
        ride_day = next((d for d in data["days"] if d["date"] == date), None)
        assert ride_day is not None
        assert ride_day["calories_out_rides"] == 1100
    finally:
        db_conn.execute("DELETE FROM rides WHERE filename = %s", (f"test_ride_{date}.fit",))
        db_conn.commit()


# ---------------------------------------------------------------------------
# Tool date serialization (regression: datetime.date not JSON-serializable)
# ---------------------------------------------------------------------------

def test_upcoming_training_load_dates_are_strings(db_conn):
    """get_upcoming_training_load returns string dates regardless of DB column type.

    Regression: if planned_workouts.date is a PostgreSQL DATE type instead of TEXT,
    the tool returned datetime.date objects which crashed ADK's JSON serialization.
    """
    import json
    from server.nutrition.tools import get_upcoming_training_load
    from datetime import datetime, timedelta

    # Insert a future workout
    future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        db_conn.execute(
            "INSERT INTO planned_workouts (date, name, total_duration_s, planned_tss) "
            "VALUES (%s, %s, %s, %s)",
            (future, "Test Integration Ride", 3600, 50),
        )
        db_conn.commit()

        result = get_upcoming_training_load(days_ahead=3)

        # All dates must be strings, not datetime.date
        for day in result["days"]:
            assert isinstance(day["date"], str), f"date is {type(day['date'])}, expected str"

        # Must be JSON-serializable
        json.dumps(result)  # raises TypeError if date objects present
    finally:
        db_conn.execute("DELETE FROM planned_workouts WHERE name = %s", ("Test Integration Ride",))
        db_conn.commit()


def test_recent_workouts_dates_are_strings(db_conn):
    """get_recent_workouts returns string dates regardless of DB column type."""
    import json
    from server.nutrition.tools import get_recent_workouts

    result = get_recent_workouts(days_back=7)

    for ride in result:
        assert isinstance(ride["date"], str), f"date is {type(ride['date'])}, expected str"

    # Must be JSON-serializable
    json.dumps(result)
