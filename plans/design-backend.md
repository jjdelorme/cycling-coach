# Macro Tracker — Backend Architecture Proposal
> **Version target:** v1.9.x

## 1. Overview

This document specifies the backend architecture for the Macro Tracker feature: data model, API endpoints, GCS photo storage, calorie burn integration, AI coaching context, and migration strategy. It is designed to integrate cleanly with the existing FastAPI/PostgreSQL/psycopg2 stack and follows established patterns from `server/routers/`, `server/database.py`, and `server/coaching/`.

Key architectural decisions:
- **Three new PostgreSQL tables** (`meal_logs`, `meal_items`, `macro_targets`) added via the existing `init_db()` migration pattern
- **GCS photo storage** using the existing `gs://jasondel-coach-data` bucket with a new `meals/` prefix and signed URLs for frontend access
- **New `/api/nutrition` router** following the existing `APIRouter` + auth dependency pattern
- **Calorie burn derived from existing `rides.total_calories`** plus BMR estimate from athlete settings — no new data ingestion needed
- **Nutritionist agent tools** query the new tables directly; the cycling coach gets a lightweight cross-domain data accessor

---

## 2. Data Model

### 2.1 New Tables — DDL

These tables are added to the `_SCHEMA` string in `server/database.py`, following the existing `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` pattern.

```sql
-- Daily macro targets (configurable per user)
CREATE TABLE IF NOT EXISTS macro_targets (
    user_id TEXT PRIMARY KEY DEFAULT 'athlete',
    calories INTEGER NOT NULL DEFAULT 2500,
    protein_g REAL NOT NULL DEFAULT 150,
    carbs_g REAL NOT NULL DEFAULT 300,
    fat_g REAL NOT NULL DEFAULT 80,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Individual meal logs
CREATE TABLE IF NOT EXISTS meal_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    date TEXT NOT NULL,                          -- YYYY-MM-DD, matches rides.date format
    logged_at TEXT NOT NULL,                     -- ISO 8601 timestamp
    meal_type TEXT,                              -- breakfast, lunch, dinner, snack
    description TEXT NOT NULL,                   -- AI-generated natural language description
    total_calories INTEGER NOT NULL,
    total_protein_g REAL NOT NULL,
    total_carbs_g REAL NOT NULL,
    total_fat_g REAL NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',   -- high, medium, low
    photo_gcs_path TEXT,                         -- gs://jasondel-coach-data/meals/{user_id}/{timestamp}.jpg
    agent_notes TEXT,                            -- nutritionist commentary/context
    edited_by_user BOOLEAN DEFAULT FALSE         -- true if user manually corrected macros
);

CREATE INDEX IF NOT EXISTS idx_meal_logs_date ON meal_logs(date);
CREATE INDEX IF NOT EXISTS idx_meal_logs_user_date ON meal_logs(user_id, date);

-- Individual food items within a meal (child of meal_logs)
CREATE TABLE IF NOT EXISTS meal_items (
    id SERIAL PRIMARY KEY,
    meal_id INTEGER NOT NULL REFERENCES meal_logs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    serving_size TEXT,                           -- e.g., "6 oz", "1 cup", "200g"
    calories INTEGER NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meal_items_meal_id ON meal_items(meal_id);
```

### 2.2 Design Notes

**Date format**: `meal_logs.date` uses `TEXT` in `YYYY-MM-DD` format, matching the existing `rides.date` and `daily_metrics.date` convention. This keeps joins and comparisons simple across tables.

**`logged_at` vs `date`**: `date` is the calendar day (for aggregation and display), `logged_at` is the precise ISO 8601 timestamp (for ordering meals within a day). This mirrors how `rides.date` and `rides.start_time` serve different purposes.

**`user_id` default**: Defaults to `'athlete'` matching the existing single-user-with-roles pattern (see `coach_memory.user_id`, `chat_sessions.user_id`). Ready for multi-athlete if that's ever needed — just change the default and add the FK.

**`ON DELETE CASCADE`**: `meal_items` cascade-deletes when the parent `meal_logs` row is deleted. This avoids orphan items and matches the expectation that deleting a meal deletes its itemized breakdown.

