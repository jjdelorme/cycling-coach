"""Integration tests for meal plan API endpoints."""

import json


def _insert_planned_meal(db_conn, date, meal_slot, name, calories, protein, carbs, fat,
                         description="", items=None, agent_notes=""):
    """Helper to insert a planned meal directly into the DB."""
    items_json = json.dumps(items) if items else None
    db_conn.execute(
        "INSERT INTO planned_meals (user_id, date, meal_slot, name, description, "
        "total_calories, total_protein_g, total_carbs_g, total_fat_g, items, agent_notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (user_id, date, meal_slot) DO UPDATE SET "
        "name = EXCLUDED.name, total_calories = EXCLUDED.total_calories, "
        "total_protein_g = EXCLUDED.total_protein_g, total_carbs_g = EXCLUDED.total_carbs_g, "
        "total_fat_g = EXCLUDED.total_fat_g",
        ("athlete", date, meal_slot, name, description,
         calories, protein, carbs, fat, items_json, agent_notes),
    )
    db_conn.commit()


def _insert_actual_meal(db_conn, date, meal_type, description, calories, protein, carbs, fat):
    """Helper to insert an actual meal log directly into the DB."""
    db_conn.execute(
        "INSERT INTO meal_logs (user_id, date, logged_at, meal_type, description, "
        "total_calories, total_protein_g, total_carbs_g, total_fat_g, confidence) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("athlete", date, f"{date}T12:00:00", meal_type, description,
         calories, protein, carbs, fat, "high"),
    )
    db_conn.commit()


def _cleanup_planned(db_conn, date):
    """Remove planned meals for a date."""
    db_conn.execute("DELETE FROM planned_meals WHERE date = %s AND user_id = %s", (date, "athlete"))
    db_conn.commit()


def _cleanup_actual(db_conn, date):
    """Remove actual meals for a date."""
    db_conn.execute("DELETE FROM meal_logs WHERE date = %s AND user_id = %s", (date, "athlete"))
    db_conn.commit()


# ---------------------------------------------------------------------------
# GET /api/nutrition/meal-plan
# ---------------------------------------------------------------------------

def test_meal_plan_empty(client):
    """GET /api/nutrition/meal-plan returns empty plan for far-future dates."""
    r = client.get("/api/nutrition/meal-plan?date=2099-01-01&days=3")
    assert r.status_code == 200
    data = r.json()
    assert data["start_date"] == "2099-01-01"
    assert len(data["days"]) == 3
    for day in data["days"]:
        assert day["planned"] == {}
        assert day["actual"] == []
        assert day["day_totals"]["planned_calories"] == 0
        assert day["day_totals"]["actual_calories"] == 0


def test_meal_plan_populated(client, db_conn):
    """GET /api/nutrition/meal-plan returns populated plan data."""
    date = "2098-06-01"
    try:
        _insert_planned_meal(db_conn, date, "breakfast", "Oatmeal with berries",
                             450, 15.0, 65.0, 12.0)
        _insert_planned_meal(db_conn, date, "lunch", "Grilled chicken salad",
                             600, 45.0, 30.0, 25.0)

        r = client.get(f"/api/nutrition/meal-plan?date={date}&days=1")
        assert r.status_code == 200
        data = r.json()
        assert len(data["days"]) == 1

        day = data["days"][0]
        assert day["date"] == date
        assert "breakfast" in day["planned"]
        assert "lunch" in day["planned"]
        assert day["planned"]["breakfast"]["name"] == "Oatmeal with berries"
        assert day["planned"]["breakfast"]["total_calories"] == 450
        assert day["planned"]["lunch"]["name"] == "Grilled chicken salad"
        assert day["day_totals"]["planned_calories"] == 1050
    finally:
        _cleanup_planned(db_conn, date)


def test_meal_plan_default_date(client):
    """GET /api/nutrition/meal-plan without date defaults to today."""
    r = client.get("/api/nutrition/meal-plan")
    assert r.status_code == 200
    data = r.json()
    assert "start_date" in data
    assert len(data["days"]) == 7  # default days=7


