# Macro Tracker — AI Integration Design Proposal
> **Version target:** v1.9.x

## 1. Overview

This document describes how the Macro Tracker feature integrates with the platform's AI layer. It covers three major areas:

1. **Vision model integration** — Using Gemini's multimodal capability to analyze meal photos and extract structured macro data
2. **Nutritionist agent design** — A dedicated ADK agent with its own tools, persona, and session/memory services
3. **Agent-to-Agent (A2A) communication** — How the Nutritionist and Cycling Coach exchange data to produce holistic athlete guidance

The design follows the established patterns from `server/coaching/` — callable system instructions, permission-gated tools, singleton `Runner`, `DbSessionService`/`DbMemoryService` backed by Postgres.

---

## 2. Vision Model Integration

### 2.1 Meal Photo Analysis Flow

```
User snaps photo → Frontend sends multipart request → /api/nutrition/analyze-meal
    → Store original image in GCS (gs://jasondel-coach-data/meals/{user_id}/{timestamp}.jpg)
    → Build Content with image Part + structured extraction prompt
    → Nutritionist agent processes via Gemini multimodal
    → Agent calls save_meal_analysis tool with extracted data
    → Return structured result to frontend
```

### 2.2 Multimodal Content Construction

The image is sent to the Nutritionist agent as a `types.Content` message with both an image part and a text part. This goes through the standard ADK `runner.run_async()` — the agent itself decides how to interpret the image using its system instruction.

```python
from google.genai import types

content = types.Content(
    role="user",
    parts=[
        types.Part.from_image(image=types.Image.from_bytes(
            data=image_bytes,
            mime_type="image/jpeg",  # or image/png
        )),
        types.Part.from_text(
            text=user_comment or "Analyze this meal and estimate its macros."
        ),
    ],
)
```