**No `voice_note_gcs_path` column**: The feature spec mentions optional voice comments. These are transcribed before reaching the backend and sent as the text `comment` parameter alongside the photo. No raw audio storage is needed — the transcription is context for the AI analysis, not a persistent artifact. If raw audio storage is later needed, add the column then.

### 2.3 Relationship to Existing Tables

```
users.email ──────────────── meal_logs.user_id (logical, not FK — matches existing pattern)
                             meal_logs.date ──── daily_metrics.date (join for calorie balance)
                             meal_logs.date ──── rides.date (join for calories out)
meal_logs.id ─── FK ──────── meal_items.meal_id
macro_targets.user_id ────── (standalone config, one row per user)
```

No foreign keys to `users` — this matches the existing pattern where `coach_memory`, `chat_sessions`, etc. use `user_id TEXT` without a formal FK constraint.

---

## 3. Photo Storage — GCS Strategy

### 3.1 Bucket and Path Convention

Use the existing bucket `gs://jasondel-coach-data` with a new path prefix:

```
gs://jasondel-coach-data/
├── fit/           ← existing ride FIT files
├── json/          ← existing ride JSON files
├── planned_workouts/
└── meals/         ← NEW
    └── {user_id}/
        └── {YYYYMMDD}_{HHmmss}_{uuid_short}.jpg
```

**Path example**: `gs://jasondel-coach-data/meals/athlete/20260409_123456_a1b2c3.jpg`

**Why reuse the existing bucket?**
- No new infrastructure to provision
- Same service account permissions already in place
- Same lifecycle policies can be applied
- Consistent with the project's GCS data strategy

### 3.2 Upload Flow

The backend handles uploads — the frontend never writes to GCS directly. This keeps credentials server-side and allows the backend to resize/validate before storage.

```
Frontend                        Backend                          GCS
   │                               │                               │
   │  POST /api/nutrition/meals    │                               │
   │  (multipart: image + comment) │                               │
   │ ──────────────────────────────>│                               │
   │                               │  1. Validate image (type, size)│
   │                               │  2. Resize to max 1200px      │
   │                               │  3. Upload to GCS             │
   │                               │ ─────────────────────────────>│
   │                               │  4. Store meal_log with       │
   │                               │     photo_gcs_path            │
   │                               │  5. Send to nutritionist agent│
   │                               │  6. Agent calls save_meal     │
   │                               │     tool → inserts items      │
   │  { meal_id, macros, photo_url}│                               │
   │ <──────────────────────────────│                               │
```

### 3.3 Photo Retrieval — Signed URLs

The frontend needs to display meal photos. Since the GCS bucket is private, the backend generates short-lived signed URLs.

```python
from google.cloud import storage
from datetime import timedelta

_storage_client = None

def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client

def generate_photo_url(gcs_path: str, expiry_minutes: int = 60) -> str:
    """Generate a signed URL for a meal photo.

    Args:
        gcs_path: Full GCS path (gs://bucket/path/to/photo.jpg)
        expiry_minutes: URL validity in minutes (default 60).

    Returns:
        HTTPS signed URL.
    """
    if not gcs_path:
        return ""
    # Parse gs://bucket/path
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

**Why signed URLs over a proxy endpoint?**
- No backend CPU/memory spent streaming image bytes
- GCS serves the image directly with CDN-like performance
- 60-minute expiry is sufficient for a session — photos are re-fetched on page load
- Simpler implementation; no streaming route needed

**Tradeoff**: Signed URLs expire, so cached images in the browser will 404 after the TTL. The frontend handles this by re-requesting the meal list (which regenerates URLs) on visibility change or pull-to-refresh. This is acceptable for meal photos that aren't referenced offline.

### 3.4 Upload Implementation

```python
import uuid
from datetime import datetime
from PIL import Image
import io

MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_DIMENSION = 1200
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

