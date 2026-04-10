"""Integration test for meal analysis rate limiting."""


def test_rate_limit_count_query(db_conn):
    """Verify rate limit count query works against the real DB."""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")

    # Insert 20 meal rows directly to simulate hitting the limit
    for i in range(20):
        db_conn.execute(
            "INSERT INTO meal_logs (user_id, date, logged_at, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                "athlete",
                today,
                f"{today}T{10 + i // 6}:{(i * 10) % 60:02d}:00",
                f"Rate limit test meal {i + 1}",
                500,
                30,
                50,
                20,
            ),
        )
    db_conn.commit()

    # Verify the count query returns >= 20
    count_row = db_conn.execute(
        "SELECT COUNT(*) AS cnt FROM meal_logs WHERE date = %s AND user_id = %s",
        (today, "athlete"),
    ).fetchone()
    assert count_row["cnt"] >= 20


def test_rate_limit_constant_matches_router():
    """DAILY_ANALYSIS_LIMIT constant is accessible and equals 20."""
    from server.routers.nutrition import DAILY_ANALYSIS_LIMIT

    assert DAILY_ANALYSIS_LIMIT == 20


def test_rate_limit_429_response(client, db_conn):
    """POST /api/nutrition/meals returns 429 after daily limit is reached."""
    from datetime import datetime
    import io

    today = datetime.now().strftime("%Y-%m-%d")

    # Ensure we have at least 20 meals for today
    existing = db_conn.execute(
        "SELECT COUNT(*) AS cnt FROM meal_logs WHERE date = %s AND user_id = %s",
        (today, "athlete"),
    ).fetchone()

    needed = 20 - existing["cnt"]
    for i in range(max(needed, 0)):
        db_conn.execute(
            "INSERT INTO meal_logs (user_id, date, logged_at, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                "athlete",
                today,
                f"{today}T08:{i:02d}:00",
                f"Rate limit 429 test meal {i + 1}",
                400,
                25,
                40,
                15,
            ),
        )
    db_conn.commit()

    # Attempt the 21st analysis — should get 429
    # Create a minimal valid JPEG (smallest valid JPEG is ~107 bytes)
    fake_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xd9"
    )

    r = client.post(
        "/api/nutrition/meals",
        files={"file": ("test.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
        data={"comment": "This should be rate limited", "meal_type": "snack"},
    )
    assert r.status_code == 429
    assert "limit" in r.json()["detail"].lower()