**Note:** `types.Part.from_image` and `types.Image.from_bytes` are the current Gemini SDK patterns. If the ADK `runner.run_async()` passes content through to Gemini natively (which it does — ADK is a thin orchestration layer over Gemini's function-calling protocol), multimodal parts are supported out-of-the-box. **Verify:** Confirm that ADK's `runner.run_async()` forwards non-text parts unchanged to the underlying Gemini model. If not, the image analysis may need to happen as a direct `genai.GenerativeModel.generate_content()` call outside the agent, with results fed into the agent as text context.

### 2.3 System Prompt — Macro Extraction Guidance

The Nutritionist agent's system instruction includes specific guidance on how to analyze meal images. This is embedded in the agent's `instruction` callable (see Section 3.2), not as a per-request prompt:

```
MEAL PHOTO ANALYSIS PROTOCOL:
When you receive a meal photo, analyze it methodically:

1. IDENTIFY each distinct food item visible in the image. List them.
2. ESTIMATE portion sizes using visual cues:
   - Plate size (standard dinner plate ~10in / 25cm)
   - Comparison to utensils, hands, or known objects
   - Depth and density of food
3. For each identified item, estimate:
   - Serving size (grams or common unit)
   - Calories, protein (g), carbohydrates (g), fat (g)
4. SUM totals across all items.
5. Assign a CONFIDENCE score (high / medium / low) based on:
   - Image clarity and lighting
   - Whether items are clearly identifiable vs obscured
   - Whether portion sizes are estimable
   - Whether the meal matches common known patterns

If confidence is LOW, call ask_clarification to ask the user a specific question
before saving. Examples of good clarification questions:
- "Is that grilled chicken or tofu on top of the salad?"
- "About how many ounces of rice would you estimate is on the plate?"
- "I see a sauce — is that olive oil or a cream-based dressing?"

If confidence is MEDIUM or HIGH, proceed directly to save_meal_analysis.
Always call save_meal_analysis with your best estimate — never leave a
meal unlogged. The user can edit later.

LEARNING FROM HISTORY:
Before analyzing a new photo, consider the user's recent meal history
(use get_meal_history). If the meal looks similar to a previously logged
meal, use that as a baseline and adjust for visible differences. This
improves accuracy for users who eat recurring meals (e.g., same breakfast
most days).
```

### 2.4 Response Parsing and Validation

The agent does **not** return structured JSON directly. Instead, it calls the `save_meal_analysis` tool with structured arguments. This follows the existing platform pattern — tools receive structured data via ADK's function-calling protocol, not via parsed LLM text output.

Validation happens at the tool level:

```python
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
) -> dict:
    """Save a meal analysis to the database.

    Args:
        meal_description: Brief natural language description (e.g., "Grilled chicken breast with brown rice and steamed broccoli").
        items: List of individual food items. Each dict has:
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
        meal_type: Optional: "breakfast", "lunch", "dinner", "snack", or "".
        photo_gcs_path: GCS path to the stored photo (set by the API layer, not the user).

    Returns:
        Saved meal record with id and timestamp.
    """
```

**Validation rules (enforced in tool body):**
- `total_calories` must be > 0 and < 10000 (sanity bounds)
- `total_protein_g`, `total_carbs_g`, `total_fat_g` must each be >= 0
- Macro sum cross-check: `(protein*4 + carbs*4 + fat*9)` should be within 15% of `total_calories` — log a warning if not, but still save (LLM estimates are inherently approximate)
- `confidence` must be one of `high`, `medium`, `low`
- `items` must be a non-empty list

---

## 3. Nutritionist Agent Design

### 3.1 Module Structure

Following the established `server/coaching/` pattern:

```
server/nutrition/
├── __init__.py
├── agent.py            # Agent, Runner, chat() — mirrors coaching/agent.py
├── tools.py            # Read-only tools
├── planning_tools.py   # Write tools (permission-gated)
├── session_service.py  # Re-use or extend DbSessionService
└── memory_service.py   # Re-use or extend DbMemoryService
```

### 3.2 Agent Definition

```python
# server/nutrition/agent.py

APP_NAME = "nutrition-coach"

Agent(
    name="nutritionist",
    model=_get_effective_model(),  # same model resolution as cycling_coach
    description="Sports nutritionist specializing in endurance athlete fueling",
    instruction=_build_system_instruction,  # callable, built from DB state
    tools=tools,
)
```

### 3.3 System Instruction (Callable)

Dynamically assembled from DB state, same pattern as the cycling coach's `_build_system_instruction(ctx)`:

```python
def _build_system_instruction(ctx) -> str:
    """Build nutritionist system instruction from athlete data."""
    # Pull athlete weight, FTP, recent training load, daily calorie targets
    # Pull last 3 days of meal history inline (for pattern recognition)
    # Pull recent rides for caloric expenditure context

    return f"""You are an expert sports nutritionist working with an endurance cyclist.

TODAY'S DATE: {today_str} ({today_iso})

ATHLETE PROFILE:
- Weight: {weight_kg} kg ({weight_lbs} lbs)
- FTP: {ftp} W
- Current CTL (training load): {ctl}
- Daily caloric target: {daily_cal_target} kcal (configured)
- Macro targets: P {protein_target}g / C {carb_target}g / F {fat_target}g

RECENT MEALS (last 3 days — use for pattern recognition):
{recent_meals_text}

RECENT TRAINING (last 3 days — for expenditure context):
{recent_rides_text}

YOUR ROLE:
You are the athlete's dedicated nutritionist. Your responsibilities:
1. Analyze meal photos and estimate macronutrient content accurately
2. Track daily and weekly intake trends
3. Identify patterns (repeated meals, nutrient gaps, timing issues)
4. Provide fueling guidance for upcoming workouts
5. Flag concerning patterns (chronic under-fueling, excessive deficit)

MEAL PHOTO ANALYSIS PROTOCOL:
{analysis_protocol}

COMMUNICATION STYLE:
- Be concise and specific with numbers
- When analyzing a meal, lead with the macro summary, then details
- Don't lecture about nutrition basics — this athlete trains seriously
- If you see a pattern (e.g., consistently low protein at breakfast), mention it once, clearly
- Reference specific numbers from recent history when making recommendations

INTER-AGENT COLLABORATION:
You may receive requests from the Cycling Coach agent asking about the athlete's
nutritional status. When responding to coach queries:
- Provide concrete numbers (total kcal today, macro breakdown, timing of last meal)
- Flag any concerns relevant to the coach's question (e.g., "athlete has only consumed
  800 kcal today ahead of tomorrow's planned 4h ride")
- Keep responses data-dense and actionable — the coach needs facts, not advice
"""
```

### 3.4 Tool Inventory

#### Read-Only Tools (`server/nutrition/tools.py`)

| Tool | Args | Returns | Purpose |
|------|------|---------|---------|
| `get_meal_history` | `days_back: int = 7` | List of meal records with macros and timestamps | Browse recent intake |
| `get_daily_macros` | `date: str = ""` | Aggregate macros for a given day (total + per-meal breakdown) | Check daily totals |
| `get_weekly_summary` | `date: str = ""` | 7-day average intake vs targets, daily breakdown | Trend analysis |
| `get_recent_workouts` | `days_back: int = 3` | Recent ride summaries with TSS, duration, estimated caloric burn | Context for fueling advice |
| `get_macro_targets` | — | Current daily macro targets from DB | Reference for gap analysis |
| `get_caloric_balance` | `date: str = ""` | Intake vs estimated expenditure (BMR + ride calories) for a day | Energy balance check |

#### Write Tools — Permission-Gated (`server/nutrition/planning_tools.py`)

| Tool | Args | Returns | Purpose |
|------|------|---------|---------|
| `save_meal_analysis` | See Section 2.4 | Saved record with ID | Persist analyzed meal |
| `update_meal` | `meal_id: int, updates: dict` | Updated record | User corrections to a logged meal |
| `delete_meal` | `meal_id: int` | Confirmation | Remove incorrectly logged meal |
| `set_macro_targets` | `calories: int, protein_g: float, carbs_g: float, fat_g: float` | Updated targets | Adjust daily targets |
| `ask_clarification` | `question: str, context: str` | The question (echoed back for display) | Request user input for ambiguous images |

**`ask_clarification` design note:** This tool doesn't actually query the user — it returns the question as text, which the agent includes in its response. The frontend renders this as a follow-up question. The user's answer comes in the next chat message, along with the original image context from the session history.

#### Tool Schema Example — `get_daily_macros`

ADK infers the JSON schema from the Python function signature and docstring:

```python
def get_daily_macros(date: str = "") -> dict:
    """Get the aggregate macronutrient totals for a specific day.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today if empty.

    Returns:
        Daily macro summary including:
        - total_calories, total_protein_g, total_carbs_g, total_fat_g
        - target_calories, target_protein_g, target_carbs_g, target_fat_g
        - remaining (target minus consumed)
        - meals: list of individual meal records for the day
        - meal_count: number of meals logged
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        meals = conn.execute(
            "SELECT * FROM meal_logs WHERE date = ? AND user_id = ? ORDER BY logged_at",
            (date, "athlete"),
        ).fetchall()

        targets = _get_macro_targets(conn)

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
```

### 3.5 Confidence Scoring and Clarification Logic

The agent handles ambiguity through its system prompt instructions (Section 2.3), not through hardcoded logic. The confidence assessment is part of the LLM's reasoning:

- **High confidence**: Clear photo, recognizable foods, estimable portions. Agent calls `save_meal_analysis` directly.
- **Medium confidence**: Most items identifiable, some uncertainty on portions or ingredients. Agent saves its best estimate and notes uncertainty in `meal_description`.
- **Low confidence**: Obscured items, unusual foods, or unclear portions. Agent calls `ask_clarification` first, then saves after the user responds.

The agent also leverages meal history (via `get_meal_history`) for pattern matching. If a photo looks similar to a previously logged meal, the agent can reference that meal's macros as a baseline — this is especially useful for users who eat the same breakfast repeatedly.

### 3.6 Session and Memory Services

**Session service**: Re-use the existing `DbSessionService` from `server/coaching/session_service.py`. It is keyed by `app_name`, so the nutritionist uses `app_name="nutrition-coach"` to keep sessions separate. The same `chat_sessions` and `chat_events` tables serve both agents.

**Memory service**: Re-use `DbMemoryService` similarly. The `coach_memory` table gets an `app_name` column (or the existing `user_id` + content dedup is sufficient). The nutritionist's conversation memory helps it recall patterns like "you mentioned you're lactose intolerant" across sessions.

---

## 4. Agent-to-Agent (A2A) Communication

### 4.1 Architecture: ADK AgentTool Pattern

Google ADK supports wrapping one agent as a tool for another using `google.adk.tools.agent_tool.AgentTool`. This is the recommended pattern for agent-to-agent communication within the same application:

```python
from google.adk.tools.agent_tool import AgentTool

# In the Cycling Coach's agent setup:
nutritionist_tool = AgentTool(
    agent=_get_nutritionist_agent(),  # the Nutritionist Agent instance
)

# Added to the cycling_coach's tool list:
tools.append(nutritionist_tool)
```

When the Cycling Coach invokes this tool, ADK handles:
1. Marshaling the coach's query into a message to the nutritionist
2. Running the nutritionist agent (with its own tools and context)
3. Returning the nutritionist's response as the tool result

**Verify:** Confirm that `AgentTool` is available in the installed ADK version (`google-cloud-aiplatform[adk]>=1.88.0`). The alternative is `google.adk.agents.LlmAgent` with sub-agents, which uses a different delegation pattern. Check ADK docs for the exact import path.

### 4.2 Communication Direction

**Both directions — Coach asks Nutritionist, Nutritionist asks Coach:**

| Direction | Trigger | Example Query |
|-----------|---------|---------------|
| Coach → Nutritionist | Planning a big workout | "What has the athlete consumed today? Are they fueled enough for tomorrow's 4h endurance ride?" |
| Coach → Nutritionist | Writing coach notes | "Provide fueling guidance for a 3.5h ride at tempo intensity" |
| Coach → Nutritionist | Post-ride analysis | "The athlete bonked at hour 3. What did their pre-ride nutrition look like?" |
| Nutritionist → Coach | Assessing caloric needs | "What is the athlete's planned training load for the next 3 days?" |
| Nutritionist → Coach | Setting macro targets | "What is the current weekly TSS target and training phase?" |

### 4.3 Implementation: Bidirectional AgentTool Wiring

The challenge with bidirectional `AgentTool` is circular references — the coach agent needs the nutritionist as a tool, and vice versa. Two approaches:

**Approach A — Lightweight data tools instead of full AgentTool (Recommended):**

Rather than wiring each agent as a tool of the other, give each agent read-only data tools that query the other domain's database tables:

```python
# In Cycling Coach's tools.py — add a nutrition data accessor:
def get_athlete_nutrition_status(date: str = "") -> dict:
    """Get the athlete's nutritional intake status for fueling decisions.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        Caloric intake, macro breakdown, meal count, and last meal time for the day.
    """
    # Direct DB query against meal_logs table — no agent invocation needed
    ...

# In Nutritionist's tools.py — add a training data accessor:
def get_upcoming_training_load(days_ahead: int = 3) -> dict:
    """Get upcoming planned workouts and training load for fueling guidance.

    Args:
        days_ahead: Number of days to look ahead.

    Returns:
        Planned workouts with TSS, duration, and type for each day.
    """
    # Direct DB query against planned_workouts table
    ...
```

**Approach B — Unidirectional AgentTool (Coach → Nutritionist only):**

Only the Coach gets the Nutritionist as an AgentTool. The Nutritionist gets lightweight read-only tools for training data (no circular dependency):

```python
# Cycling Coach agent setup:
from server.nutrition.agent import get_nutritionist_agent

nutritionist_tool = AgentTool(agent=get_nutritionist_agent())
tools.append(nutritionist_tool)

# Nutritionist agent — no AgentTool reference to coach, just data tools:
tools = [
    get_meal_history,
    get_daily_macros,
    get_upcoming_training_load,  # reads from planned_workouts directly
    get_recent_workouts,         # reads from rides directly
    ...
]
```

### 4.4 Recommended Approach: Hybrid (Approach A primary, Approach B for complex reasoning)

**Primary (90% of interactions):** Use Approach A — lightweight cross-domain data tools. This avoids the latency and token cost of nested agent invocations. When the coach needs nutrition data, it calls `get_athlete_nutrition_status()` directly from the DB.

**Complex reasoning (10%):** Use Approach B — the Coach invokes the Nutritionist via `AgentTool` when it needs the nutritionist to *reason*, not just query data. Example: "Given the athlete's nutrition over the past 3 days and tomorrow's 4h ride, write fueling guidance for the coach notes." This requires the nutritionist's system prompt, meal history context, and reasoning ability — a simple data tool isn't sufficient.

```python
# Cycling Coach agent setup — both patterns:
tools = [
    # ... existing coaching tools ...
    get_athlete_nutrition_status,   # Approach A: direct DB query for simple checks
    AgentTool(agent=nutritionist),  # Approach B: full agent for complex reasoning
]
```

The coach's system prompt instructs when to use each:

```
NUTRITION INTEGRATION:
- For quick checks (has the athlete eaten today? total calories so far?),
  use get_athlete_nutrition_status — it's fast and doesn't require the nutritionist.
- For complex fueling guidance (pre-ride nutrition plans, recovery meal advice,
  multi-day fueling strategies), delegate to the nutritionist agent — it has
  specialized knowledge and meal history context.
```

### 4.5 A2A Message Schemas

When using `AgentTool`, the message format is handled by ADK — the coach sends a natural language query, and the nutritionist responds in natural language. There is no custom schema needed for AgentTool communication.

For the lightweight data tools (Approach A), the return schemas are standard Python dicts:

```python
# get_athlete_nutrition_status return schema:
{
    "date": "2026-04-09",
    "meals_logged": 3,
    "total_calories": 1850,
    "total_protein_g": 145.2,
    "total_carbs_g": 210.5,
    "total_fat_g": 62.3,
    "target_calories": 2800,
    "remaining_calories": 950,
    "last_meal_at": "2026-04-09T12:30:00",
    "last_meal_description": "Grilled chicken salad with quinoa",
    "caloric_balance": {
        "intake": 1850,
        "estimated_bmr": 1750,
        "ride_expenditure": 1200,
        "net_balance": -1100
    }
}

# get_upcoming_training_load return schema:
{
    "days": [
        {
            "date": "2026-04-10",
            "planned_tss": 180,
            "planned_duration_h": 4.0,
            "workout_name": "Endurance Base",
            "workout_type": "endurance",
            "estimated_calories": 2400,
            "coach_notes": "Long steady ride, Z2 power"
        },
        ...
    ],
    "total_planned_tss_3d": 280,
    "total_estimated_calories_3d": 3800
}
```

---

## 5. Workout Planning Integration

### 5.1 Fueling Tips in Coach Notes

When the Cycling Coach creates or modifies workouts via `generate_week_from_spec` or `replace_workout`, and the workout is longer than 90 minutes, the coach should query nutritional context and include fueling guidance in the coach notes.

**Modified coach system prompt addition:**

```
NUTRITION-AWARE COACH NOTES:
For workouts longer than 90 minutes, include fueling guidance in your coach notes:
1. Check the athlete's recent intake via get_athlete_nutrition_status
2. For rides > 2 hours, include:
   - Pre-ride meal recommendation (timing + approximate calories)
   - On-bike fueling target (calories/hour — typically 60-90g carbs/hour for endurance)
   - Post-ride recovery nutrition window
3. If the athlete's recent intake suggests under-fueling, flag this prominently
4. For particularly long or intense sessions (>3h or IF >0.85), delegate to
   the nutritionist for detailed fueling guidance
```

**Example coach note output (generated by LLM, not hardcoded):**

```
Saturday 4h Endurance Ride — Z2 steady state

Target: 4 hours, TSS ~180, IF 0.65-0.70
Keep power between 165-185w. Cadence 85-95. No surges above tempo.

Fueling plan:
- Pre-ride (2h before): 600-800 kcal meal, carb-heavy (oatmeal, banana, toast)
- On-bike: 60-80g carbs/hour (~250-320 kcal/h) — gels, bars, or drink mix
- Total on-bike target: ~1000-1200 kcal over 4 hours
- Post-ride: recovery shake within 30 min, full meal within 2 hours

Note: You logged only 1,400 kcal yesterday — make sure to eat well tonight
and have a solid breakfast. You need ~2,400 kcal on the bike alone tomorrow.
```

### 5.2 Integration Point — `set_workout_coach_notes`

The existing `set_workout_coach_notes` tool is the integration point. No new tools are needed for this workflow. The coach simply:

1. Calls `get_athlete_nutrition_status` (or the nutritionist AgentTool for complex guidance)
2. Incorporates the nutritional context into the notes
3. Calls `set_workout_coach_notes` as it already does

---

## 6. Pre-Workout Fuel Check

### 6.1 When Coach Checks Fueling

The Cycling Coach should check nutritional readiness when:
- Planning a training block (`generate_week_from_spec` for the coming week)
- The athlete asks about tomorrow's workout
- Before a particularly demanding session (TSS > 150 or duration > 3h)

### 6.2 Fuel Check Flow

```
Coach receives request to plan/discuss upcoming workout
    → Coach calls get_athlete_nutrition_status(date=today)
    → Checks: has athlete consumed enough calories relative to training load?
    → If concerning (e.g., < 50% of caloric target by evening, or negative energy balance
       > 1000 kcal for 2+ consecutive days):
        → Coach flags this in its response:
          "Heads up — you've only logged 1,200 kcal today and you have a
           4h ride planned tomorrow (estimated burn: 2,400 kcal). Consider
           a larger dinner tonight and a carb-heavy breakfast."
    → If adequate: no special mention needed
```

### 6.3 Decision Logic — Agent-Side, Not Code-Side

Per the project's architectural principles ("AGENT DECIDES, TOOLS EXECUTE"), the fuel check logic lives in the coach's system prompt, not in Python code. The tools expose the data; the LLM reasons about whether intake is adequate:

```
PRE-WORKOUT FUEL CHECK:
Before discussing any upcoming workout with TSS > 100 or duration > 2 hours,
check the athlete's recent nutrition:
1. Call get_athlete_nutrition_status for today
2. Call get_daily_macros for yesterday (via nutritionist or direct tool)
3. Consider: Is the athlete in significant caloric deficit? Is carb intake
   sufficient for glycogen replenishment?
4. If intake looks low relative to training demands, proactively mention it.
   Don't wait for the athlete to ask.
5. For multi-day training blocks, check the last 2-3 days of intake vs
   training load — chronic under-fueling is more concerning than a single
   low day.
```

---

## 7. API Endpoints

### 7.1 New Router: `/api/nutrition`

Following the `server/routers/coaching.py` pattern:

```python
# server/routers/nutrition.py

@router.post("/chat")
async def nutrition_chat(req: NutritionChatRequest, user: CurrentUser):
    """Send a message (text and/or image) to the nutritionist agent."""
    response = await nutrition_agent.chat(
        message=req.message,
        image_data=req.image_data,       # base64-encoded image bytes
        image_mime_type=req.image_mime_type,
        user_id=user.email,
        session_id=req.session_id or str(uuid.uuid4()),
        user=user,
    )
    return NutritionChatResponse(response=response.text, session_id=response.session_id)

@router.post("/analyze-meal")
async def analyze_meal(
    file: UploadFile,
    comment: str = Form(""),
    meal_type: str = Form(""),
    user: CurrentUser = Depends(require_read),
):
    """Analyze a meal photo and return macro estimates.

    This is a convenience endpoint that:
    1. Stores the image in GCS
    2. Sends it to the nutritionist agent for analysis
    3. Returns the structured meal analysis
    """
    ...

# Standard session CRUD — same pattern as coaching
@router.get("/sessions")
@router.get("/sessions/{session_id}")
@router.delete("/sessions/{session_id}")

# Meal log CRUD (direct DB, no agent)
@router.get("/meals")                  # List meals with date range filter
@router.get("/meals/{meal_id}")        # Get single meal with items
@router.put("/meals/{meal_id}")        # User edits a logged meal
@router.delete("/meals/{meal_id}")     # Delete a logged meal

# Macro targets
@router.get("/targets")               # Current daily macro targets
@router.put("/targets")               # Update targets

# Daily/weekly summaries
@router.get("/daily-summary")         # Aggregate macros for a date
@router.get("/weekly-summary")        # 7-day trend with daily breakdown
```

### 7.2 Request/Response Schemas

```python
class NutritionChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    image_data: Optional[str] = None       # base64 encoded
    image_mime_type: Optional[str] = None  # "image/jpeg" or "image/png"

class NutritionChatResponse(BaseModel):
    response: str
    session_id: str

class MealAnalysisResponse(BaseModel):
    meal_id: int
    description: str
    items: list[MealItem]
    total_calories: int
    total_protein_g: float
    total_carbs_g: float
    total_fat_g: float
    confidence: str   # "high", "medium", "low"
    meal_type: str
    photo_url: str
    logged_at: str    # ISO 8601
    agent_notes: str  # any commentary from the nutritionist

class MealItem(BaseModel):
    name: str
    serving_size: str
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
```

---

## 8. Database Tables

```sql
-- Daily macro targets (configurable, one row per user)
CREATE TABLE macro_targets (
    user_id TEXT PRIMARY KEY DEFAULT 'athlete',
    calories INTEGER NOT NULL DEFAULT 2500,
    protein_g REAL NOT NULL DEFAULT 150,
    carbs_g REAL NOT NULL DEFAULT 300,
    fat_g REAL NOT NULL DEFAULT 80,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Individual meal logs
CREATE TABLE meal_logs (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    date DATE NOT NULL,
    logged_at TIMESTAMP NOT NULL DEFAULT NOW(),
    meal_type TEXT,                          -- breakfast, lunch, dinner, snack
    description TEXT NOT NULL,
    total_calories INTEGER NOT NULL,
    total_protein_g REAL NOT NULL,
    total_carbs_g REAL NOT NULL,
    total_fat_g REAL NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',  -- high, medium, low
    photo_gcs_path TEXT,                     -- gs://jasondel-coach-data/meals/...
    agent_notes TEXT,                        -- nutritionist commentary
    edited_by_user BOOLEAN DEFAULT FALSE     -- true if user manually corrected
);

-- Individual food items within a meal
CREATE TABLE meal_items (
    id SERIAL PRIMARY KEY,
    meal_id INTEGER NOT NULL REFERENCES meal_logs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    serving_size TEXT,
    calories INTEGER NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL
);

-- Index for common queries
CREATE INDEX idx_meal_logs_date ON meal_logs(date);
CREATE INDEX idx_meal_logs_user_date ON meal_logs(user_id, date);
```

---

## 9. Design Tradeoffs

### 9.1 Separate Agent vs. Single Agent with Nutrition Tools

| Factor | Separate Nutritionist Agent | Single Agent + Nutrition Tools |
|--------|---------------------------|-------------------------------|
| **System prompt** | Focused, domain-specific. ~800 tokens of nutrition expertise without diluting the coaching prompt. | Combined prompt grows large. Nutrition instructions compete with coaching instructions for attention. |
| **Tool count** | Each agent has ~15-20 tools. Manageable for Gemini function-calling. | Combined: ~35+ tools. Higher risk of tool confusion and slower selection. |
| **Session/memory** | Separate conversation threads. User can have parallel coaching and nutrition conversations. | Single conversation mixes topics. Hard to search memory for nutrition-specific history. |
| **Latency (cross-agent)** | AgentTool adds one extra LLM round-trip when agents need to collaborate. | No cross-agent latency — single agent has all tools. |
| **Maintainability** | Independent development and testing. Nutrition changes don't risk coaching regressions. | Single codebase, simpler deployment. |

**Decision: Separate agents.** The system prompt focus and tool isolation benefits outweigh the occasional cross-agent latency cost. The hybrid approach (Section 4.4) minimizes cross-agent calls by using direct DB tools for simple data lookups.

### 9.2 Real-Time A2A vs. Async Data Sharing

| Factor | Real-Time (AgentTool) | Async (Shared DB only) |
|--------|----------------------|------------------------|
| **Latency** | Adds 2-5s per nested agent call | Zero — just DB reads |
| **Reasoning quality** | Nutritionist can reason about complex queries | Limited to pre-computed summaries |
| **Complexity** | AgentTool wiring, potential circular deps | Simple, no agent coordination needed |
| **Use cases covered** | All — simple and complex | Simple lookups only |

**Decision: Hybrid.** Direct DB tools for the 90% case (data lookups), AgentTool for the 10% case (complex nutritional reasoning). See Section 4.4.

### 9.3 Structured Output vs. Free-Form LLM Response for Macro Extraction

| Factor | ADK `output_schema` | Tool-based extraction (current pattern) |
|--------|---------------------|----------------------------------------|
| **Reliability** | Gemini enforces JSON schema — guaranteed structure | LLM must decide to call the tool correctly — could skip or malformat |
| **Flexibility** | Rigid schema — can't include free-form notes alongside structured data | Agent can call `save_meal_analysis` AND add conversational commentary |
| **Pattern consistency** | New pattern, not used anywhere in codebase | Matches existing coaching agent — tools receive structured args |
| **Error handling** | Schema validation at model level | Validation in tool body — can return error messages for retry |

**Decision: Tool-based extraction (existing pattern).** The `save_meal_analysis` tool receives structured data via ADK function-calling, which already provides schema enforcement. Using `output_schema` would force all agent output into a rigid JSON format, losing the conversational response that accompanies the analysis. The tool pattern gives us structured storage AND natural language response.

### 9.4 Image Processing: Agent-Internal vs. Pre-Processing Pipeline

| Factor | Agent-internal (Gemini vision) | Pre-processing (separate vision call) |
|--------|-------------------------------|---------------------------------------|
| **Simplicity** | One LLM call — image + prompt → structured macros | Two calls: vision API → labels/items, then agent → macros |
| **Context** | Agent has full session context (dietary history, preferences) when analyzing | Vision call is stateless; needs a second pass for context |
| **Cost** | Single Gemini call (multimodal pricing) | Two calls — potentially cheaper if vision-only model is used for step 1 |
| **Accuracy** | Gemini can use meal history and athlete context to improve estimates | Context-free vision may miss nuances (e.g., "that's always a 6oz portion") |

**Decision: Agent-internal.** The nutritionist agent processes the image directly via multimodal `Content`. This lets the agent use session context and meal history to improve accuracy. A separate vision pipeline adds complexity without meaningful benefit for this use case.

---

## 10. Open Questions / Items to Verify

1. **ADK multimodal pass-through**: Confirm that `runner.run_async()` forwards image parts in `Content` to Gemini unchanged. If ADK strips non-text parts, the image analysis step needs to happen outside the agent loop.

2. **AgentTool import path**: Verify `google.adk.tools.agent_tool.AgentTool` exists in the installed ADK version. Alternative: `google.adk.tools.AgentTool` or a different delegation pattern.

3. **AgentTool session isolation**: When Coach invokes Nutritionist via AgentTool, does the nutritionist get its own session, or does it share the coach's session? This affects memory and context isolation.

4. **Gemini vision accuracy for food**: Benchmark Gemini 2.5 Flash's food recognition accuracy against a test set of 50-100 meal photos with known macros. If accuracy is insufficient, consider Gemini 2.5 Pro for the nutritionist agent (at higher cost).

5. **GCS signed URLs**: For displaying meal photos in the frontend, determine whether to use signed URLs (time-limited) or a proxy endpoint that streams from GCS. Signed URLs are simpler but expire.

6. **Rate limiting**: Meal photo analysis is more expensive than text-only coaching chat (multimodal tokens). Consider per-user rate limits on `/api/nutrition/analyze-meal` (e.g., 20 analyses/day).

7. **Voice comments**: The optional voice note in Flow B is passed directly to Gemini as a multimodal `Part` alongside the image — no transcription step. The backend receives the audio blob (`audio/webm` or `audio/mp4`) from the upload and includes it in the `contents` array sent to the agent. This is native to Gemini's multimodal capability and keeps the analysis in a single model call. The agent sees both the visual and audio context simultaneously, which is the intended use: the user's verbal description helps resolve ambiguities the image alone cannot (e.g., "that's the low-fat version" or "about 6 ounces"). Audio is not stored long-term — it is used only during the analysis request.
