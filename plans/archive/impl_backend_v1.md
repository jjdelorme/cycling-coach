# Macro Tracker v1 — Backend Implementation Plan

> **Single source of truth for the backend engineer.** Every phase lists exact files, function names, patterns to follow, test cases, and verification commands.

## Key Design Decisions (resolved from codebase investigation)

### DECISION Q1: YES — ADK multimodal IS supported

**Evidence:** `server/coaching/agent.py:302-305` constructs `types.Content(role="user", parts=[types.Part.from_text(text=message)])` and passes it to `runner.run_async()` at line 314 via `new_message=content`. ADK's Runner forwards `types.Content` directly to Gemini. Since `types.Content.parts` accepts any `types.Part` including `types.Part.from_image()`, multimodal content with image parts will be forwarded unchanged to the underlying Gemini model.

**Implication for Phase 5:** The Nutritionist agent can receive images directly via `runner.run_async()`. No separate `genai.GenerativeModel.generate_content()` call is needed. Build the `chat()` function to construct `types.Content` with both image and text parts, following the exact pattern at `server/coaching/agent.py:302-305`.

### DECISION Q2: google-cloud-storage NOT in requirements.txt

`requirements.txt` lists `google-cloud-aiplatform[adk]>=1.88.0` but NOT `google-cloud-storage` or `Pillow`. Both must be added explicitly.

### DECISION Q3: TEXT columns confirmed

`rides.date` is `TEXT NOT NULL` (`server/database.py:30`). `daily_metrics.date` is `TEXT PRIMARY KEY` (`server/database.py:124`). All temporal columns use TEXT. Meal tables will follow this pattern.

---

## Phase 1: DB Schema + Seed + Query Helpers

### 1A. Add tables to `_SCHEMA` in `server/database.py`

**Target file:** `server/database.py`
**Location:** Append to the `_SCHEMA` string, BEFORE the closing `"""`  (currently at line 256)
**Pattern:** Follow the existing `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` pattern visible at lines 28-256.

**Add this SQL block:**

```sql
CREATE TABLE IF NOT EXISTS macro_targets (
    user_id TEXT PRIMARY KEY DEFAULT 'athlete',
    calories INTEGER NOT NULL DEFAULT 2500,
    protein_g REAL NOT NULL DEFAULT 150,
    carbs_g REAL NOT NULL DEFAULT 300,
    fat_g REAL NOT NULL DEFAULT 80,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meal_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    date TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    meal_type TEXT,
    description TEXT NOT NULL,
    total_calories INTEGER NOT NULL,
    total_protein_g REAL NOT NULL,
    total_carbs_g REAL NOT NULL,
    total_fat_g REAL NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    photo_gcs_path TEXT,
    agent_notes TEXT,
    edited_by_user BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_meal_logs_date ON meal_logs(date);
CREATE INDEX IF NOT EXISTS idx_meal_logs_user_date ON meal_logs(user_id, date);

CREATE TABLE IF NOT EXISTS meal_items (
    id SERIAL PRIMARY KEY,
    meal_id INTEGER NOT NULL REFERENCES meal_logs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    serving_size TEXT,
    calories INTEGER NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meal_items_meal_id ON meal_items(meal_id);
```

### 1B. Add `_seed_macro_targets()` to `server/database.py`

**Pattern:** Mirror `_seed_workout_templates()` at `server/database.py:533-550`.

```python
def _seed_macro_targets(conn):
    """Insert default macro targets if table is empty."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM macro_targets")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO macro_targets (user_id, calories, protein_g, carbs_g, fat_g, updated_at) "
            "VALUES ('athlete', 2500, 150, 300, 80, CURRENT_TIMESTAMP)"
        )
    conn.commit()
    cur.close()
```

**Call it from `init_db()`:** Add `_seed_macro_targets(conn)` after `_seed_workout_templates(conn)` at line 499. Reopen a connection or use the existing `conn` — follow the pattern of how `_seed_workout_templates(conn)` is called.

Actually, looking more carefully at `init_db()` (lines 490-530): the `conn` is created at line 492 but closed at line 530. The seed must happen before close. Insert the call at line 500, right after `_seed_workout_templates(conn)`:

```python
_seed_workout_templates(conn)
_seed_macro_targets(conn)    # <-- ADD THIS LINE
```

### 1C. Add query helpers to `server/queries.py`

**Target file:** `server/queries.py`
**Pattern:** Follow the existing functions like `get_current_pmc_row()` (line 48) — take `conn` as first arg, return plain dicts.

**Add these functions at the end of the file:**

```python
def get_meals_for_date(conn, date: str, user_id: str = "athlete") -> list[dict]:
    """Get all meals for a given date, ordered by logged_at."""
    rows = conn.execute(
        "SELECT * FROM meal_logs WHERE date = %s AND user_id = %s ORDER BY logged_at",
        (date, user_id),
    ).fetchall()
    return [dict(r) for r in rows]


def get_meal_items(conn, meal_id: int) -> list[dict]:
    """Get itemized breakdown for a meal."""
    rows = conn.execute(
        "SELECT * FROM meal_items WHERE meal_id = %s ORDER BY id",
        (meal_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_macro_targets(conn, user_id: str = "athlete") -> dict:
    """Get daily macro targets, falling back to defaults if no row exists."""
    row = conn.execute(
        "SELECT * FROM macro_targets WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "calories": 2500,
        "protein_g": 150.0,
        "carbs_g": 300.0,
        "fat_g": 80.0,
    }


def get_daily_meal_totals(conn, date: str, user_id: str = "athlete") -> dict:
    """Get aggregate macro totals for a date."""
    row = conn.execute(
        "SELECT COALESCE(SUM(total_calories), 0) AS calories, "
        "COALESCE(SUM(total_protein_g), 0) AS protein_g, "
        "COALESCE(SUM(total_carbs_g), 0) AS carbs_g, "
        "COALESCE(SUM(total_fat_g), 0) AS fat_g, "
        "COUNT(*) AS meal_count "
        "FROM meal_logs WHERE date = %s AND user_id = %s",
        (date, user_id),
    ).fetchone()
    return dict(row) if row else {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "meal_count": 0}
```

### Verification

```bash
source venv/bin/activate
# Start local Postgres if not running:
podman run -d --name coach-db -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:16-alpine
# Run the app briefly to trigger init_db():
python -c "from server.database import init_db; init_db(); print('Schema OK')"
# Verify tables exist:
PGPASSWORD=dev psql -h localhost -U postgres -d coach -c "\dt meal_*; \dt macro_*"
```

---

## Phase 2: GCS Photo Module

### Target files

Create the module directory and files:
```
server/nutrition/__init__.py   (empty)
server/nutrition/photo.py
```

### `server/nutrition/__init__.py`

Empty file. Just creates the Python package.

### `server/nutrition/photo.py`

