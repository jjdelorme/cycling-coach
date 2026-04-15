# Macro Tracker — Final Design Specification
> **Version target:** v1.9.x

## 1. Executive Summary

The Macro Tracker adds meal photo logging, AI-powered macronutrient estimation, and a dedicated Nutritionist agent to the cycling coaching platform. Users snap a photo, the Nutritionist agent analyzes it via Gemini's multimodal vision, and structured macro data (calories, protein, carbs, fat) is persisted alongside the photo. A dashboard widget shows daily energy balance (calories in vs. out), and the Nutritionist and Cycling Coach agents share data to produce holistic fueling and training guidance.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Navigation | New "Nutrition" bottom tab (5th tab) | Peer-level feature used multiple times daily; needs its own FAB and timeline |
| Primary interaction | Camera FAB -> photo -> AI analysis -> save (3 taps) | Speed is king — kitchen, one hand, under 5 seconds |
| AI architecture | Separate Nutritionist agent (not bolted onto cycling coach) | Focused system prompt, isolated tool set (~15 tools each vs ~35 combined), independent sessions |
| Agent communication | Hybrid: direct DB tools (90%) + AgentTool (10%) | Fast data lookups for common cases; full agent reasoning for complex fueling guidance |
| Photo storage | GCS (`gs://jasondel-coach-data/meals/`) with signed URLs | Existing bucket, no new infra, CDN-like serving, no backend streaming |
| Analysis flow | Synchronous (single POST, 3-8s response) | Single-user app; no concurrent pressure; simpler than polling |
| Data model | `meal_logs` + `meal_items` + `macro_targets` (3 new tables) | Itemized breakdown enables per-food editing; targets enable progress tracking |
| Date/time column types | TEXT (YYYY-MM-DD / ISO 8601) | Matches existing `rides.date`, `daily_metrics.date` convention |
| Voice notes | v1 — audio passed directly to Gemini as a multimodal `Part` | Native Gemini capability; no transcription step; helps resolve ambiguous images |
| Offline support | Deferred to v2 | Over-engineering for v1; most logging happens at home with connectivity |

---

## 2. User Experience

### 2.1 Navigation

Add a 5th tab `"Nutrition"` to the mobile bottom nav and desktop top nav, between "Analysis" and "Coach."

```
Mobile bottom nav:
[ Dashboard | Rides | Calendar | Nutrition | Coach ]
```

**Icon:** `UtensilsCrossed` from lucide-react.  
**TabKey:** `'nutrition'` added to the `TabKey` union type. The `Nutrition` page component lazy-loads.

On desktop, the tab renders as a standard nav button. The Nutritionist chat lives in the existing `CoachPanel` slide-out as a second tab (see Section 2.6).

### 2.2 Primary Flow: Quick Capture (3 taps)

```
[Nutrition tab] -> tap FAB -> [Camera/file picker] -> photo taken
-> [Analysis card with spinner] -> [Macros populate] -> [Save]
```

1. User opens Nutrition tab. Sees today's meal timeline (or empty state).
2. Taps the FAB (bottom-right, `Camera` icon, 56px accent circle).
3. Native camera/file picker opens via `<input type="file" accept="image/*" capture="environment">`.
4. Photo selected -> upload begins immediately. No intermediate confirm screen.
5. Analysis card appears with skeleton placeholders and pulsing `Sparkles` icon (3-8s).
6. Macros populate with animated transition. Card becomes editable.
7. User taps "Save." Meal slides into timeline.

**Image optimization:** Client-side resize to max 1200px longest edge via `<canvas>` before upload. Server normalizes to JPEG at 85% quality as a second pass.

### 2.3 AI Clarification Flow

When the agent assigns `confidence: "low"`:

1. Analysis card renders with an amber `AlertTriangle` badge.
2. Clarification prompt appears inline below macros: *"Is that grilled chicken or tofu on the salad?"*
3. User types a response in a single-line input.
4. Agent re-analyzes with additional context. Numbers update in-place.
5. If still uncertain, agent saves its best estimate and marks with `~` approximate indicator.

No multi-step wizard. Single inline text field preserves the one-shot feel.

### 2.4 Nutrition Page Layout