# ---------------------------------------------------------------------------
# GET /api/nutrition/meal-plan/{date}
# ---------------------------------------------------------------------------

def test_meal_plan_day_detail(client, db_conn):
    """GET /api/nutrition/meal-plan/{date} returns single day detail."""
    date = "2098-07-01"
    try:
        _insert_planned_meal(db_conn, date, "dinner", "Pasta with salmon",
                             700, 40.0, 80.0, 20.0,
                             description="Post-ride recovery meal",
                             agent_notes="Heavy training day - extra carbs")

        r = client.get(f"/api/nutrition/meal-plan/{date}")
        assert r.status_code == 200
        data = r.json()
        assert data["date"] == date
        assert "dinner" in data["planned"]
        assert data["planned"]["dinner"]["name"] == "Pasta with salmon"
        assert data["planned"]["dinner"]["description"] == "Post-ride recovery meal"
        assert data["planned"]["dinner"]["agent_notes"] == "Heavy training day - extra carbs"
        assert data["day_totals"]["planned_calories"] == 700
    finally:
        _cleanup_planned(db_conn, date)


def test_meal_plan_day_empty(client):
    """GET /api/nutrition/meal-plan/{date} returns empty day for no plans."""
    r = client.get("/api/nutrition/meal-plan/2099-12-31")
    assert r.status_code == 200
    data = r.json()
    assert data["planned"] == {}
    assert data["actual"] == []


# ---------------------------------------------------------------------------
# DELETE /api/nutrition/meal-plan/{date}
# ---------------------------------------------------------------------------

def test_delete_meal_plan_by_date(client, db_conn):
    """DELETE /api/nutrition/meal-plan/{date} clears all meals for a date."""
    date = "2098-08-01"
    try:
        _insert_planned_meal(db_conn, date, "breakfast", "Eggs", 300, 25.0, 5.0, 20.0)
        _insert_planned_meal(db_conn, date, "lunch", "Sandwich", 500, 30.0, 50.0, 15.0)

        r = client.delete(f"/api/nutrition/meal-plan/{date}")
        assert r.status_code == 200
        data = r.json()
        assert data["removed"] == 2
        assert data["meal_slot"] == "all"

        # Verify gone
        r = client.get(f"/api/nutrition/meal-plan/{date}")
        assert r.json()["planned"] == {}
    finally:
        _cleanup_planned(db_conn, date)


def test_delete_meal_plan_by_slot(client, db_conn):
    """DELETE /api/nutrition/meal-plan/{date}?meal_slot= clears a specific slot."""
    date = "2098-08-02"
    try:
        _insert_planned_meal(db_conn, date, "breakfast", "Eggs", 300, 25.0, 5.0, 20.0)
        _insert_planned_meal(db_conn, date, "lunch", "Sandwich", 500, 30.0, 50.0, 15.0)

        r = client.delete(f"/api/nutrition/meal-plan/{date}?meal_slot=breakfast")
        assert r.status_code == 200
        data = r.json()
        assert data["removed"] == 1
        assert data["meal_slot"] == "breakfast"

        # Verify only breakfast removed, lunch remains
        r = client.get(f"/api/nutrition/meal-plan/{date}")
        day = r.json()
        assert "breakfast" not in day["planned"]
        assert "lunch" in day["planned"]
    finally:
        _cleanup_planned(db_conn, date)


def test_delete_meal_plan_invalid_slot(client):
    """DELETE /api/nutrition/meal-plan/{date} rejects invalid meal_slot."""
    r = client.delete("/api/nutrition/meal-plan/2098-08-03?meal_slot=brunch")
    assert r.status_code == 400


def test_delete_meal_plan_empty(client):
    """DELETE /api/nutrition/meal-plan/{date} returns 0 removed for empty date."""
    r = client.delete("/api/nutrition/meal-plan/2099-12-31")
    assert r.status_code == 200
    assert r.json()["removed"] == 0