```python
"""GCS upload and signed URL helpers for meal photos."""

import io
import os
import uuid
from datetime import datetime, timedelta

from PIL import Image

MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_DIMENSION = 1200
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

MEAL_PHOTO_BUCKET = os.environ.get("MEAL_PHOTO_BUCKET", "jasondel-coach-data")
MEAL_PHOTO_PREFIX = os.environ.get("MEAL_PHOTO_PREFIX", "meals")

_storage_client = None


def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        from google.cloud import storage
        _storage_client = storage.Client()
    return _storage_client


def upload_meal_photo(
    image_bytes: bytes,
    mime_type: str,
    user_id: str = "athlete",
) -> tuple[str, bytes]:
    """Upload a meal photo to GCS after resizing.

    Returns:
        Tuple of (gcs_path, resized_jpeg_bytes) — the resized bytes are needed
        for passing to the agent for analysis.
    """
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported image type: {mime_type}. Allowed: {', '.join(ALLOWED_MIME_TYPES)}")

    if len(image_bytes) > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"Image too large (max {MAX_IMAGE_SIZE_MB}MB)")

    # Resize to max 1200px longest edge
    img = Image.open(io.BytesIO(image_bytes))
    if max(img.size) > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

    # Convert to JPEG 85%
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    resized_bytes = buf.getvalue()

    # Build GCS path
    now = datetime.now()
    short_id = uuid.uuid4().hex[:6]
    blob_name = f"{MEAL_PHOTO_PREFIX}/{user_id}/{now.strftime('%Y%m%d_%H%M%S')}_{short_id}.jpg"
    gcs_path = f"gs://{MEAL_PHOTO_BUCKET}/{blob_name}"

    # Upload
    bucket = _get_storage_client().bucket(MEAL_PHOTO_BUCKET)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(resized_bytes, content_type="image/jpeg")

    return gcs_path, resized_bytes


def generate_photo_url(gcs_path: str, expiry_minutes: int = 60) -> str:
    """Generate a V4 signed URL for a meal photo.

    Args:
        gcs_path: Full GCS path (gs://bucket/path/to/photo.jpg).
        expiry_minutes: URL validity in minutes (default 60).

    Returns:
        HTTPS signed URL, or empty string if gcs_path is empty.
    """
    if not gcs_path:
        return ""

    parts = gcs_path.replace("gs://", "").split("/", 1)
    bucket_name, blob_name = parts[0], parts[1]

    bucket = _get_storage_client().bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expiry_minutes),
        method="GET",
    )
```

### Dependencies

Add to `requirements.txt`:
```
google-cloud-storage>=2.14.0
Pillow>=10.0.0
```

### Verification

```bash
pip install google-cloud-storage Pillow
python -c "from server.nutrition.photo import ALLOWED_MIME_TYPES; print('Photo module OK')"
```

---

## Phase 3: Read-Only Agent Tools

### Target file: `server/nutrition/tools.py`

**Pattern:** Mirror `server/coaching/tools.py`. Each function is a plain Python function with a descriptive docstring (ADK infers the JSON schema from signature + docstring). Functions use `get_db()` context manager from `server/database.py`.