#### Mobile (primary)

```
+----------------------------------+
| NUTRITION             [filter] [chef] |  <- page header + nutritionist toggle
+----------------------------------+
| +----------------------------+   |
| | TODAY - Apr 9              |   |
| | 1,847 kcal  -  142g P     |   |  <- DailySummaryStrip
| | 218g C  -  62g F           |   |
| | ==================-- 78%   |   |  <- progress bar vs daily target
| +----------------------------+   |
|                                  |
| +------------------------------+ |
| | 12:34 PM                     | |
| | [thumb]  Grilled chicken     | |  <- MacroCard
| |          salad w/ quinoa     | |
| |          487 kcal            | |
| |          38g P - 42g C - 18g F | |
| +------------------------------+ |
|                                  |
| +------------------------------+ |
| | 8:15 AM                      | |
| | [thumb]  Oatmeal w/ banana   | |  <- MacroCard
| +------------------------------+ |
|                          [camera] |  <- FAB
+----------------------------------+
| [Dash] [Rides] [Cal] [Nutr] [Coach] |
+----------------------------------+
```

**DailySummaryStrip:** Total calories (large bold, `text-accent`), macro breakdown in micro-labels (`text-[10px] font-bold text-text-muted uppercase tracking-widest`), progress bar toward daily calorie target (`bg-accent` fill on `bg-surface-low` track).

**Date navigation:** `ChevronLeft` / `ChevronRight` buttons flanking a date display (same pattern as Rides page date navigator).

**Empty state:** Large faded `UtensilsCrossed` icon, "NO MEALS LOGGED TODAY" text, accent "Log a Meal" button.

### 2.5 MacroCard Design

**Display mode** (in timeline):

```
+----------------------------------+
| 12:34 PM                     ~  |  <- timestamp + optional ~ for low confidence
| [72x72 thumb]  Grilled chicken  |  <- AI-generated description
|                salad w/ quinoa  |
| [487 kcal] [38g P] [42g C] [18g F] |  <- color-coded macro values
+----------------------------------+
```

**Macro color coding** (reuses existing palette):
- Calories: `text-accent` (red)
- Protein: `text-green` (matches CTL/fitness color)
- Carbs: `text-yellow` (matches warning color)
- Fat: `text-blue` (matches power color)

**Edit mode** (tap to expand inline, no modal):
- Larger photo preview (tappable to view full)
- Each macro value becomes `<input type="number">` styled to match display until focused
- "Save Changes" button appears when values differ from stored
- "Ask the nutritionist about this meal" quick action opens Nutritionist chat with meal context pre-filled
- `Trash2` delete button in header with `window.confirm()` prompt

### 2.6 Nutritionist Chat

**Decision: Tabbed within existing CoachPanel slide-out.**

```
+-------------------------------------+
| [Cycling Coach] [Nutritionist]      |  <- tab switcher (pill buttons)
|-------------------------------------|
|                                     |
|  (chat messages for active agent)   |
|                                     |
|-------------------------------------|
| [ Ask your nutritionist... ]  [>]  |
+-------------------------------------+
```

- Active tab: `bg-accent text-white` (Coach) or `bg-green text-white` (Nutritionist)
- Each tab maintains its own message history and session
- When Nutritionist is active: send button uses `bg-green`, bot avatar shows `UtensilsCrossed`
- Context passing: opening from a MacroCard's "Ask about this meal" button prepends meal context (photo URL, macros, description) as a view hint

**Why tabbed, not a separate panel:** Avoids duplicating the slide-out mechanism, prevents awkward dual-panel states, and scales if more agents are added later.

### 2.7 Dashboard Widget: Energy Balance

New card in the Dashboard grid after "Next Workout" / "Latest Ride":

```
+----------------------------------+
| ENERGY BALANCE - Today           |
|----------------------------------|
|    IN          OUT        NET    |
|  1,847       2,340       -493   |  <- large bold numbers
|   kcal        kcal        kcal  |
|  3 meals     Morning Ride       |
|                                  |
| [==========-------] in vs out   |  <- ratio bar
|                                  |
| This Week: [mini sparkline]     |  <- 7-day net calorie trend
|                                  |
| [ Log a Meal -> ]               |  <- CTA to Nutrition tab
+----------------------------------+
```