def upload_meal_photo(
    image_bytes: bytes,
    mime_type: str,
    user_id: str = "athlete",
) -> str:
    """Upload a meal photo to GCS, returning the gs:// path.

    Resizes to max 1200px on the longest edge before upload.
    """
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported image type: {mime_type}")

    if len(image_bytes) > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"Image too large (max {MAX_IMAGE_SIZE_MB}MB)")

    # Resize
    img = Image.open(io.BytesIO(image_bytes))
    if max(img.size) > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    resized_bytes = buf.getvalue()

    # Build path
    now = datetime.now()
    short_id = uuid.uuid4().hex[:6]
    blob_name = f"meals/{user_id}/{now.strftime('%Y%m%d_%H%M%S')}_{short_id}.jpg"
    gcs_path = f"gs://jasondel-coach-data/{blob_name}"

    # Upload
    bucket = _get_storage_client().bucket("jasondel-coach-data")
    blob = bucket.blob(blob_name)
    blob.upload_from_string(resized_bytes, content_type="image/jpeg")

    return gcs_path
```

### 3.5 Lifecycle Policies

No automatic deletion — meal photos are persistent training records. The `meals/` prefix keeps them organized for potential future cleanup. Storage cost is negligible: at ~100KB per resized photo, 10 meals/day = ~1MB/day = ~365MB/year.

---

## 4. API Endpoints

### 4.1 New Router: `server/routers/nutrition.py`

Mounted as `app.include_router(nutrition.router)` in `server/main.py`, following the existing pattern.

```python
router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])
```

### 4.2 Endpoint Specification

#### Meal Photo Analysis (Primary Flow)

```
POST /api/nutrition/meals
```

Upload a meal photo for AI analysis and storage. This is the primary entry point — it handles photo upload, GCS storage, agent analysis, and DB persistence in a single request.

- **Auth**: `require_write`
- **Content-Type**: `multipart/form-data`
- **Request**:
  | Field | Type | Required | Description |
  |-------|------|----------|-------------|
  | `file` | `UploadFile` | Yes | Meal photo (JPEG, PNG, WebP, max 10MB) |
  | `comment` | `str (Form)` | No | Optional text context ("about 6oz of chicken") |
  | `meal_type` | `str (Form)` | No | "breakfast", "lunch", "dinner", "snack" |

- **Response** (201 Created):
```json
{
  "meal_id": 42,
  "date": "2026-04-09",
  "logged_at": "2026-04-09T12:34:56",
  "meal_type": "lunch",
  "description": "Grilled chicken breast with brown rice and steamed broccoli",
  "total_calories": 487,
  "total_protein_g": 38.2,
  "total_carbs_g": 42.5,
  "total_fat_g": 18.1,
  "confidence": "high",
  "photo_url": "https://storage.googleapis.com/...(signed URL)...",
  "items": [
    {
      "id": 101,
      "name": "Grilled chicken breast",
      "serving_size": "6 oz",
      "calories": 280,
      "protein_g": 32.0,
      "carbs_g": 0.0,
      "fat_g": 12.0
    },
    {
      "id": 102,
      "name": "Brown rice",
      "serving_size": "1 cup",
      "calories": 150,
      "protein_g": 3.5,
      "carbs_g": 32.0,
      "fat_g": 1.5
    },
    {
      "id": 103,
      "name": "Steamed broccoli",
      "serving_size": "1 cup",
      "calories": 57,
      "protein_g": 2.7,
      "carbs_g": 10.5,
      "fat_g": 4.6
    }
  ],
  "agent_notes": "Solid post-ride meal. Good protein-to-carb ratio for recovery."
}
```

**Implementation flow**:
1. Validate and resize image
2. Upload to GCS → get `gcs_path`
3. Insert a placeholder `meal_logs` row (with photo path, no macros yet)
4. Send image + comment to nutritionist agent via `runner.run_async()`
5. Agent analyzes and calls `save_meal_analysis` tool → updates the row with macros, inserts `meal_items`
6. Return the completed meal record with signed photo URL

**Why a single endpoint rather than upload + poll?** The analysis takes 3-8 seconds — short enough for a synchronous HTTP response. The frontend shows a loading state during this time. If latency becomes a problem at scale, this can be converted to async (see Section 8.2).

---

#### Meal CRUD

```
GET /api/nutrition/meals
```

List meals with optional date range filter.

- **Auth**: `require_read`
- **Query params**:
  | Param | Type | Default | Description |
  |-------|------|---------|-------------|
  | `start_date` | `str` | None | YYYY-MM-DD lower bound |
  | `end_date` | `str` | None | YYYY-MM-DD upper bound |
  | `limit` | `int` | 50 | Max results |
  | `offset` | `int` | 0 | Pagination offset |

- **Response**:
```json
{
  "meals": [
    {
      "id": 42,
      "date": "2026-04-09",
      "logged_at": "2026-04-09T12:34:56",
      "meal_type": "lunch",
      "description": "Grilled chicken breast with brown rice...",
      "total_calories": 487,
      "total_protein_g": 38.2,
      "total_carbs_g": 42.5,
      "total_fat_g": 18.1,
      "confidence": "high",
      "photo_url": "https://...",
      "edited_by_user": false
    }
  ],
  "total": 127,
  "limit": 50,
  "offset": 0
}
```

**Pagination**: Uses `LIMIT/OFFSET` — simple and sufficient for this data volume (max ~10 meals/day, ~3650/year). Cursor-based pagination would be premature.

---

```
GET /api/nutrition/meals/{meal_id}
```

Get a single meal with its itemized breakdown.

- **Auth**: `require_read`
- **Response**: Full meal record including `items[]` array and signed `photo_url`.

---

```
PUT /api/nutrition/meals/{meal_id}
```

Update a meal's macro values (user edits after AI analysis).

- **Auth**: `require_write`
- **Request body**:
```json
{
  "total_calories": 500,
  "total_protein_g": 40.0,
  "total_carbs_g": 45.0,
  "total_fat_g": 20.0,
  "meal_type": "lunch",
  "items": [
    {
      "name": "Grilled chicken breast",
      "serving_size": "7 oz",
      "calories": 300,
      "protein_g": 35.0,
      "carbs_g": 0.0,
      "fat_g": 14.0
    }
  ]
}
```

**Behavior**: Sets `edited_by_user = TRUE`. If `items` is provided, the existing items are deleted and replaced (full replace, not partial update — simpler and matches the UI pattern of editing the whole card).

---

```
DELETE /api/nutrition/meals/{meal_id}
```

Delete a meal and its items (cascaded via FK).

- **Auth**: `require_write`
- **Response**: `{"status": "ok"}`
- **GCS cleanup**: Optionally delete the photo from GCS. Since storage is cheap (~$0.02/GB/month), this can be deferred or skipped. The photo path stays in the DB for audit until the row is deleted.

---

#### Daily and Weekly Summaries

```
GET /api/nutrition/daily-summary
```

Aggregate macros for a specific date, including caloric balance.

- **Auth**: `require_read`
- **Query params**: `date` (YYYY-MM-DD, defaults to today)
- **Response**:
```json
{
  "date": "2026-04-09",
  "total_calories_in": 1847,
  "total_protein_g": 142.3,
  "total_carbs_g": 218.5,
  "total_fat_g": 62.1,
  "meal_count": 3,
  "target_calories": 2500,
  "target_protein_g": 150.0,
  "target_carbs_g": 300.0,
  "target_fat_g": 80.0,
  "remaining_calories": 653,
  "calories_out": {
    "rides": 1200,
    "estimated_bmr": 1750,
    "total": 2950
  },
  "net_caloric_balance": -1103
}
```

---

```
GET /api/nutrition/weekly-summary
```

7-day breakdown with daily totals and weekly averages.

- **Auth**: `require_read`
- **Query params**: `date` (any date in the target week, defaults to today; week is Mon-Sun)
- **Response**:
```json
{
  "week_start": "2026-04-06",
  "week_end": "2026-04-12",
  "avg_daily_calories": 2150,
  "avg_daily_protein_g": 155.0,
  "avg_daily_carbs_g": 245.0,
  "avg_daily_fat_g": 72.0,
  "days": [
    {
      "date": "2026-04-06",
      "total_calories": 2340,
      "total_protein_g": 168.0,
      "total_carbs_g": 260.0,
      "total_fat_g": 78.0,
      "meal_count": 4,
      "calories_out_rides": 1500
    }
  ]
}
```

---

#### Macro Targets

```
GET /api/nutrition/targets
```

Get current daily macro targets.

- **Auth**: `require_read`
- **Response**:
```json
{
  "calories": 2500,
  "protein_g": 150.0,
  "carbs_g": 300.0,
  "fat_g": 80.0,
  "updated_at": "2026-04-01T10:00:00"
}
```

---

```
PUT /api/nutrition/targets
```

Update daily macro targets.

- **Auth**: `require_write`
- **Request body**:
```json
{
  "calories": 2800,
  "protein_g": 160.0,
  "carbs_g": 320.0,
  "fat_g": 85.0
}
```

- **Validation**: `calories` > 0 and < 10000; each macro >= 0.

---

#### Nutritionist Chat

```
POST /api/nutrition/chat
```

Send a message to the nutritionist agent. Supports text-only and multimodal (text + image).

- **Auth**: `require_read` (write tools are permission-gated within the agent, same as coaching)
- **Request body**:
```json
{
  "message": "What should I eat before tomorrow's long ride?",
  "session_id": "abc-123",
  "image_data": null,
  "image_mime_type": null
}
```

- **Response**:
```json
{
  "response": "Based on your planned 4h endurance ride tomorrow...",
  "session_id": "abc-123"
}
```

This mirrors the existing `POST /api/coaching/chat` pattern from `server/routers/coaching.py`.

---

#### Nutritionist Chat Sessions

```
GET  /api/nutrition/sessions              — list sessions
GET  /api/nutrition/sessions/{session_id} — get session with messages
DELETE /api/nutrition/sessions/{session_id} — delete session
```

Same pattern as `server/routers/coaching.py` session endpoints, filtered by `app_name="nutrition-coach"`.

---

### 4.3 Pydantic Schemas

Added to `server/models/schemas.py`:

```python
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
    calories_out: dict  # {rides, estimated_bmr, total}
    net_caloric_balance: int

class NutritionChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    image_data: Optional[str] = None       # base64 encoded
    image_mime_type: Optional[str] = None

class NutritionChatResponse(BaseModel):
    response: str
    session_id: str

class MealUpdateRequest(BaseModel):
    total_calories: Optional[int] = None
    total_protein_g: Optional[float] = None
    total_carbs_g: Optional[float] = None
    total_fat_g: Optional[float] = None
    meal_type: Optional[str] = None
    items: Optional[list[MealItem]] = None
```

---

## 5. Calorie Burn Integration

### 5.1 "Calories Out" from Rides

The existing `rides` table already stores `total_calories` (ingested from Garmin/Intervals.icu). This is the primary source for exercise caloric expenditure.

**Query for a given date**:

```python
def get_ride_calories_for_date(conn, date: str) -> int:
    """Sum total_calories from all rides on a given date."""
    row = conn.execute(
        "SELECT COALESCE(SUM(total_calories), 0) AS total "
        "FROM rides WHERE date = %s",
        (date,),
    ).fetchone()
    return int(row["total"])
```

### 5.2 BMR Estimate

For total daily energy expenditure (TDEE), we need a basal metabolic rate estimate. This is computed from athlete settings, not stored in a table.

```python
def estimate_daily_bmr(conn) -> int:
    """Estimate BMR using Mifflin-St Jeor from athlete settings.

    Falls back to a conservative 1750 kcal if settings are incomplete.
    """
    from server.database import get_all_athlete_settings
    settings = get_all_athlete_settings()

    try:
        weight_kg = float(settings.get("weight_kg", 0))
        age = int(settings.get("age", 0))
        gender = settings.get("gender", "").lower()
    except (ValueError, TypeError):
        return 1750

    if weight_kg <= 0 or age <= 0:
        return 1750

    # Mifflin-St Jeor equation (height not tracked, use weight-based estimate)
    # For cyclists, we use an activity multiplier of 1.2 (sedentary baseline,
    # ride calories are added separately)
    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * 175 - 5 * age + 5  # assume 175cm
    elif gender == "female":
        bmr = 10 * weight_kg + 6.25 * 165 - 5 * age - 161  # assume 165cm
    else:
        bmr = 10 * weight_kg + 6.25 * 170 - 5 * age - 78  # midpoint

    return round(bmr * 1.2)  # sedentary multiplier (exercise added separately)