```python
"""Read-only ADK tools for the Nutritionist agent to query meal and training data."""

from datetime import datetime, timedelta
from server.database import get_db, get_all_athlete_settings
from server.queries import get_meals_for_date, get_meal_items, get_macro_targets, get_daily_meal_totals


def get_meal_history(days_back: int = 7) -> list[dict]:
    """Get recent meal history with macros and timestamps.

    Args:
        days_back: Number of days to look back. Default 7.

    Returns:
        List of meal records with date, description, macros, and confidence.
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, date, logged_at, meal_type, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g, "
            "confidence, edited_by_user "
            "FROM meal_logs WHERE date >= %s AND user_id = %s ORDER BY date DESC, logged_at DESC",
            (cutoff, "athlete"),
        ).fetchall()

    return [dict(r) for r in rows]


def get_daily_macros(date: str = "") -> dict:
    """Get the aggregate macronutrient totals for a specific day.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today if empty.

    Returns:
        Daily macro summary including totals, targets, remaining, and per-meal breakdown.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        meals = conn.execute(
            "SELECT id, logged_at, meal_type, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g, confidence "
            "FROM meal_logs WHERE date = %s AND user_id = %s ORDER BY logged_at",
            (date, "athlete"),
        ).fetchall()

        targets = get_macro_targets(conn)

    total_cal = sum(m["total_calories"] for m in meals)
    total_p = sum(m["total_protein_g"] for m in meals)
    total_c = sum(m["total_carbs_g"] for m in meals)
    total_f = sum(m["total_fat_g"] for m in meals)

    return {
        "date": date,
        "total_calories": total_cal,
        "total_protein_g": round(total_p, 1),
        "total_carbs_g": round(total_c, 1),
        "total_fat_g": round(total_f, 1),
        "target_calories": targets["calories"],
        "target_protein_g": targets["protein_g"],
        "target_carbs_g": targets["carbs_g"],
        "target_fat_g": targets["fat_g"],
        "remaining_calories": targets["calories"] - total_cal,
        "remaining_protein_g": round(targets["protein_g"] - total_p, 1),
        "meals": [dict(m) for m in meals],
        "meal_count": len(meals),
    }


def get_weekly_summary(date: str = "") -> dict:
    """Get a 7-day nutrition summary with daily breakdown and weekly averages.

    Args:
        date: Any date in the target week (YYYY-MM-DD). Defaults to today. Week is Mon-Sun.

    Returns:
        Weekly averages and per-day totals.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    dt = datetime.fromisoformat(date)
    start = dt - timedelta(days=dt.weekday())
    end = start + timedelta(days=6)

    days = []
    with get_db() as conn:
        for i in range(7):
            day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            totals = get_daily_meal_totals(conn, day)
            # Get ride calories for this day
            ride_row = conn.execute(
                "SELECT COALESCE(SUM(total_calories), 0) AS ride_cal "
                "FROM rides WHERE date = %s",
                (day,),
            ).fetchone()
            totals["date"] = day
            totals["calories_out_rides"] = int(ride_row["ride_cal"]) if ride_row else 0
            days.append(totals)

    days_with_meals = [d for d in days if d["meal_count"] > 0]
    n = len(days_with_meals) or 1

    return {
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": end.strftime("%Y-%m-%d"),
        "avg_daily_calories": round(sum(d["calories"] for d in days_with_meals) / n),
        "avg_daily_protein_g": round(sum(d["protein_g"] for d in days_with_meals) / n, 1),
        "avg_daily_carbs_g": round(sum(d["carbs_g"] for d in days_with_meals) / n, 1),
        "avg_daily_fat_g": round(sum(d["fat_g"] for d in days_with_meals) / n, 1),
        "days": days,
    }


def get_caloric_balance(date: str = "") -> dict:
    """Get caloric intake vs estimated expenditure for a day.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        Intake, ride expenditure, estimated BMR, total expenditure, and net balance.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        totals = get_daily_meal_totals(conn, date)
        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s",
            (date,),
        ).fetchone()
        ride_cal = int(ride_row["total"]) if ride_row else 0

    bmr = _estimate_daily_bmr()
    total_out = ride_cal + bmr

    return {
        "date": date,
        "intake": int(totals["calories"]),
        "rides": ride_cal,
        "estimated_bmr": bmr,
        "total_expenditure": total_out,
        "net_balance": int(totals["calories"]) - total_out,
    }


def get_macro_targets_tool() -> dict:
    """Get the athlete's current daily macro targets.

    Returns:
        Daily targets for calories, protein, carbs, and fat.
    """
    with get_db() as conn:
        return get_macro_targets(conn)


def get_upcoming_training_load(days_ahead: int = 3) -> dict:
    """Get upcoming planned workouts and training load for fueling guidance.

    Args:
        days_ahead: Number of days to look ahead. Default 3.

    Returns:
        Planned workouts with date, name, TSS, duration, and estimated calories.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, name, total_duration_s, planned_tss, coach_notes "
            "FROM planned_workouts WHERE date >= %s AND date <= %s ORDER BY date",
            (today, end),
        ).fetchall()

    days = []
    for r in rows:
        tss = float(r["planned_tss"] or 0)
        duration_h = (r["total_duration_s"] or 0) / 3600
        # Rough calorie estimate from duration (500-700 kcal/hr for cycling)
        est_cal = round(duration_h * 600) if duration_h > 0 else 0
        days.append({
            "date": r["date"],
            "name": r["name"],
            "planned_tss": round(tss),
            "duration_h": round(duration_h, 1),
            "estimated_calories": est_cal,
            "coach_notes": r["coach_notes"],
        })

    return {
        "days": days,
        "total_planned_tss": sum(d["planned_tss"] for d in days),
        "total_estimated_calories": sum(d["estimated_calories"] for d in days),
    }


def get_recent_workouts(days_back: int = 3) -> list[dict]:
    """Get recent completed ride summaries for nutritional context.

    Args:
        days_back: Number of days to look back. Default 3.

    Returns:
        List of ride summaries with TSS, duration, and calories burned.
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, sub_sport, duration_s, tss, total_calories, "
            "avg_power, normalized_power "
            "FROM rides WHERE date >= %s ORDER BY date DESC",
            (cutoff,),
        ).fetchall()

    return [
        {
            "date": r["date"],
            "sport": r["sub_sport"],
            "duration_h": round((r["duration_s"] or 0) / 3600, 1),
            "tss": r["tss"],
            "calories_burned": r["total_calories"] or 0,
            "avg_power": r["avg_power"],
            "normalized_power": r["normalized_power"],
        }
        for r in rows
    ]


def _estimate_daily_bmr() -> int:
    """Estimate BMR from athlete settings using Mifflin-St Jeor equation."""
    settings = get_all_athlete_settings()
    try:
        weight_kg = float(settings.get("weight_kg", 0))
        age = int(settings.get("age", 0))
        gender = settings.get("gender", "").lower()
    except (ValueError, TypeError):
        return 1750

    if weight_kg <= 0 or age <= 0:
        return 1750

    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * 175 - 5 * age + 5
    elif gender == "female":
        bmr = 10 * weight_kg + 6.25 * 165 - 5 * age - 161
    else:
        bmr = 10 * weight_kg + 6.25 * 170 - 5 * age - 78

    return round(bmr * 1.2)  # Sedentary multiplier; exercise added separately
```

### Verification

```bash
python -c "from server.nutrition.tools import get_meal_history; print('Tools module OK')"
```

---

## Phase 4: Write Tools (Permission-Gated)

### Target file: `server/nutrition/planning_tools.py`

**Pattern:** Mirror `server/coaching/planning_tools.py`. Each function takes structured args, validates, writes to DB, and returns a status dict. Permission gating happens at the agent level (Phase 5), same pattern as `server/coaching/agent.py:76-83`.