**Data sources:**
- "Calories In" — sum from today's `meal_logs`
- "Calories Out" — `rides.total_calories` + estimated BMR from athlete settings
- "Net" — difference; green (surplus) or red (deficit)
- Sparkline: Chart.js `Line`, last 7 days, minimal (`h-16`, no axis labels)

### 2.8 Week Summary View

Toggle from daily to weekly view on the Nutrition page:

```
+----------------------------------+
| WEEKLY NUTRITION - Apr 7-13      |
| Avg Daily: 2,150 kcal            |
| Avg Protein: 155g - Carbs: 245g  |
| Avg Fat: 72g                     |
|                                  |
| Mon ================---  2,340   |
| Tue ==============-----  1,980   |  <- Chart.js horizontal Bar
| Wed ===================  2,450   |     (stacked P/C/F segments)
| Thu ============-------  1,750   |
| Fri ==================-  2,200   |
+----------------------------------+
```

### 2.9 New Frontend Components

| Component | File | Purpose |
|-----------|------|---------|
| `Nutrition` | `pages/Nutrition.tsx` | Top-level page: meal timeline + FAB + date nav |
| `MealCapture` | `components/MealCapture.tsx` | Camera/upload trigger |
| `MacroCard` | `components/MacroCard.tsx` | Single meal display + inline edit |
| `MacroAnalysisCard` | `components/MacroAnalysisCard.tsx` | In-flight analysis (skeleton -> populated) |
| `MealTimeline` | `components/MealTimeline.tsx` | Day scrollable meal list |
| `DailySummaryStrip` | `components/DailySummaryStrip.tsx` | Daily totals bar with progress |
| `NutritionDashboardWidget` | `components/NutritionDashboardWidget.tsx` | Energy balance card for Dashboard |
| `NutritionistPanel` | `components/NutritionistPanel.tsx` | Nutritionist tab within CoachPanel |

**Modified components:** `Layout.tsx` (add tab + icon), `App.tsx` (add page + TabKey), `Dashboard.tsx` (add widget), `CoachPanel.tsx` (add tab switcher).

### 2.10 New Hooks

| Hook | Purpose |
|------|---------|
| `useMeals(params?)` | Fetch meal history (date-filtered) |
| `useMeal(id)` | Fetch single meal detail |
| `useLogMeal()` | Mutation: upload photo + optional comment, receive AI analysis |
| `useUpdateMeal()` | Mutation: edit macro values |
| `useDeleteMeal()` | Mutation: remove a meal |
| `useDailyNutrition(date)` | Aggregated daily totals + caloric balance |
| `useNutritionistChat()` | Chat mutation for Nutritionist agent |

---

## 3. Data Model

### 3.1 DDL — Three New Tables

Added to the `_SCHEMA` string in `server/database.py` using `CREATE TABLE IF NOT EXISTS`:

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
    date TEXT NOT NULL,                          -- YYYY-MM-DD (matches rides.date)
    logged_at TEXT NOT NULL,                     -- ISO 8601 timestamp
    meal_type TEXT,                              -- breakfast, lunch, dinner, snack
    description TEXT NOT NULL,                   -- AI-generated meal description
    total_calories INTEGER NOT NULL,
    total_protein_g REAL NOT NULL,
    total_carbs_g REAL NOT NULL,
    total_fat_g REAL NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',   -- high, medium, low
    photo_gcs_path TEXT,                         -- gs://jasondel-coach-data/meals/{user_id}/{timestamp}.jpg
    agent_notes TEXT,                            -- nutritionist commentary
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

### 3.2 Design Notes

- **TEXT for dates/timestamps**: Matches `rides.date`, `daily_metrics.date`, and all other temporal columns in the existing schema. Keeps joins trivial.
- **`user_id` default `'athlete'`**: Matches `coach_memory.user_id`, `chat_sessions.user_id`. Ready for multi-user by changing the default.
- **`ON DELETE CASCADE`** on `meal_items`: Deleting a meal deletes its itemized breakdown. No orphans.
- **No `voice_note_gcs_path`**: Audio is used only during the analysis request (passed directly to Gemini as a multimodal `Part`) and is not stored long-term. Only the resulting macro analysis is persisted.
- **No foreign key to `users`**: Matches existing pattern (`coach_memory`, `chat_sessions` use `user_id TEXT` without FK).