```

**Why estimate height?** The athlete settings don't include height. The Mifflin-St Jeor equation needs it, but for endurance athletes, the weight/age terms dominate. Using an assumed average height introduces ~5% error, which is well within the margin of error for calorie tracking overall. If height tracking is added later, this function adapts by reading from settings.

### 5.3 Caloric Balance Computation

Used by `/api/nutrition/daily-summary` and the nutritionist's `get_caloric_balance` tool:

```python
def compute_caloric_balance(conn, date: str) -> dict:
    """Compute calories in vs out for a given date."""
    # Calories in: sum from meal_logs
    in_row = conn.execute(
        "SELECT COALESCE(SUM(total_calories), 0) AS total "
        "FROM meal_logs WHERE date = %s AND user_id = %s",
        (date, "athlete"),
    ).fetchone()
    calories_in = int(in_row["total"])

    # Calories out: rides + BMR
    ride_cal = get_ride_calories_for_date(conn, date)
    bmr = estimate_daily_bmr(conn)

    total_out = ride_cal + bmr

    return {
        "intake": calories_in,
        "rides": ride_cal,
        "estimated_bmr": bmr,
        "total_expenditure": total_out,
        "net_balance": calories_in - total_out,
    }
```

### 5.4 TSS-to-Calories Fallback

Some rides may have `total_calories = 0` (if the device didn't record it). In that case, estimate from TSS:

```python
def estimate_ride_calories(tss: float, ftp: int, duration_s: float) -> int:
    """Estimate ride calories from TSS when device calories are missing.

    Uses the relationship: kJ ≈ TSS * FTP * duration / 36000
    And the ~25% gross efficiency: calories ≈ kJ / 0.25 * 4.184
    Simplified: calories ≈ kJ * 4.184 (since kJ work ≈ kcal at ~25% efficiency)
    """
    if not tss or not ftp or not duration_s:
        return 0
    # IF = TSS / (duration_h * 100), NP = IF * FTP
    # Work (kJ) = NP * duration_s / 1000
    # For simplicity: kJ ≈ calories (at ~25% efficiency, 1 kJ work ≈ 1 kcal)
    duration_h = duration_s / 3600
    intensity = (tss / (duration_h * 100)) ** 0.5 if duration_h > 0 else 0
    np_estimate = intensity * ftp
    kj = np_estimate * duration_s / 1000
    return round(kj)  # kJ ≈ kcal at 25% gross efficiency