```python
"""Write tools for the Nutritionist agent — permission-gated at the agent level."""

from datetime import datetime
from server.database import get_db
from server.logging_config import get_logger

logger = get_logger(__name__)


def save_meal_analysis(
    meal_description: str,
    items: list[dict],
    total_calories: int,
    total_protein_g: float,
    total_carbs_g: float,
    total_fat_g: float,
    confidence: str,
    meal_type: str = "",
    photo_gcs_path: str = "",
    agent_notes: str = "",
) -> dict:
    """Save a meal analysis to the database after photo analysis.

    Call this tool after analyzing a meal photo. Provide the full itemized
    breakdown and macro totals.

    Args:
        meal_description: Brief natural language description (e.g., "Grilled chicken breast with brown rice and steamed broccoli").
        items: List of individual food items. Each dict must have:
            - name (str): Item name
            - serving_size (str): e.g., "6 oz", "1 cup", "200g"
            - calories (int)
            - protein_g (float)
            - carbs_g (float)
            - fat_g (float)
        total_calories: Sum of calories across all items.
        total_protein_g: Sum of protein across all items.
        total_carbs_g: Sum of carbs across all items.
        total_fat_g: Sum of fat across all items.
        confidence: "high", "medium", or "low".
        meal_type: Optional: "breakfast", "lunch", "dinner", "snack".
        photo_gcs_path: GCS path to the stored photo (set by the API layer).
        agent_notes: Optional nutritionist commentary about the meal.

    Returns:
        Saved meal record with id and timestamp.
    """
    # Validation
    if total_calories <= 0 or total_calories > 10000:
        return {"error": f"total_calories must be between 1 and 10000, got {total_calories}"}
    if total_protein_g < 0 or total_carbs_g < 0 or total_fat_g < 0:
        return {"error": "Macro values must be non-negative"}
    if confidence not in ("high", "medium", "low"):
        return {"error": f"confidence must be high/medium/low, got '{confidence}'"}
    if not items:
        return {"error": "items list must not be empty"}

    # Cross-check: macro calories vs total (log warning if >15% off, still save)
    macro_cal = round(total_protein_g * 4 + total_carbs_g * 4 + total_fat_g * 9)
    if total_calories > 0 and abs(macro_cal - total_calories) / total_calories > 0.15:
        logger.warning(
            "macro_calorie_mismatch",
            total_calories=total_calories,
            macro_derived_calories=macro_cal,
            difference_pct=round(abs(macro_cal - total_calories) / total_calories * 100, 1),
        )

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    logged_at = now.isoformat()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO meal_logs (user_id, date, logged_at, meal_type, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g, "
            "confidence, photo_gcs_path, agent_notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            ("athlete", date_str, logged_at, meal_type or None, meal_description,
             total_calories, total_protein_g, total_carbs_g, total_fat_g,
             confidence, photo_gcs_path or None, agent_notes or None),
        )
        row = conn.execute("SELECT lastval()").fetchone()
        meal_id = row[0] if row else None

        # Insert individual items
        for item in items:
            conn.execute(
                "INSERT INTO meal_items (meal_id, name, serving_size, calories, "
                "protein_g, carbs_g, fat_g) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (meal_id, item.get("name", "Unknown"), item.get("serving_size"),
                 item.get("calories", 0), item.get("protein_g", 0),
                 item.get("carbs_g", 0), item.get("fat_g", 0)),
            )

    return {
        "status": "saved",
        "meal_id": meal_id,
        "date": date_str,
        "logged_at": logged_at,
        "description": meal_description,
        "total_calories": total_calories,
        "confidence": confidence,
        "items_count": len(items),
    }


def update_meal(
    meal_id: int,
    total_calories: int = 0,
    total_protein_g: float = 0,
    total_carbs_g: float = 0,
    total_fat_g: float = 0,
    meal_type: str = "",
) -> dict:
    """Update macro values on an existing meal (user corrections).

    Args:
        meal_id: The meal to update.
        total_calories: New calorie total (0 = no change).
        total_protein_g: New protein total (0 = no change).
        total_carbs_g: New carbs total (0 = no change).
        total_fat_g: New fat total (0 = no change).
        meal_type: New meal type (empty = no change).

    Returns:
        Status of the update.
    """
    updates = []
    params = []
    if total_calories > 0:
        updates.append("total_calories = %s")
        params.append(total_calories)
    if total_protein_g > 0:
        updates.append("total_protein_g = %s")
        params.append(total_protein_g)
    if total_carbs_g > 0:
        updates.append("total_carbs_g = %s")
        params.append(total_carbs_g)
    if total_fat_g > 0:
        updates.append("total_fat_g = %s")
        params.append(total_fat_g)
    if meal_type:
        updates.append("meal_type = %s")
        params.append(meal_type)

    if not updates:
        return {"error": "No values to update"}

    updates.append("edited_by_user = TRUE")
    params.append(meal_id)

    with get_db() as conn:
        conn.execute(
            f"UPDATE meal_logs SET {', '.join(updates)} WHERE id = %s",
            params,
        )

    return {"status": "updated", "meal_id": meal_id}


def delete_meal(meal_id: int) -> dict:
    """Delete a meal and its items from the database.

    Args:
        meal_id: The meal to delete.

    Returns:
        Confirmation of deletion.
    """
    with get_db() as conn:
        row = conn.execute("SELECT id, description FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            return {"error": f"Meal {meal_id} not found"}
        # meal_items cascade-deletes via FK
        conn.execute("DELETE FROM meal_logs WHERE id = %s", (meal_id,))

    return {"status": "deleted", "meal_id": meal_id}


def set_macro_targets(
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> dict:
    """Update the athlete's daily macro targets.

    Args:
        calories: Daily calorie target (must be > 0 and < 10000).
        protein_g: Daily protein target in grams (must be >= 0).
        carbs_g: Daily carbs target in grams (must be >= 0).
        fat_g: Daily fat target in grams (must be >= 0).

    Returns:
        Updated targets.
    """
    if calories <= 0 or calories > 10000:
        return {"error": f"calories must be between 1 and 10000, got {calories}"}
    if protein_g < 0 or carbs_g < 0 or fat_g < 0:
        return {"error": "Macro targets must be non-negative"}

    with get_db() as conn:
        conn.execute(
            "INSERT INTO macro_targets (user_id, calories, protein_g, carbs_g, fat_g, updated_at) "
            "VALUES ('athlete', %s, %s, %s, %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "calories = EXCLUDED.calories, protein_g = EXCLUDED.protein_g, "
            "carbs_g = EXCLUDED.carbs_g, fat_g = EXCLUDED.fat_g, "
            "updated_at = EXCLUDED.updated_at",
            (calories, protein_g, carbs_g, fat_g),
        )

    return {
        "status": "updated",
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
    }


def ask_clarification(question: str, context: str = "") -> dict:
    """Request clarification from the user about an ambiguous meal photo.

    Call this when confidence is low and you need more information before saving.
    The question will be displayed to the user as a follow-up prompt.

    Args:
        question: Specific question to ask (e.g., "Is that grilled chicken or tofu?").
        context: What you're uncertain about.

    Returns:
        The question echoed back for display to the user.
    """
    return {
        "status": "clarification_needed",
        "question": question,
        "context": context,
    }
```

### Verification

```bash
python -c "from server.nutrition.planning_tools import save_meal_analysis; print('Planning tools OK')"
```

---

## Phase 5: Nutritionist Agent

### Target file: `server/nutrition/agent.py`

**CRITICAL: Mirror `server/coaching/agent.py` exactly.** Same singleton Runner pattern, same `_permission_gate` wrapping, same `_build_system_instruction` callable pattern, same `chat()` async function structure.

**Key difference from cycling coach (Q1 decision):** The `chat()` function must accept optional `image_data` (bytes) and `image_mime_type` (str) parameters. When provided, it constructs a multimodal `types.Content` with both image and text parts, following the pattern at `server/coaching/agent.py:302-305`.