### 3.3 GCS Photo Storage

Use the existing `gs://jasondel-coach-data` bucket:

```
gs://jasondel-coach-data/
  fit/                           <- existing
  json/                          <- existing
  planned_workouts/              <- existing
  meals/                         <- NEW
    {user_id}/
      {YYYYMMDD}_{HHmmss}_{uuid_short}.jpg
```

**Example:** `gs://jasondel-coach-data/meals/athlete/20260409_123456_a1b2c3.jpg`

**Signed URLs for retrieval:** Backend generates V4 signed URLs with 60-minute expiry. Frontend re-fetches meal lists (which regenerate URLs) on page load and pull-to-refresh. No backend image streaming needed.

**Upload flow:**
1. Frontend sends `multipart/form-data` to backend
2. Backend validates (type, size), resizes to max 1200px (Pillow), converts to JPEG 85%
3. Backend uploads to GCS, stores `gs://` path in `meal_logs.photo_gcs_path`
4. Backend sends image to Nutritionist agent for analysis
5. Agent calls `save_meal_analysis` tool -> updates row with macros, inserts `meal_items`
6. Backend returns completed meal with signed photo URL

**Storage cost:** ~100KB/photo after resize. 10 meals/day = ~365MB/year. Negligible. No lifecycle/auto-delete policy needed.

### 3.4 Seed Data

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

Called from `init_db()` after `_seed_workout_templates(conn)`.

### 3.5 Migration Strategy

Purely additive: 3 new tables, new indexes, no `ALTER TABLE` on existing tables. Zero risk to existing data. Rollback = ignore empty tables.

---

## 4. API Design

### 4.1 Router

New file: `server/routers/nutrition.py`, mounted as `app.include_router(nutrition.router)` in `server/main.py`.

```python
router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])
```

### 4.2 Endpoints

#### `POST /api/nutrition/meals` — Analyze & Log Meal (primary flow)

Upload a meal photo for AI analysis and storage. Handles upload, GCS storage, agent analysis, and DB persistence in a single synchronous request.

- **Auth:** `require_write`
- **Content-Type:** `multipart/form-data`
- **Request fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | `UploadFile` | Yes | Meal photo (JPEG, PNG, WebP; max 10MB) |
| `comment` | `str (Form)` | No | Text context ("about 6oz of chicken") |
| `meal_type` | `str (Form)` | No | breakfast, lunch, dinner, snack |