# ---------------------------------------------------------------------------
# GET/PUT /api/nutrition/preferences
# ---------------------------------------------------------------------------

def test_get_preferences(client):
    """GET /api/nutrition/preferences returns dietary preferences."""
    r = client.get("/api/nutrition/preferences")
    assert r.status_code == 200
    data = r.json()
    assert "dietary_preferences" in data
    assert "nutritionist_principles" in data
    # Should have non-empty defaults
    assert len(data["dietary_preferences"]) > 0
    assert len(data["nutritionist_principles"]) > 0


def test_update_preferences(client):
    """PUT /api/nutrition/preferences updates a section."""
    r = client.put("/api/nutrition/preferences", json={
        "section": "dietary_preferences",
        "value": "- Diet type: Mediterranean\n- Allergies: none",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "updated"
    assert r.json()["section"] == "dietary_preferences"

    # Verify persistence
    r = client.get("/api/nutrition/preferences")
    assert "Mediterranean" in r.json()["dietary_preferences"]


def test_update_preferences_invalid_section(client):
    """PUT /api/nutrition/preferences rejects invalid section."""
    r = client.put("/api/nutrition/preferences", json={
        "section": "invalid_section",
        "value": "test",
    })
    assert r.status_code == 400


def test_update_nutritionist_principles(client):
    """PUT /api/nutrition/preferences can update nutritionist_principles."""
    r = client.put("/api/nutrition/preferences", json={
        "section": "nutritionist_principles",
        "value": "- Custom principle: always eat before rides",
    })
    assert r.status_code == 200

    r = client.get("/api/nutrition/preferences")
    assert "always eat before rides" in r.json()["nutritionist_principles"]


# ---------------------------------------------------------------------------
# Plan-vs-actual matching
# ---------------------------------------------------------------------------

def test_plan_vs_actual_day_totals(client, db_conn):
    """Verify day_totals calculations with both planned and actual meals."""
    date = "2098-09-01"
    try:
        # Insert planned meals
        _insert_planned_meal(db_conn, date, "breakfast", "Oatmeal", 400, 12.0, 60.0, 10.0)
        _insert_planned_meal(db_conn, date, "lunch", "Rice bowl", 600, 35.0, 70.0, 15.0)

        # Insert actual meals
        _insert_actual_meal(db_conn, date, "breakfast", "Oatmeal with honey", 450, 14.0, 65.0, 12.0)

        r = client.get(f"/api/nutrition/meal-plan/{date}")
        assert r.status_code == 200
        data = r.json()

        # Planned totals: 400 + 600 = 1000
        assert data["day_totals"]["planned_calories"] == 1000
        assert data["day_totals"]["planned_protein_g"] == 47.0

        # Actual totals: just one meal logged
        assert data["day_totals"]["actual_calories"] == 450
        assert data["day_totals"]["actual_protein_g"] == 14.0

        # Verify planned dict has both slots
        assert len(data["planned"]) == 2
        # Verify actual list has one entry
        assert len(data["actual"]) == 1
    finally:
        _cleanup_planned(db_conn, date)
        _cleanup_actual(db_conn, date)


def test_plan_items_json_parsed(client, db_conn):
    """Verify items JSON is parsed correctly in meal plan response."""
    date = "2098-09-02"
    items = [
        {"name": "Chicken breast", "calories": 300, "protein_g": 35.0, "carbs_g": 0.0, "fat_g": 7.0},
        {"name": "Brown rice", "calories": 200, "protein_g": 5.0, "carbs_g": 45.0, "fat_g": 2.0},
    ]
    try:
        _insert_planned_meal(db_conn, date, "lunch", "Chicken and rice",
                             500, 40.0, 45.0, 9.0, items=items)

        r = client.get(f"/api/nutrition/meal-plan/{date}")
        data = r.json()
        lunch = data["planned"]["lunch"]
        assert lunch["items"] is not None
        assert len(lunch["items"]) == 2
        assert lunch["items"][0]["name"] == "Chicken breast"
    finally:
        _cleanup_planned(db_conn, date)