```python
"""ADK-based Nutritionist agent setup."""

import functools
import time
import threading

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.genai import types

from server.config import GEMINI_MODEL, GCP_PROJECT, GCP_LOCATION
from server.database import get_setting
from server.logging_config import get_logger, get_trace_id
from server.telemetry import get_tracer
from server.coaching.session_service import DbSessionService
from server.coaching.memory_service import DbMemoryService
from server.nutrition.tools import (
    get_meal_history,
    get_daily_macros,
    get_weekly_summary,
    get_caloric_balance,
    get_macro_targets_tool,
    get_upcoming_training_load,
    get_recent_workouts,
)
from server.nutrition.planning_tools import (
    save_meal_analysis,
    update_meal,
    delete_meal,
    set_macro_targets,
    ask_clarification,
)

APP_NAME = "nutrition-coach"

logger = get_logger(__name__)
_tracer = get_tracer(__name__)

# Singleton instances
_session_service = None
_memory_service = None
_runner = None

# Write tools that require readwrite/admin role
_WRITE_TOOLS = {
    save_meal_analysis,
    update_meal,
    delete_meal,
    set_macro_targets,
}

# Thread-local storage for current user role during agent execution
_current_user_role = threading.local()


def _permission_gate(fn):
    """Wrap a write tool to check the caller's role before executing."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        role = getattr(_current_user_role, "role", "admin")
        if role not in ("readwrite", "admin"):
            return {"error": "You don't have write permissions. Ask an administrator to upgrade your access."}
        return fn(*args, **kwargs)
    return wrapper


def _build_system_instruction(ctx) -> str:
    """Build the nutritionist system instruction dynamically from DB state."""
    from datetime import datetime, timedelta
    from server.database import get_all_athlete_settings, get_db
    from server.queries import get_current_pmc_row, get_macro_targets

    settings = get_all_athlete_settings()
    today = datetime.now()
    today_str = today.strftime("%A, %B %d, %Y")
    today_iso = today.strftime("%Y-%m-%d")

    try:
        ftp = float(settings.get("ftp", 0))
    except (ValueError, TypeError):
        ftp = 0.0
    try:
        weight_kg = float(settings.get("weight_kg", 0))
    except (ValueError, TypeError):
        weight_kg = 0.0

    with get_db() as conn:
        pmc = get_current_pmc_row(conn)
        targets = get_macro_targets(conn)

        # Recent meals (last 3 days)
        three_days_ago = (today - timedelta(days=3)).strftime("%Y-%m-%d")
        recent_meals = conn.execute(
            "SELECT date, logged_at, description, total_calories, total_protein_g, "
            "total_carbs_g, total_fat_g FROM meal_logs WHERE date >= %s "
            "AND user_id = %s ORDER BY date DESC, logged_at DESC LIMIT 15",
            (three_days_ago, "athlete"),
        ).fetchall()

        # Recent rides (last 3 days)
        recent_rides = conn.execute(
            "SELECT date, sub_sport, duration_s, tss, total_calories "
            "FROM rides WHERE date >= %s ORDER BY date DESC LIMIT 5",
            (three_days_ago,),
        ).fetchall()

    ctl = round(pmc["ctl"], 1) if pmc and pmc.get("ctl") is not None else "N/A"

    recent_meals_text = "\n".join([
        f"  - {m['date']} {m['logged_at'][-8:-3]}: {m['description']} — "
        f"{m['total_calories']} kcal (P{round(m['total_protein_g'])}g / "
        f"C{round(m['total_carbs_g'])}g / F{round(m['total_fat_g'])}g)"
        for m in recent_meals
    ]) or "  No meals logged recently."

    recent_rides_text = "\n".join([
        f"  - {r['date']}: {r['sub_sport'] or 'ride'}, "
        f"{round((r['duration_s'] or 0) / 3600, 1)}h, "
        f"TSS {r['tss'] or '?'}, {r['total_calories'] or '?'} kcal"
        for r in recent_rides
    ]) or "  No recent rides."

    return f"""You are an expert sports nutritionist working with an endurance cyclist.

TODAY'S DATE: {today_str} ({today_iso})

ATHLETE PROFILE:
- Weight: {weight_kg} kg / FTP: {int(ftp)} W / Current CTL: {ctl}
- Daily targets: {targets['calories']} kcal (P {targets['protein_g']}g / C {targets['carbs_g']}g / F {targets['fat_g']}g)

RECENT MEALS (last 3 days):
{recent_meals_text}

RECENT TRAINING (last 3 days):
{recent_rides_text}

YOUR ROLE:
1. Analyze meal photos and estimate macros accurately
2. Track daily and weekly intake trends
3. Identify patterns (repeated meals, nutrient gaps, timing issues)
4. Provide fueling guidance for upcoming workouts
5. Flag concerning patterns (chronic under-fueling, excessive deficit)

MEAL PHOTO ANALYSIS PROTOCOL:
When you receive a meal photo:
1. IDENTIFY each distinct food item visible
2. ESTIMATE portion sizes using visual cues (plate size, utensils, depth/density)
3. For each item, estimate serving size and macros
4. SUM totals. Assign CONFIDENCE (high/medium/low)
5. If LOW confidence, call ask_clarification before saving
6. If MEDIUM or HIGH, call save_meal_analysis directly
7. Before analyzing, check get_meal_history for similar past meals as baselines

COMMUNICATION STYLE:
- Concise, specific with numbers
- Lead with macro summary, then details
- Don't lecture — this athlete trains seriously
- Reference specific numbers from history when making recommendations"""


def _get_effective_model() -> str:
    """Return the Gemini model, preferring DB setting over env var default."""
    db_model = get_setting("gemini_model")
    return db_model if db_model else GEMINI_MODEL


def reset_runner():
    """Reset cached runner so the next chat() picks up new settings."""
    global _runner, _session_service, _memory_service
    _runner = None
    _session_service = None
    _memory_service = None


def _get_agent():
    tools = [
        get_meal_history,
        get_daily_macros,
        get_weekly_summary,
        get_caloric_balance,
        get_macro_targets_tool,
        get_upcoming_training_load,
        get_recent_workouts,
        ask_clarification,
    ]
    for fn in _WRITE_TOOLS:
        tools.append(_permission_gate(fn))

    return Agent(
        name="nutritionist",
        model=_get_effective_model(),
        description="Sports nutritionist specializing in endurance athlete fueling",
        instruction=_build_system_instruction,
        tools=tools,
    )


def get_runner():
    global _session_service, _runner, _memory_service
    if _runner is None:
        _session_service = DbSessionService()
        _memory_service = DbMemoryService()
        _runner = Runner(
            agent=_get_agent(),
            app_name=APP_NAME,
            session_service=_session_service,
            memory_service=_memory_service,
        )
    return _runner, _session_service, _memory_service


async def chat(
    message: str,
    user_id: str = "athlete",
    session_id: str = "default",
    user=None,
    image_data: bytes | None = None,
    image_mime_type: str | None = None,
    photo_gcs_path: str = "",
) -> str:
    """Send a message (optionally with an image) to the nutritionist agent.

    When image_data is provided, constructs a multimodal Content with both
    image and text parts — the agent sees the photo directly via Gemini's
    vision capability.
    """
    import os

    trace_id = get_trace_id()
    t0 = time.monotonic()

    logger.info(
        "nutritionist_chat_start",
        session_id=session_id,
        user_id=user_id,
        user_role=user.role if user else "admin",
        message_len=len(message),
        has_image=image_data is not None,
        trace_id=trace_id,
    )

    # Auth config — same pattern as server/coaching/agent.py:270-283
    db_api_key = get_setting("gemini_api_key")
    db_location = get_setting("gcp_location")

    if db_api_key:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
        os.environ["GOOGLE_API_KEY"] = db_api_key
    else:
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT)

    effective_location = db_location if db_location else GCP_LOCATION
    os.environ["GOOGLE_CLOUD_LOCATION"] = effective_location

    if user is not None:
        _current_user_role.role = user.role
    else:
        _current_user_role.role = "admin"

    runner, session_service, memory_service = get_runner()

    # Ensure session exists
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    # Build Content — multimodal if image provided (Q1 decision: YES)
    parts = []
    if image_data and image_mime_type:
        parts.append(types.Part.from_image(
            image=types.Image.from_bytes(data=image_data, mime_type=image_mime_type)
        ))
        # Inject photo_gcs_path context so save_meal_analysis knows where the photo is
        if photo_gcs_path:
            message = f"[Photo stored at: {photo_gcs_path}]\n{message}"

    parts.append(types.Part.from_text(text=message))

    content = types.Content(role="user", parts=parts)

    response_text = ""
    tool_calls: list[str] = []

    with _tracer.start_as_current_span("nutritionist.chat") as chat_span:
        chat_span.set_attribute("session_id", session_id)
        chat_span.set_attribute("user_id", user_id)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fn_name = part.function_call.name
                        tool_calls.append(fn_name)
                        with _tracer.start_as_current_span("nutritionist.tool_call") as tool_span:
                            tool_span.set_attribute("tool_name", fn_name)
                        logger.debug("nutritionist_tool_call", tool=fn_name, session_id=session_id, trace_id=trace_id)
                    elif hasattr(part, "function_response") and part.function_response:
                        logger.debug("nutritionist_tool_response", tool=part.function_response.name, session_id=session_id, trace_id=trace_id)
                    elif part.text and event.author == "nutritionist":
                        response_text += part.text

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "nutritionist_chat_complete",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        latency_ms=round(elapsed_ms, 1),
        tool_calls=tool_calls,
        tool_call_count=len(tool_calls),
        response_len=len(response_text),
        success=bool(response_text),
    )

    # Save session to long-term memory
    updated_session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if updated_session:
        await memory_service.add_session_to_memory(updated_session)

    return response_text or "I couldn't generate a response. Please try again."
```