- **Response (201 Created):**

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
    {"id": 101, "name": "Grilled chicken breast", "serving_size": "6 oz", "calories": 280, "protein_g": 32.0, "carbs_g": 0.0, "fat_g": 12.0},
    {"id": 102, "name": "Brown rice", "serving_size": "1 cup", "calories": 150, "protein_g": 3.5, "carbs_g": 32.0, "fat_g": 1.5},
    {"id": 103, "name": "Steamed broccoli", "serving_size": "1 cup", "calories": 57, "protein_g": 2.7, "carbs_g": 10.5, "fat_g": 4.6}
  ],
  "agent_notes": "Solid post-ride meal. Good protein-to-carb ratio for recovery."
}
```

**Why synchronous, not upload + poll?** Analysis takes 3-8 seconds — acceptable for a loading state. Single-user app has no concurrent pressure. If latency increases later, convert to `202 Accepted` + polling (see Section 7).

---

#### `GET /api/nutrition/meals` — List Meals

- **Auth:** `require_read`
- **Query params:** `start_date`, `end_date` (YYYY-MM-DD), `limit` (default 50), `offset` (default 0)
- **Response:** `{ "meals": [MealSummary...], "total": 127, "limit": 50, "offset": 0 }`
- **Pagination:** `LIMIT/OFFSET`. At ~3,650 meals/year max, offset pagination has no performance issues.

#### `GET /api/nutrition/meals/{meal_id}` — Get Meal Detail

- **Auth:** `require_read`
- **Response:** Full meal record including `items[]` array and signed `photo_url`.

#### `PUT /api/nutrition/meals/{meal_id}` — Update Meal

- **Auth:** `require_write`
- **Behavior:** Sets `edited_by_user = TRUE`. If `items` provided, existing items are deleted and replaced (full replace, not partial — list is typically 3-8 items; simpler and correct).

#### `DELETE /api/nutrition/meals/{meal_id}` — Delete Meal

- **Auth:** `require_write`
- **Response:** `{"status": "ok"}`
- **GCS cleanup:** Deferred. Storage is cheap (~$0.02/GB/month).

---

#### `GET /api/nutrition/daily-summary` — Daily Aggregate

- **Auth:** `require_read`
- **Query params:** `date` (YYYY-MM-DD, defaults to today)
- **Response:**

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

**BMR estimation:** Mifflin-St Jeor equation from athlete settings (weight, age, gender). Assumed height (175cm male / 165cm female) introduces ~5% error — well within overall calorie tracking margin. Falls back to 1750 kcal if settings are incomplete.

**TSS-to-calories fallback:** For rides with `total_calories = 0`, estimate from TSS using `kJ ~= kcal` at ~25% gross efficiency.

#### `GET /api/nutrition/weekly-summary` — Weekly Aggregate

- **Auth:** `require_read`
- **Query params:** `date` (any date in target week, defaults to today; Mon-Sun week)
- **Response:** 7-day breakdown with per-day totals, weekly averages, and ride calories per day.

---

#### `GET /api/nutrition/targets` — Get Macro Targets
#### `PUT /api/nutrition/targets` — Update Macro Targets

- **Auth:** `require_read` / `require_write`
- **Validation:** calories > 0 and < 10000; each macro >= 0

---

#### `POST /api/nutrition/chat` — Nutritionist Chat

- **Auth:** `require_read` (write tools are permission-gated within agent)
- **Request:** `{ "message": "...", "session_id": "...", "image_data": null, "image_mime_type": null }`
- **Response:** `{ "response": "...", "session_id": "..." }`

Mirrors `POST /api/coaching/chat` pattern.

#### Nutritionist Sessions — `GET /api/nutrition/sessions`, `GET /api/nutrition/sessions/{id}`, `DELETE /api/nutrition/sessions/{id}`

Same pattern as `server/routers/coaching.py`, filtered by `app_name="nutrition-coach"`.

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

---

## 5. AI Architecture

### 5.1 Nutritionist Agent

**Module structure** (mirrors `server/coaching/`):

```
server/nutrition/
  __init__.py
  agent.py              # Agent, Runner, chat() — mirrors coaching/agent.py
  tools.py              # Read-only agent tools
  planning_tools.py     # Write tools (permission-gated)
  photo.py              # GCS upload/signed URL helpers
```

**Agent definition:**

```python
APP_NAME = "nutrition-coach"

Agent(
    name="nutritionist",
    model=_get_effective_model(),
    description="Sports nutritionist specializing in endurance athlete fueling",
    instruction=_build_system_instruction,  # callable, built from DB state
    tools=tools,
)
```

**Session/memory services:** Re-use existing `DbSessionService` and `DbMemoryService` from `server/coaching/`. Keyed by `app_name="nutrition-coach"` for session isolation. Same `chat_sessions` and `chat_events` tables serve both agents.

### 5.2 System Instruction (Callable)

Dynamically assembled from DB state, same pattern as the cycling coach's `_build_system_instruction(ctx)`:

```python
def _build_system_instruction(ctx) -> str:
    # Pull: athlete weight/FTP, daily calorie targets, last 3 days meals,
    # recent rides for expenditure context, current CTL
    return f"""You are an expert sports nutritionist working with an endurance cyclist.

TODAY'S DATE: {today_str}

ATHLETE PROFILE:
- Weight: {weight_kg} kg / FTP: {ftp} W / Current CTL: {ctl}
- Daily targets: {daily_cal_target} kcal (P {protein_target}g / C {carb_target}g / F {fat_target}g)

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
- Reference specific numbers from history when making recommendations
"""
```

### 5.3 Vision Integration

The image is sent to the Nutritionist agent as a `types.Content` message with both an image part and a text part, processed through `runner.run_async()`:

```python
from google.genai import types