```

---

## 6. Coaching Context — AI Integration Points

### 6.1 Nutritionist Agent Tools (New)

The nutritionist agent (`server/nutrition/`) gets dedicated tools for querying meal data. These are defined in `server/nutrition/tools.py` following the `server/coaching/tools.py` pattern.

**Read-only tools**:

| Tool | Purpose |
|------|---------|
| `get_meal_history(days_back=7)` | List recent meals with macros |
| `get_daily_macros(date="")` | Aggregate macros for a day with target comparison |
| `get_weekly_summary(date="")` | 7-day averages and daily breakdown |
| `get_caloric_balance(date="")` | Intake vs expenditure for a day |
| `get_macro_targets()` | Current daily targets |
| `get_upcoming_training_load(days_ahead=3)` | Planned workouts with TSS/duration (reads from `planned_workouts`) |

**Write tools** (permission-gated, in `server/nutrition/planning_tools.py`):

| Tool | Purpose |
|------|---------|
| `save_meal_analysis(...)` | Persist analyzed meal (called by agent after photo analysis) |
| `update_meal(meal_id, ...)` | Update meal macros |
| `delete_meal(meal_id)` | Delete a meal |
| `set_macro_targets(...)` | Update daily targets |

### 6.2 Cross-Domain Data Accessor for Cycling Coach

The cycling coach agent gets one new lightweight tool in `server/coaching/tools.py`:

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
        # Meals today
        meals = conn.execute(
            "SELECT total_calories, total_protein_g, total_carbs_g, "
            "total_fat_g, logged_at, description "
            "FROM meal_logs WHERE date = %s AND user_id = %s ORDER BY logged_at DESC",
            (date, "athlete"),
        ).fetchall()

        # Caloric balance
        balance = compute_caloric_balance(conn, date)

        # Targets
        targets_row = conn.execute(
            "SELECT calories, protein_g, carbs_g, fat_g FROM macro_targets "
            "WHERE user_id = %s",
            ("athlete",),
        ).fetchone()

    total_cal = sum(m["total_calories"] for m in meals)
    total_p = sum(m["total_protein_g"] for m in meals)
    total_c = sum(m["total_carbs_g"] for m in meals)
    total_f = sum(m["total_fat_g"] for m in meals)

    target_cal = targets_row["calories"] if targets_row else 2500

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
        "caloric_balance": balance,
    }
```