### Verification

```bash
python -c "from server.nutrition.agent import APP_NAME; print(f'Nutritionist agent module OK, app_name={APP_NAME}')"
```

---

## Phase 6: Pydantic Schemas

### Target file: `server/models/schemas.py`

**Pattern:** Follow the existing schema definitions (e.g., `RideSummary` at line 7, `ChatRequest` at line 155).

**Add at the end of the file:**

```python
# --- Nutrition Schemas ---

class MealItem(BaseModel):
    id: Optional[int] = None
    name: str
    serving_size: Optional[str] = None
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float


class MealSummary(BaseModel):
    id: int
    date: str
    logged_at: str
    meal_type: Optional[str] = None
    description: str
    total_calories: int
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    confidence: str
    photo_url: Optional[str] = None
    edited_by_user: bool = False


class MealDetail(MealSummary):
    items: list[MealItem] = []
    agent_notes: Optional[str] = None


class MacroTargets(BaseModel):
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    updated_at: Optional[str] = None


class DailyNutritionSummary(BaseModel):
    date: str
    total_calories_in: int
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    meal_count: int
    target_calories: int
    target_protein_g: float
    target_carbs_g: float
    target_fat_g: float
    remaining_calories: int
    calories_out: dict
    net_caloric_balance: int


class MealUpdateRequest(BaseModel):
    total_calories: Optional[int] = None
    total_protein_g: Optional[float] = None
    total_carbs_g: Optional[float] = None
    total_fat_g: Optional[float] = None
    meal_type: Optional[str] = None
    items: Optional[list[MealItem]] = None


class NutritionChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    image_data: Optional[str] = None
    image_mime_type: Optional[str] = None


class NutritionChatResponse(BaseModel):
    response: str
    session_id: str
```

### Verification

```bash
python -c "from server.models.schemas import MealDetail, NutritionChatRequest; print('Nutrition schemas OK')"
```

---

## Phase 7: Nutrition Router

### Target file: `server/routers/nutrition.py` (new file)

**Pattern:** Mirror `server/routers/coaching.py` exactly — same imports, same auth dependencies, same response model usage. Refer to `server/routers/coaching.py:1-28` for the chat endpoint pattern, and lines 31-88 for session CRUD.