content = types.Content(
    role="user",
    parts=[
        types.Part.from_image(image=types.Image.from_bytes(
            data=image_bytes, mime_type="image/jpeg",
        )),
        types.Part.from_text(
            text=user_comment or "Analyze this meal and estimate its macros."
        ),
    ],
)
```

**Decision: Agent-internal vision (not a separate pre-processing pipeline).** The agent processes the image directly via multimodal `Content`. This lets it use session context and meal history to improve accuracy. A separate vision step adds complexity without meaningful benefit.

**Response handling:** The agent does NOT return structured JSON directly. It calls the `save_meal_analysis` tool with structured arguments via ADK function-calling. This matches the existing coaching pattern (tools receive structured data, agent provides conversational response alongside).

**Validation in `save_meal_analysis` tool body:**
- `total_calories` > 0 and < 10000
- Each macro >= 0
- Cross-check: `(protein*4 + carbs*4 + fat*9)` within 15% of `total_calories` (log warning if not, still save)
- `confidence` must be `high`, `medium`, or `low`
- `items` must be non-empty

### 5.4 Agent Tools

**Read-only tools** (`server/nutrition/tools.py`):

| Tool | Purpose |
|------|---------|
| `get_meal_history(days_back=7)` | Recent meals with macros and timestamps |
| `get_daily_macros(date="")` | Aggregate macros for a day with target comparison |
| `get_weekly_summary(date="")` | 7-day averages and daily breakdown |
| `get_caloric_balance(date="")` | Intake vs expenditure (BMR + rides) |
| `get_macro_targets()` | Current daily targets |
| `get_upcoming_training_load(days_ahead=3)` | Planned workouts with TSS/duration (reads `planned_workouts` directly) |
| `get_recent_workouts(days_back=3)` | Recent ride summaries with TSS, duration, calories |

**Write tools** (`server/nutrition/planning_tools.py`, permission-gated):

| Tool | Purpose |
|------|---------|
| `save_meal_analysis(...)` | Persist analyzed meal (called by agent after photo analysis) |
| `update_meal(meal_id, ...)` | Update meal macros |
| `delete_meal(meal_id)` | Remove meal |
| `set_macro_targets(...)` | Update daily targets |
| `ask_clarification(question, context)` | Request user input for ambiguous images (returns question text; frontend renders as follow-up) |

### 5.5 Agent-to-Agent Communication

**Decision: Hybrid approach — direct DB tools (primary) + AgentTool (complex reasoning).**

**Primary (90% of interactions):** Each agent gets lightweight cross-domain read-only tools that query the other domain's tables directly:

```python
# In Cycling Coach's tools.py:
def get_athlete_nutrition_status(date: str = "") -> dict:
    """Quick nutritional check — direct DB query, no agent invocation."""
    # Returns: calories in/out, macro breakdown, meal count, last meal time

# In Nutritionist's tools.py:
def get_upcoming_training_load(days_ahead: int = 3) -> dict:
    """Upcoming planned workouts — direct DB query, no agent invocation."""
    # Returns: planned workouts with TSS, duration, type, estimated calories
```

**Complex reasoning (10%):** The Cycling Coach gets the Nutritionist as an `AgentTool` for cases requiring the nutritionist's full reasoning ability:

```python
from google.adk.tools.agent_tool import AgentTool

# Cycling Coach agent setup:
tools = [
    # ... existing coaching tools ...
    get_athlete_nutrition_status,        # direct DB for quick checks
    AgentTool(agent=nutritionist),       # full agent for complex fueling guidance
]
```

**Unidirectional AgentTool (Coach -> Nutritionist only)** to avoid circular dependencies. The Nutritionist reads training data via direct DB tools, never invokes the Coach agent.

**Coach system prompt addition:**

```
NUTRITION INTEGRATION:
- For quick checks (has the athlete eaten today? total calories?),
  use get_athlete_nutrition_status — fast, no agent invocation.
- For complex fueling guidance (pre-ride nutrition plans, recovery meal advice,
  multi-day fueling strategies), delegate to the nutritionist agent.