This is a **direct DB query**, not an agent invocation. It gives the cycling coach quick access to nutritional status without the latency of invoking the nutritionist agent. The AI integration proposal covers when to use this lightweight tool vs. invoking the full nutritionist agent via `AgentTool`.

### 6.3 Registration

In `server/coaching/agent.py`, add `get_athlete_nutrition_status` to the tools list:

```python
from server.coaching.tools import (
    # ... existing imports ...
    get_athlete_nutrition_status,
)

# In _get_agent():
tools = [
    # ... existing tools ...
    get_athlete_nutrition_status,
]
```

---

## 7. Shared Data Access Layer

### 7.1 New Query Functions in `server/queries.py`

Following the existing pattern where `queries.py` holds shared functions used by both tools and routers:

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
    """Get daily macro targets, falling back to defaults."""
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

---

## 8. Design Tradeoffs

### 8.1 Photo Storage: GCS vs. Inline Database (BYTEA)

| Factor | GCS (chosen) | PostgreSQL BYTEA |
|--------|-------------|------------------|
| **Storage cost** | ~$0.02/GB/month | Part of DB disk — more expensive at scale |
| **Retrieval performance** | Served directly by GCS CDN | DB must read/stream binary; blocks connection pool |
| **Backup impact** | Photos excluded from DB backups (desired) | Bloats DB dumps, slows pg_dump |
| **Signed URLs** | Native support | N/A — must proxy through backend |
| **Simplicity** | Requires `google-cloud-storage` dependency | No new dependency |

**Decision**: GCS. The performance and cost benefits are clear. The `google-cloud-storage` dependency is already transitively available in the environment (via `google-cloud-aiplatform`).

### 8.2 Analysis Flow: Synchronous vs. Async

| Factor | Synchronous (chosen) | Async (webhook/polling) |
|--------|---------------------|------------------------|
| **Latency** | 3-8s wait in HTTP response | Upload returns immediately; poll for result |
| **Complexity** | One endpoint, one request-response cycle | Upload endpoint + status endpoint + polling logic on frontend |
| **Error handling** | Errors returned in same response | Must handle orphaned jobs, timeouts, retries |
| **Frontend** | Simple loading spinner during fetch | Polling loop or WebSocket for status updates |

**Decision**: Synchronous for v1. The 3-8s analysis time is acceptable with a loading state. The single-user nature of this app means there's no concurrent request pressure.

**Future escape hatch**: If analysis latency increases (larger models, more complex prompts), convert to async:
1. `POST /api/nutrition/meals` returns `202 Accepted` with `meal_id`
2. Analysis runs in a background task (FastAPI `BackgroundTasks` or a task queue)
3. `GET /api/nutrition/meals/{meal_id}` returns `status: "analyzing"` until complete
4. Frontend polls every 2s or uses SSE

### 8.3 Pagination: Offset vs. Cursor