```python
"""Nutrition meal logging and Nutritionist chat endpoints."""

import uuid
import base64
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException

from server.auth import CurrentUser, require_read, require_write
from server.models.schemas import (
    MealSummary, MealDetail, MealItem, MacroTargets,
    DailyNutritionSummary, MealUpdateRequest,
    NutritionChatRequest, NutritionChatResponse,
    SessionSummary, SessionDetail, SessionMessage,
)
from server.database import get_db
from server.queries import get_meals_for_date, get_meal_items, get_macro_targets, get_daily_meal_totals
from server.nutrition.photo import upload_meal_photo, generate_photo_url

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


# ---------------------------------------------------------------------------
# Meal CRUD
# ---------------------------------------------------------------------------

@router.post("/meals", status_code=201)
async def create_meal(
    file: UploadFile = File(...),
    comment: str = Form(""),
    meal_type: str = Form(""),
    user: CurrentUser = Depends(require_write),
):
    """Analyze and log a meal photo. Primary entry point for meal logging."""
    from server.nutrition.agent import chat as nutrition_chat

    # Validate file
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, f"Unsupported image type: {file.content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 10MB)")

    # Upload to GCS and get resized bytes for agent
    gcs_path, resized_bytes = upload_meal_photo(image_bytes, file.content_type)

    # Send to nutritionist agent for analysis
    prompt = comment or "Analyze this meal and estimate its macros."
    if meal_type:
        prompt += f" This is a {meal_type} meal."

    session_id = str(uuid.uuid4())
    response_text = await nutrition_chat(
        message=prompt,
        user_id=user.email if hasattr(user, "email") else "athlete",
        session_id=session_id,
        user=user,
        image_data=resized_bytes,
        image_mime_type="image/jpeg",
        photo_gcs_path=gcs_path,
    )

    # The agent should have called save_meal_analysis tool.
    # Fetch the most recent meal to return it.
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM meal_logs WHERE photo_gcs_path = %s ORDER BY id DESC LIMIT 1",
            (gcs_path,),
        ).fetchone()

        if not row:
            # Agent didn't save — return the response text as a fallback
            return {"status": "analysis_only", "response": response_text, "photo_url": generate_photo_url(gcs_path)}

        meal = dict(row)
        items = get_meal_items(conn, meal["id"])

    meal["photo_url"] = generate_photo_url(gcs_path)
    meal["items"] = items

    return meal


@router.get("/meals")
async def list_meals(
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(require_read),
):
    """List meals with optional date range filter."""
    with get_db() as conn:
        query = "SELECT * FROM meal_logs WHERE user_id = %s"
        params: list = ["athlete"]

        if start_date:
            query += " AND date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND date <= %s"
            params.append(end_date)

        # Get total count
        count_row = conn.execute(
            query.replace("SELECT *", "SELECT COUNT(*) AS total"), params
        ).fetchone()
        total = count_row["total"] if count_row else 0

        query += " ORDER BY date DESC, logged_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()

    meals = []
    for r in rows:
        m = dict(r)
        m["photo_url"] = generate_photo_url(m.get("photo_gcs_path", ""))
        meals.append(m)

    return {"meals": meals, "total": total, "limit": limit, "offset": offset}


@router.get("/meals/{meal_id}")
async def get_meal(meal_id: int, user: CurrentUser = Depends(require_read)):
    """Get a single meal with its itemized breakdown."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal not found")
        items = get_meal_items(conn, meal_id)

    meal = dict(row)
    meal["photo_url"] = generate_photo_url(meal.get("photo_gcs_path", ""))
    meal["items"] = items
    return meal


@router.put("/meals/{meal_id}")
async def update_meal_endpoint(
    meal_id: int,
    req: MealUpdateRequest,
    user: CurrentUser = Depends(require_write),
):
    """Update a meal's macro values (user edits after AI analysis)."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal not found")

        updates = []
        params = []
        if req.total_calories is not None:
            updates.append("total_calories = %s")
            params.append(req.total_calories)
        if req.total_protein_g is not None:
            updates.append("total_protein_g = %s")
            params.append(req.total_protein_g)
        if req.total_carbs_g is not None:
            updates.append("total_carbs_g = %s")
            params.append(req.total_carbs_g)
        if req.total_fat_g is not None:
            updates.append("total_fat_g = %s")
            params.append(req.total_fat_g)
        if req.meal_type is not None:
            updates.append("meal_type = %s")
            params.append(req.meal_type)

        if updates:
            updates.append("edited_by_user = TRUE")
            params.append(meal_id)
            conn.execute(f"UPDATE meal_logs SET {', '.join(updates)} WHERE id = %s", params)

        # Replace items if provided
        if req.items is not None:
            conn.execute("DELETE FROM meal_items WHERE meal_id = %s", (meal_id,))
            for item in req.items:
                conn.execute(
                    "INSERT INTO meal_items (meal_id, name, serving_size, calories, "
                    "protein_g, carbs_g, fat_g) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (meal_id, item.name, item.serving_size, item.calories,
                     item.protein_g, item.carbs_g, item.fat_g),
                )

    return {"status": "updated", "meal_id": meal_id}


@router.delete("/meals/{meal_id}")
async def delete_meal_endpoint(meal_id: int, user: CurrentUser = Depends(require_write)):
    """Delete a meal and its items."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal not found")
        conn.execute("DELETE FROM meal_logs WHERE id = %s", (meal_id,))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Daily / Weekly Summaries
# ---------------------------------------------------------------------------

@router.get("/daily-summary")
async def daily_summary(date: str = "", user: CurrentUser = Depends(require_read)):
    """Get aggregated macros and caloric balance for a date."""
    from datetime import datetime
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        totals = get_daily_meal_totals(conn, date)
        targets = get_macro_targets(conn)

        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s",
            (date,),
        ).fetchone()
        ride_cal = int(ride_row["total"]) if ride_row else 0

    from server.nutrition.tools import _estimate_daily_bmr
    bmr = _estimate_daily_bmr()
    total_out = ride_cal + bmr
    cal_in = int(totals["calories"])

    return {
        "date": date,
        "total_calories_in": cal_in,
        "total_protein_g": round(float(totals["protein_g"]), 1),
        "total_carbs_g": round(float(totals["carbs_g"]), 1),
        "total_fat_g": round(float(totals["fat_g"]), 1),
        "meal_count": int(totals["meal_count"]),
        "target_calories": targets["calories"],
        "target_protein_g": targets["protein_g"],
        "target_carbs_g": targets["carbs_g"],
        "target_fat_g": targets["fat_g"],
        "remaining_calories": targets["calories"] - cal_in,
        "calories_out": {"rides": ride_cal, "estimated_bmr": bmr, "total": total_out},
        "net_caloric_balance": cal_in - total_out,
    }


@router.get("/weekly-summary")
async def weekly_summary_endpoint(date: str = "", user: CurrentUser = Depends(require_read)):
    """Get 7-day breakdown with daily totals and weekly averages."""
    from server.nutrition.tools import get_weekly_summary
    return get_weekly_summary(date)


# ---------------------------------------------------------------------------
# Macro Targets
# ---------------------------------------------------------------------------

@router.get("/targets")
async def get_targets(user: CurrentUser = Depends(require_read)):
    """Get current daily macro targets."""
    with get_db() as conn:
        return get_macro_targets(conn)


@router.put("/targets")
async def update_targets(req: MacroTargets, user: CurrentUser = Depends(require_write)):
    """Update daily macro targets."""
    if req.calories <= 0 or req.calories > 10000:
        raise HTTPException(400, "calories must be between 1 and 10000")
    if req.protein_g < 0 or req.carbs_g < 0 or req.fat_g < 0:
        raise HTTPException(400, "Macro targets must be non-negative")

    with get_db() as conn:
        conn.execute(
            "INSERT INTO macro_targets (user_id, calories, protein_g, carbs_g, fat_g, updated_at) "
            "VALUES ('athlete', %s, %s, %s, %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "calories = EXCLUDED.calories, protein_g = EXCLUDED.protein_g, "
            "carbs_g = EXCLUDED.carbs_g, fat_g = EXCLUDED.fat_g, "
            "updated_at = EXCLUDED.updated_at",
            (req.calories, req.protein_g, req.carbs_g, req.fat_g),
        )
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Nutritionist Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=NutritionChatResponse)
async def nutrition_chat_endpoint(req: NutritionChatRequest, user: CurrentUser = Depends(require_read)):
    """Send a message to the nutritionist agent."""
    from server.nutrition.agent import chat as nutrition_chat

    session_id = req.session_id or str(uuid.uuid4())

    # Decode base64 image if provided
    image_bytes = None
    if req.image_data:
        image_bytes = base64.b64decode(req.image_data)

    response = await nutrition_chat(
        message=req.message,
        session_id=session_id,
        user=user,
        image_data=image_bytes,
        image_mime_type=req.image_mime_type,
    )

    return NutritionChatResponse(response=response, session_id=session_id)


# ---------------------------------------------------------------------------
# Nutritionist Sessions — same pattern as server/routers/coaching.py:31-88
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=list[SessionSummary])
async def list_nutrition_sessions(user: CurrentUser = Depends(require_read)):
    """List nutritionist chat sessions."""
    with get_db() as conn:
        # ADK stores sessions with app_name; filter by our app
        # The DbSessionService uses chat_sessions table
        rows = conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions "
            "WHERE session_id LIKE %s ORDER BY updated_at DESC",
            ("nutrition-%",),
        ).fetchall()

    return [
        SessionSummary(
            session_id=r["session_id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_nutrition_session(session_id: str, user: CurrentUser = Depends(require_read)):
    """Get a nutritionist session with messages."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()

        if not row:
            raise HTTPException(404, "Session not found")

        events = conn.execute(
            "SELECT author, role, content_text, timestamp FROM chat_events "
            "WHERE session_id = %s ORDER BY id",
            (session_id,),
        ).fetchall()

    return SessionDetail(
        session_id=row["session_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        messages=[
            SessionMessage(
                author=e["author"], role=e["role"],
                content_text=e["content_text"], timestamp=e["timestamp"],
            )
            for e in events
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_nutrition_session(session_id: str, user: CurrentUser = Depends(require_write)):
    """Delete a nutritionist session."""
    with get_db() as conn:
        conn.execute("DELETE FROM chat_events WHERE session_id = %s", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
    return {"status": "deleted"}
```