```

### 5.6 Workout Planning Integration

For workouts > 90 minutes, the Coach should include fueling guidance in coach notes:

1. Coach calls `get_athlete_nutrition_status` (or Nutritionist AgentTool for complex guidance)
2. Incorporates nutritional context into the notes
3. Calls `set_workout_coach_notes` (existing tool — no new tools needed)

**Coach system prompt addition:**

```
NUTRITION-AWARE COACH NOTES:
For workouts > 90 minutes, include fueling guidance:
1. Check recent intake via get_athlete_nutrition_status
2. For rides > 2h: pre-ride meal timing, on-bike carb targets (60-90g/h), recovery window
3. If recent intake suggests under-fueling, flag prominently
4. For rides > 3h or IF > 0.85, delegate to nutritionist for detailed guidance
```

Per project principles: this logic lives in the system prompt, not Python code. The agent reasons from data; tools just expose data.

---

## 6. Cross-Cutting Concerns

### 6.1 Authentication

All nutrition endpoints use the existing auth middleware:
- Read endpoints: `require_read`
- Write endpoints (meal CRUD, targets, photo upload): `require_write`
- Chat: `require_read` (write tools are permission-gated within agent, same as coaching)
- `GOOGLE_AUTH_ENABLED=false` bypasses auth for local dev

### 6.2 Photo Upload Limits

| Constraint | Value |
|------------|-------|
| Max file size | 10MB (pre-resize) |
| Allowed MIME types | `image/jpeg`, `image/png`, `image/webp` |
| Max dimension after resize | 1200px longest edge |
| Output format | JPEG, 85% quality |
| Output size (typical) | ~80-150KB |

### 6.3 Rate Limiting

Meal photo analysis is expensive (multimodal Gemini tokens). Implement per-user rate limit on `POST /api/nutrition/meals`: **20 analyses/day**. This is generous (most users log 3-6 meals/day) but prevents abuse. Return `429 Too Many Requests` if exceeded.

### 6.4 Error Handling

- Image validation failures (wrong type, too large): `400 Bad Request` with specific message
- GCS upload failure: `502 Bad Gateway` with retry guidance
- Agent analysis failure/timeout: `504 Gateway Timeout` — meal photo is still stored in GCS; user can retry analysis or enter macros manually
- Signed URL generation failure: fall back to empty `photo_url`; meal data is still usable without the photo

### 6.5 New Dependencies

| Package | Purpose | Notes |
|---------|---------|-------|
| `google-cloud-storage` | GCS upload/signed URLs | Likely already available via `google-cloud-aiplatform` — verify |
| `Pillow` | Server-side image resize | Standard, lightweight |

### 6.6 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEAL_PHOTO_BUCKET` | `jasondel-coach-data` | GCS bucket for photos |
| `MEAL_PHOTO_PREFIX` | `meals` | Path prefix within bucket |

Optional — defaults match existing bucket. No new secrets. GCS uses same ADC as Vertex AI.

### 6.7 Module Structure (Full)

```
server/
  nutrition/                    <- NEW module
    __init__.py
    agent.py                    # Nutritionist agent, Runner, chat()
    tools.py                    # Read-only agent tools
    planning_tools.py           # Write agent tools (permission-gated)
    photo.py                    # GCS upload/signed URL helpers
  routers/
    nutrition.py                <- NEW router
  models/
    schemas.py                  <- MODIFIED (add meal/nutrition schemas)
  database.py                   <- MODIFIED (add 3 tables to _SCHEMA, add seed)
  queries.py                    <- MODIFIED (add meal query helpers)
  coaching/
    agent.py                    <- MODIFIED (add nutrition tool + AgentTool)
    tools.py                    <- MODIFIED (add get_athlete_nutrition_status)
  main.py                       <- MODIFIED (include nutrition router)

frontend/src/
  pages/Nutrition.tsx            <- NEW
  components/
    MealCapture.tsx              <- NEW
    MacroCard.tsx                <- NEW
    MacroAnalysisCard.tsx        <- NEW
    MealTimeline.tsx             <- NEW
    DailySummaryStrip.tsx        <- NEW
    NutritionDashboardWidget.tsx <- NEW
    NutritionistPanel.tsx        <- NEW
  hooks/
    useMeals.ts                  <- NEW (+ useMeal, useLogMeal, etc.)
    useDailyNutrition.ts         <- NEW
    useNutritionistChat.ts       <- NEW
```