| Factor | Offset (chosen) | Cursor-based |
|--------|-----------------|-------------|
| **Implementation** | `LIMIT/OFFSET` — trivial | Requires encoded cursor, keyset pagination |
| **Performance at scale** | Degrades past ~10K rows | Consistent regardless of depth |
| **Expected data volume** | ~3,650 meals/year (10/day) | Same |
| **Frontend complexity** | Simple page numbers | Must manage opaque cursor tokens |

**Decision**: Offset. At the expected data volume, offset pagination has no performance issues. Even 10 years of data (~36K rows) won't stress `LIMIT/OFFSET` with the `idx_meal_logs_date` index.

### 8.4 Meal Items: Full Replace vs. Partial Update

When a user edits a meal, the `PUT` endpoint replaces all `meal_items` rather than patching individual items.

**Rationale**: The items list is short (typically 3-8 items) and treated as a unit. Partial updates would require item-level IDs in the frontend, merge logic in the backend, and conflict handling — all for a list that's never more than ~10 items. Full replace is simpler, correct, and fast.

---

## 9. Migration Strategy

### 9.1 Schema Addition

New tables are added using the existing `CREATE TABLE IF NOT EXISTS` pattern inside the `_SCHEMA` string in `server/database.py`. The `init_db()` function runs on every app startup and is idempotent — new tables are created if they don't exist, existing tables are untouched.

Steps:
1. Add the three `CREATE TABLE IF NOT EXISTS` statements and their `CREATE INDEX` statements to `_SCHEMA`
2. Add `macro_targets` default seed (similar to `_seed_workout_templates`) to insert a default row if the table is empty

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

3. Call `_seed_macro_targets(conn)` from `init_db()` after `_seed_workout_templates(conn)`

### 9.2 No Destructive Migrations

These are purely additive changes — new tables, new indexes. No existing tables are modified. No `ALTER TABLE` on existing tables. This means:
- Zero risk to existing data
- No downtime needed
- Rollback is simply not using the new tables (they sit empty and harmless)

### 9.3 Future Migrations

If future iterations need to add columns to `meal_logs` (e.g., `voice_note_gcs_path`), use the existing migration pattern from `init_db()`:

```python
# Add to init_db() migration section:
try:
    cur = conn.cursor()
    cur.execute("ALTER TABLE meal_logs ADD COLUMN IF NOT EXISTS voice_note_gcs_path TEXT")
    conn.commit()
    cur.close()
except Exception:
    conn.rollback()
```

---

## 10. New Dependencies

| Package | Purpose | Notes |
|---------|---------|-------|
| `google-cloud-storage` | GCS upload/signed URLs | Likely already available transitively via `google-cloud-aiplatform` — verify with `pip show google-cloud-storage` |
| `Pillow` | Image resize before upload | Standard, lightweight |

If `google-cloud-storage` is not already installed:
```
pip install google-cloud-storage Pillow
```

Add to `requirements.txt`.

---

## 11. Module Structure

```
server/
├── nutrition/                    ← NEW module
│   ├── __init__.py
│   ├── agent.py                  # Nutritionist agent, Runner, chat()
│   ├── tools.py                  # Read-only agent tools
│   ├── planning_tools.py         # Write agent tools (permission-gated)
│   └── photo.py                  # GCS upload/signed URL helpers
├── routers/
│   └── nutrition.py              ← NEW router
├── models/
│   └── schemas.py                ← MODIFIED (add meal/nutrition schemas)
├── database.py                   ← MODIFIED (add new tables to _SCHEMA)
├── queries.py                    ← MODIFIED (add meal query helpers)
├── coaching/
│   ├── agent.py                  ← MODIFIED (add nutrition tool + AgentTool)
│   └── tools.py                  ← MODIFIED (add get_athlete_nutrition_status)
└── main.py                       ← MODIFIED (include nutrition router)
```

---

## 12. Configuration

New environment variables (added to `.env` and `server/config.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEAL_PHOTO_BUCKET` | `jasondel-coach-data` | GCS bucket for meal photos |
| `MEAL_PHOTO_PREFIX` | `meals` | Path prefix within bucket |

These are optional — defaults match the existing bucket. Only needed if photos should go to a different bucket.

No new secrets required. GCS access uses the same Application Default Credentials already configured for Vertex AI.