### Verification

```bash
python -c "from server.routers.nutrition import router; print(f'Nutrition router OK, prefix={router.prefix}')"
```

---

## Phase 8: Coaching Integration

### 8A. Add `get_athlete_nutrition_status` to `server/coaching/tools.py`

**Location:** Add at the end of `server/coaching/tools.py` (after the `get_planned_workout_for_ride` function ending at line 749).

```python
def get_athlete_nutrition_status(date: str = "") -> dict:
    """Get the athlete's nutritional intake summary for fueling decisions.

    Use this to check if the athlete has eaten enough before or after training.
    For detailed nutritional guidance, delegate to the nutritionist agent.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        Caloric intake, macro breakdown, meal count, caloric balance,
        and last meal timestamp for the specified day.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        meals = conn.execute(
            "SELECT total_calories, total_protein_g, total_carbs_g, "
            "total_fat_g, logged_at, description "
            "FROM meal_logs WHERE date = %s AND user_id = %s ORDER BY logged_at DESC",
            (date, "athlete"),
        ).fetchall()

        # Ride calories
        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s",
            (date,),
        ).fetchone()
        ride_cal = int(ride_row["total"]) if ride_row else 0

        # Targets
        targets_row = conn.execute(
            "SELECT calories, protein_g, carbs_g, fat_g FROM macro_targets WHERE user_id = %s",
            ("athlete",),
        ).fetchone()

    total_cal = sum(m["total_calories"] for m in meals)
    total_p = sum(m["total_protein_g"] for m in meals)
    total_c = sum(m["total_carbs_g"] for m in meals)
    total_f = sum(m["total_fat_g"] for m in meals)

    target_cal = targets_row["calories"] if targets_row else 2500

    # BMR estimate
    from server.nutrition.tools import _estimate_daily_bmr
    bmr = _estimate_daily_bmr()

    return {
        "date": date,
        "meals_logged": len(meals),
        "total_calories": total_cal,
        "total_protein_g": round(total_p, 1),
        "total_carbs_g": round(total_c, 1),
        "total_fat_g": round(total_f, 1),
        "target_calories": target_cal,
        "remaining_calories": target_cal - total_cal,
        "last_meal_at": meals[0]["logged_at"] if meals else None,
        "last_meal_description": meals[0]["description"] if meals else None,
        "caloric_balance": {
            "intake": total_cal,
            "rides": ride_cal,
            "estimated_bmr": bmr,
            "net_balance": total_cal - ride_cal - bmr,
        },
    }
```

### 8B. Register in `server/coaching/agent.py`

**Add import** at line 31 (after the existing tool imports):
```python
from server.coaching.tools import (
    # ... existing imports ...
    get_athlete_nutrition_status,
)
```

**Add to the tools list** in `_get_agent()` at line 226 (inside the `tools = [...]` list):
```python
    get_athlete_nutrition_status,
```

### Verification

```bash
python -c "from server.coaching.tools import get_athlete_nutrition_status; print('Coaching integration OK')"
```

---

## Phase 9: App Wiring

### Target file: `server/main.py`

**Add import** at line 29, alongside existing router imports:
```python
from server.routers import rides, pmc, analysis, planning, coaching, sync, athlete, admin, nutrition
```

**Add router registration** at line 218, after `app.include_router(admin.router)`:
```python
app.include_router(nutrition.router)
```

### Verification

```bash
python -c "from server.main import app; routes = [r.path for r in app.routes]; print('Nutrition routes:', [r for r in routes if 'nutrition' in r])"
```

---

## Phase 10: Tests

### Unit Tests: `tests/unit/test_nutrition_tools.py`

Test the pure logic functions (BMR estimation, macro cross-check, validation).

```python
"""Unit tests for nutrition tool logic."""

def test_estimate_daily_bmr_defaults():
    """BMR returns 1750 when athlete settings are incomplete."""
    from server.nutrition.tools import _estimate_daily_bmr
    # With no DB, this will use defaults (weight_kg=0) -> 1750
    result = _estimate_daily_bmr()
    assert result == 1750


def test_photo_validation():
    """Photo module rejects invalid MIME types."""
    from server.nutrition.photo import ALLOWED_MIME_TYPES
    assert "image/jpeg" in ALLOWED_MIME_TYPES
    assert "image/gif" not in ALLOWED_MIME_TYPES


def test_save_meal_validation():
    """save_meal_analysis rejects invalid inputs."""
    from server.nutrition.planning_tools import save_meal_analysis
    # Calories out of range
    result = save_meal_analysis("test", [{"name": "x"}], 0, 10, 10, 10, "high")
    assert "error" in result
    # Invalid confidence
    result = save_meal_analysis("test", [{"name": "x"}], 500, 10, 10, 10, "unknown")
    assert "error" in result
    # Empty items
    result = save_meal_analysis("test", [], 500, 10, 10, 10, "high")
    assert "error" in result
```

### Integration Tests: `tests/integration/test_nutrition_api.py`

Follow patterns in `tests/integration/conftest.py`. Use the `client` and `db_conn` fixtures. Do NOT call `init_db()`. Do NOT use TRUNCATE.

```python
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


def test_daily_summary_empty(client):
    """GET /api/nutrition/daily-summary works with no meals."""
    r = client.get("/api/nutrition/daily-summary?date=2026-01-01")
    assert r.status_code == 200
    data = r.json()
    assert data["total_calories_in"] == 0
    assert data["meal_count"] == 0


def test_list_meals_empty(client):
    """GET /api/nutrition/meals returns empty list initially."""
    r = client.get("/api/nutrition/meals")
    assert r.status_code == 200
    data = r.json()
    assert data["meals"] == []
    assert data["total"] == 0


def test_meal_not_found(client):
    """GET /api/nutrition/meals/999999 returns 404."""
    r = client.get("/api/nutrition/meals/999999")
    assert r.status_code == 404
```

### Run commands

```bash
# Unit tests only (no DB needed)
pytest tests/unit/test_nutrition_tools.py -v

# Integration tests (needs test DB)
./scripts/run_integration_tests.sh -v tests/integration/test_nutrition_api.py
```