---

## 7. Open Questions

These need product/engineering input before implementation:

1. **ADK multimodal pass-through:** Confirm `runner.run_async()` forwards image parts in `Content` to Gemini unchanged. If ADK strips non-text parts, image analysis needs a direct `genai.GenerativeModel.generate_content()` call outside the agent loop, with results fed as text context.

2. **AgentTool import path:** Verify `google.adk.tools.agent_tool.AgentTool` exists in the installed ADK version. Alternative import paths may apply.

3. **AgentTool session isolation:** When Coach invokes Nutritionist via AgentTool, does the Nutritionist get its own session or share the Coach's? Affects memory and context isolation.

4. **Gemini vision accuracy:** Benchmark Gemini 2.5 Flash food recognition against a test set of 50-100 meal photos with known macros. If accuracy is insufficient, consider Gemini 2.5 Pro for the Nutritionist (higher cost).

5. **Height in athlete settings:** BMR estimation assumes height (175/165cm). Should we add a `height_cm` field to athlete settings for more accurate TDEE? ~5% error without it.

6. **Daily calorie target source:** Should the Nutritionist agent be able to recommend/adjust calorie targets based on training load, or is this always user-configured? The `set_macro_targets` tool exists but the policy for who sets targets needs a decision.

---

## 8. Implementation Phasing

### v1 — Core Meal Logging + Nutritionist

**Backend:**
- [ ] Add 3 tables to `_SCHEMA` + seed macro targets
- [ ] `server/nutrition/photo.py` — GCS upload + signed URL helpers
- [ ] `server/nutrition/tools.py` — read-only agent tools
- [ ] `server/nutrition/planning_tools.py` — write tools (save_meal_analysis, update, delete)
- [ ] `server/nutrition/agent.py` — Nutritionist agent with system instruction
- [ ] `server/routers/nutrition.py` — all endpoints (meals CRUD, daily/weekly summary, targets, chat, sessions)
- [ ] `server/coaching/tools.py` — add `get_athlete_nutrition_status`
- [ ] Pydantic schemas in `server/models/schemas.py`
- [ ] Shared query functions in `server/queries.py`

**Frontend:**
- [ ] `Nutrition` page with meal timeline, date nav, DailySummaryStrip
- [ ] `MealCapture` (FAB + file input + client-side resize)
- [ ] `MacroCard` (display + inline edit)
- [ ] `MacroAnalysisCard` (loading state)
- [ ] Nutritionist tab in CoachPanel
- [ ] All hooks (`useMeals`, `useLogMeal`, `useUpdateMeal`, `useDeleteMeal`, `useDailyNutrition`, `useNutritionistChat`)
- [ ] Layout/App changes (new tab, TabKey)

**Testing:**
- [ ] Unit tests for photo validation, BMR estimation, caloric balance computation, macro cross-check
- [ ] Integration tests for meal CRUD endpoints, daily/weekly summary, targets
- [ ] Planning tool tests (assert DB writes, not specific macro values — per project testing principles)

### v2 — Polish + Advanced Features (defer)

- Offline support (IndexedDB queuing, retry on connectivity)
- AgentTool wiring (Coach -> Nutritionist for complex fueling reasoning)
- Nutrition-aware coach notes for long workouts
- Dashboard Energy Balance widget with sparkline
- Weekly summary view with stacked bar chart
- Swipe gestures (swipe-to-delete, swipe date nav)
- Rate limiting on photo analysis endpoint
- Gemini vision accuracy benchmarking + model selection

### v2 Rationale

v1 delivers the core value: snap a photo, get macros, track daily intake, chat with the Nutritionist. v2 adds cross-agent intelligence, richer visualizations, and mobile polish. The Agent-to-Agent integration is deferred because it depends on resolving the ADK open questions (multimodal pass-through, AgentTool import path, session isolation) and the core feature should ship independently of those answers.
