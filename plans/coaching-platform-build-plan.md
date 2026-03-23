# Coaching Platform Build Plan

## Vision

A web-based cycling coaching platform that turns raw ride data into actionable training insights. The system serves as a persistent coaching relationship — it knows your history, understands your physiology as a 50-year-old experienced rider, tracks your progression toward Big Sky Biggie (late August 2026), and adapts when life gets in the way.

This is not a generic training app. It's built around one athlete's data, one A-race, and the specific coaching insights we've already established from analyzing a full year of training (see `season_analysis.md`).

---

## Tech Stack

- **Backend**: Python + FastAPI (we already have Python data processing; FastAPI is lightweight, async, easy to test)
- **Database**: SQLite (simple, portable, no server — perfect for single-athlete use)
- **Frontend**: HTML + vanilla JS + Chart.js (no framework overhead — fast to build, easy to maintain)
- **AI Coaching**: Claude via GCP Vertex AI (using Application Default Credentials)
- **Testing**: pytest (backend), simple integration tests for API endpoints
- **Package management**: pip with requirements.txt
- **Auth**: GCP ADC (`google-auth` + `anthropic[vertex]`) — no API keys to manage, uses `gcloud auth application-default login`

---

## Phase 0: Organize the Chaos

**Goal**: Get the project directory under control before writing a single line of app code.

### Current state (598+ files in root):
- 291 `.FIT` files (raw Garmin exports)
- 293 `.json` files (converted ride data + 2 report JSONs)
- 7 `.md` files (snapshots, analysis)
- 5 `.py` files (one-off scripts)
- 1 `.js` file (TrainingPeaks scraper)
- 1 `.zwo` file (stray planned workout)
- 1 `.txt` file
- `planned_workouts/` directory (176 ZWO files)

### Target structure:
```
coach/
├── CLAUDE.md                    # Project instructions for Claude Code
├── README.md                    # Project overview
├── requirements.txt             # Python dependencies
├── plans/                       # Build plans (this file)
│   └── coaching-platform-build-plan.md
├── data/
│   ├── fit/                     # Raw .FIT files (291 files)
│   ├── rides/                   # Converted .json ride files (291 files)
│   ├── planned_workouts/        # .zwo planned workout files (176 files)
│   └── coach.db                 # SQLite database (created in Phase 1)
├── scripts/                     # One-off data processing scripts
│   ├── convert_fit_to_json.py
│   ├── convert_fit.py
│   ├── find_structured_workouts.py
│   ├── inspect_fit.py
│   └── process_month.js
├── archive/                     # Old snapshots, notes, stray files
│   ├── snapshot.md
│   ├── snapshot2.md
│   ├── snapshot_calendar.md
│   ├── snapshot_dialog.md
│   ├── snapshot_restart.md
│   ├── stalled_snapshot.md
│   ├── planned_workout.zwo
│   └── already_downloaded.txt
├── analysis/                    # Analysis outputs
│   ├── season_analysis.md
│   ├── training_report.json
│   ├── pmc_data.json
│   └── analyze.py               # Standalone analysis script
├── server/                      # FastAPI backend
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entry point
│   ├── database.py              # SQLite models and connection
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── rides.py             # Ride data endpoints
│   │   ├── planning.py          # Training plan endpoints
│   │   ├── analysis.py          # Analysis/chart data endpoints
│   │   └── coaching.py          # AI coaching chat endpoint
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ride_service.py      # Ride data processing
│   │   ├── pmc_service.py       # CTL/ATL/TSB calculations
│   │   ├── power_curve.py       # Power duration curve
│   │   ├── route_matcher.py     # GPS route matching
│   │   ├── ef_tracker.py        # Efficiency factor tracking
│   │   └── workout_generator.py # ZWO file generation
│   ├── llm/                     # LLM provider abstraction
│   │   ├── __init__.py
│   │   ├── base.py              # LLMProvider Protocol + ChatMessage/ChatResponse models
│   │   ├── vertex_claude.py     # Claude via Vertex AI (ADC)
│   │   ├── vertex_gemini.py     # Gemini via Vertex AI (ADC) — future
│   │   ├── ollama.py            # Local open-source models — future
│   │   └── factory.py           # get_provider(config) → LLMProvider
│   └── models/
│       ├── __init__.py
│       └── schemas.py           # Pydantic models
├── web/                         # Frontend
│   ├── index.html               # Main SPA shell
│   ├── css/
│   │   └── styles.css
│   └── js/
│       ├── app.js               # Main app logic, routing
│       ├── charts.js            # Chart.js configurations
│       ├── coaching.js          # Chat interface
│       └── calendar.js          # Training calendar view
└── tests/
    ├── __init__.py
    ├── conftest.py              # Shared fixtures
    ├── test_database.py
    ├── test_ride_service.py
    ├── test_pmc_service.py
    ├── test_power_curve.py
    ├── test_route_matcher.py
    ├── test_ef_tracker.py
    ├── test_workout_generator.py
    ├── test_llm_factory.py
    ├── test_llm_mock.py
    └── test_api.py
```

### Steps:
1. Create the directory structure
2. Move `.FIT` files to `data/fit/`
3. Move ride `.json` files to `data/rides/` (exclude `training_report.json` and `pmc_data.json`)
4. Move `planned_workouts/` to `data/planned_workouts/`
5. Move scripts to `scripts/`
6. Move analysis outputs to `analysis/`
7. Move old snapshots/stray files to `archive/`
8. Verify nothing is broken (file counts match)
9. Create `.gitignore` (ignore `data/fit/`, `*.db`, `__pycache__`, `.env`)
10. Initialize git repo
11. Create `CLAUDE.md` with project context and coaching knowledge

### Tests:
- Verify file counts after move (291 FIT, 291 ride JSON, 176 ZWO)
- Verify `analyze.py` still works with updated paths

### CLAUDE.md contents (key coaching context to persist):
- Athlete profile: 50yo male, ~163 lbs, 5'10", FTP history, W/kg
- A-race: Big Sky Biggie, late August 2026, ~50mi MTB, ~6000ft climbing
- Season history summary: 581h, peaked CTL 106.8, current CTL ~21
- Key coaching principles established from analysis:
  - 12-14h/week sweet spot (not 15-19)
  - 3-week build / 1-week recovery cycles
  - Needs structured intervals, not just terrain-driven intensity
  - 48-72h recovery after hard efforts
  - Polarized approach: easy days easy, hard days hard
  - Weight is a lever: every pound matters on climbs
  - Power meter is essential — fix it
- Periodization plan: Base Rebuild → Build 1 → Build 2 → Peak → Taper
- How to handle off-plan days: don't panic, adjust the week, protect key workouts

---

## Phase 1: Data Pipeline & Database

**Goal**: Process all ride data into SQLite so the app has fast, queryable access to everything.

### Steps:

#### 1a. Database schema design
Create SQLite tables:

```
rides:
  id, date, filename, sport, sub_sport, duration_s, distance_m,
  avg_power, normalized_power, max_power, avg_hr, max_hr, avg_cadence,
  total_ascent, total_descent, total_calories, tss, intensity_factor,
  ftp, total_work_kj, training_effect, variability_index,
  best_1min_power, best_5min_power, best_20min_power, best_60min_power,
  weight, start_lat, start_lon

ride_records:
  id, ride_id, timestamp, power, heart_rate, cadence, speed,
  altitude, distance, lat, lon, temperature

planned_workouts:
  id, date, name, sport, total_duration_s, workout_xml

daily_metrics:
  date, total_tss, ctl, atl, tsb, weight, notes

athlete_log:
  id, date, type (weight/note/injury/life_event), value, note

power_bests:
  id, ride_id, date, duration_s, power
```

- **Tests**: Schema creation, insert/query round-trip

#### 1b. Data ingestion script
- Download source data from GCS bucket (`gs://jasondel-coach-data`):
  - `gs://jasondel-coach-data/json/` → `data/rides/` (291 ride JSON files)
  - `gs://jasondel-coach-data/planned_workouts/` → `data/planned_workouts/` (176 ZWO files)
- Read all ride JSON files, extract session + record data
- Compute derived metrics (power bests, zone distribution per ride)
- Insert into SQLite
- Read all ZWO files, parse and insert
- Compute and store daily PMC (CTL/ATL/TSB)

- **Tests**: Ingestion of a single known ride, verify all fields. Ingestion of a ZWO file. PMC calculation against known values.

#### 1c. Incremental update support
- Track which files have been ingested (by filename hash)
- Support adding new rides without re-processing everything
- Script: `python -m server.ingest` or `python scripts/ingest.py`

- **Tests**: Re-run ingestion, verify no duplicates. Add a new file, verify it's picked up.

---

## Phase 2: Backend API

**Goal**: FastAPI server exposing all training data through clean REST endpoints.

### Steps:

#### 2a. Core API scaffold
- FastAPI app with CORS (for local frontend)
- SQLite connection management
- Static file serving for frontend
- Health check endpoint

- **Tests**: App starts, health check returns 200

#### 2b. Ride data endpoints
```
GET /api/rides                    — list rides (filterable by date range, sport)
GET /api/rides/:id                — single ride detail with records
GET /api/rides/summary/weekly     — weekly aggregations
GET /api/rides/summary/monthly    — monthly aggregations
```

- **Tests**: List rides returns correct count. Filter by date range works. Weekly summary matches analyze.py output.

#### 2c. PMC endpoints
```
GET /api/pmc                      — daily CTL/ATL/TSB (date range filterable)
GET /api/pmc/current              — today's fitness/fatigue/form
```

- **Tests**: PMC values match known calculations. Current endpoint returns latest values.

#### 2d. Analysis endpoints
```
GET /api/analysis/power-curve     — best power at standard durations
GET /api/analysis/power-curve/history — power curve over time (by month)
GET /api/analysis/zones           — zone distribution (filterable by date range)
GET /api/analysis/efficiency      — EF (NP/avgHR) over time
GET /api/analysis/ftp-history     — FTP progression
GET /api/analysis/route-matches   — rides on similar routes
```

- **Tests**: Power curve returns values for 1min/5min/20min. Zone distribution sums to 100%.

#### 2e. Planning endpoints
```
GET  /api/plan                    — current training plan / periodization
GET  /api/plan/week/:date         — planned workouts for a given week
POST /api/plan/adjust             — replan around a missed day or life event
GET  /api/plan/compliance         — planned vs actual
POST /api/workouts/generate       — generate ZWO file for a prescribed workout
```

- **Tests**: Plan returns periodization phases. Generate produces valid ZWO XML.

---

## Phase 3: Frontend — Dashboard

**Goal**: Single-page web app with a dashboard showing key metrics at a glance.

### Steps:

#### 3a. App shell and navigation
- Single HTML page with tab/section navigation
- Sections: Dashboard, Calendar, Rides, Analysis, Plan, Coach
- Responsive layout (works on phone for quick checks)
- Chart.js loaded via CDN

- **Tests**: Page loads, all sections render without errors

#### 3b. Dashboard view
- Current CTL / ATL / TSB with color coding (green = fresh, red = fatigued)
- This week's summary (hours, TSS, rides)
- FTP and W/kg display
- "Next planned workout" card
- PMC chart (line chart: CTL, ATL, TSB over full season)
- Monthly volume bar chart

- **Tests**: Dashboard fetches data from API and renders charts

#### 3c. Calendar view
- Month view showing each day
- Color-coded by: planned workout, completed ride, rest day, missed
- Click a day to see ride details or planned workout
- Shows weekly TSS totals in sidebar

- **Tests**: Calendar renders correct days. Planned vs actual color coding is correct.

#### 3d. Ride list and detail view
- Sortable/filterable table of all rides
- Click to see: power/HR/cadence chart over time, map (if GPS), zone breakdown, key metrics
- Compare two rides side by side

- **Tests**: Ride list loads. Detail view shows correct data for a known ride.

---

## Phase 4: Advanced Analysis Tools

**Goal**: The specific tools identified in the season analysis.

### Steps:

#### 4a. Power Duration Curve
- Chart showing best power at 5s, 30s, 1min, 5min, 20min, 60min
- Overlay multiple time periods (e.g., last 30 days vs last 90 days vs all-time)
- Identify strengths/weaknesses (are you a diesel or a sprinter?)
- Show W/kg alongside raw watts

- **Tests**: Power curve computed correctly against known ride data. Overlay filtering works.

#### 4b. Efficiency Factor Tracking
- EF = Normalized Power / Average Heart Rate
- Plot EF over time for comparable rides (similar duration, same sport)
- Rising EF at same HR = improving aerobic fitness (independent of FTP test)
- Flag decoupling: when HR drifts up but power stays flat in long rides (aerobic weakness)

- **Tests**: EF calculated correctly for sample rides. Trend direction identified correctly.

#### 4c. Route Matching & Comparison
- Compare rides on the same route using GPS proximity matching
- Algorithm: downsample GPS to ~100 points, compute similarity score
- Show: same climb/segment, power comparison over time
- "You rode Leverich Canyon 12 times this year — here's your progression"

- **Tests**: Two rides on same route match with high score. Different routes score low. Power comparison shows correct values.

#### 4d. Workout Generator
- Input: workout type (Z2 endurance, threshold intervals, VO2max, etc.), duration
- Output: valid ZWO file based on current FTP
- Presets for the key workout types in the plan:
  - Z1/Z2 Endurance (various durations)
  - 2x20 Threshold
  - 3x15 Sweet Spot
  - 4x4min VO2max
  - Race simulation (variable terrain)
  - Recovery spin
- Download button to save ZWO to device

- **Tests**: Generated ZWO is valid XML. Power targets are correct for given FTP. Duration matches request.

---

## Phase 5: AI Coaching Chat

**Goal**: Interactive coaching interface powered by an LLM, with full training context. The LLM provider is abstracted so we can swap between Claude on Vertex, Gemini, open-source models, etc. without touching any coaching logic.

### Steps:

#### 5a. LLM Provider Abstraction Layer (`server/llm/`)

This is the foundation — all coaching logic talks to an `LLMProvider` protocol, never to a specific SDK.

**`base.py` — The contract:**
```python
from typing import Protocol, AsyncIterator
from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: str          # "system" | "user" | "assistant"
    content: str

class ChatResponse(BaseModel):
    content: str
    model: str         # actual model that responded
    provider: str      # "vertex-claude" | "vertex-gemini" | "ollama" | etc.
    usage: dict        # token counts, cost estimate if available

class LLMProvider(Protocol):
    """Any LLM backend must implement this interface."""

    async def chat(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse: ...

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]: ...

    def provider_name(self) -> str: ...
```

**`vertex_claude.py` — First implementation (ships in Phase 5):**
- Uses `anthropic[vertex]` SDK with ADC
- `AnthropicVertex(project_id=..., region=...)` — values from config
- Requires `gcloud auth application-default login` once
- Maps `ChatMessage` ↔ Anthropic message format

**`vertex_gemini.py` — Future implementation:**
- Uses `google-cloud-aiplatform` SDK with ADC
- Same auth mechanism, same GCP project
- Maps `ChatMessage` ↔ Gemini message format

**`ollama.py` — Future implementation:**
- HTTP calls to local Ollama server
- For running Llama, Mistral, etc. locally
- No auth required

**`factory.py` — Provider selection:**
```python
def get_provider(config: AppConfig) -> LLMProvider:
    match config.llm_provider:
        case "vertex-claude":
            return VertexClaudeProvider(config.gcp_project, config.gcp_region, config.claude_model)
        case "vertex-gemini":
            return VertexGeminiProvider(config.gcp_project, config.gcp_region, config.gemini_model)
        case "ollama":
            return OllamaProvider(config.ollama_host, config.ollama_model)
        case _:
            raise ValueError(f"Unknown LLM provider: {config.llm_provider}")
```

**`config.yaml` (or env vars):**
```yaml
llm:
  provider: "vertex-claude"          # swap this one line to change models
  gcp_project: "your-project-id"
  gcp_region: "us-central1"
  claude_model: "claude-sonnet-4-20250514"
  # gemini_model: "gemini-2.0-flash"  # uncomment when ready
  # ollama_host: "http://localhost:11434"
  # ollama_model: "llama3"
```

**Why this works:**
- Coaching logic (`coach_ai.py`) only imports `LLMProvider`, `ChatMessage`, `ChatResponse`
- Swapping models = changing one config value
- Adding a new provider = one new file implementing the protocol
- The protocol uses Python's structural typing — no inheritance required, any class with the right methods works
- Pydantic models at the boundary ensure type safety regardless of provider

- **Tests**:
  - `test_vertex_claude.py`: Provider initializes with ADC, sends a message, returns `ChatResponse`
  - `test_factory.py`: Factory returns correct provider for each config value
  - `test_llm_mock.py`: Mock provider implements protocol correctly, coaching logic works with mock (no real API calls in unit tests)

#### 5b. Coaching system prompt construction
Build a dynamic system prompt that includes:
- Athlete profile (age, weight, FTP, W/kg)
- Current fitness state (CTL, ATL, TSB)
- This week's completed rides
- This week's remaining planned workouts
- Periodization phase and targets
- Recent trends (last 4 weeks of volume/TSS)
- Key coaching principles from season analysis
- Known athlete tendencies (e.g., overreaches, needs recovery reminders)

The system prompt is provider-agnostic — it's plain text that works with any model.

- **Tests**: System prompt includes current CTL/ATL/TSB. System prompt updates when new rides are added.

#### 5c. Chat API endpoint
```
POST /api/coaching/chat           — send message, get coaching response
GET  /api/coaching/history        — conversation history
POST /api/coaching/replan         — "I missed Tuesday and Wednesday, what now?"
GET  /api/coaching/config         — current LLM provider info
```

- The coaching router gets an `LLMProvider` via dependency injection (FastAPI `Depends`)
- No router code references any specific SDK
- Response includes `provider` and `model` fields so the frontend can show what's answering

- **Tests**: Chat returns a response. Replan adjusts the week's remaining workouts. Provider info endpoint returns correct config.

#### 5d. Chat frontend
- Chat interface in the "Coach" tab
- Persistent conversation history (stored in SQLite)
- Shows which model is responding (small badge: "Claude 3.5 Sonnet via Vertex AI")
- Quick-action buttons:
  - "What should I ride today?"
  - "I missed a workout, help me replan"
  - "How am I tracking toward my goal?"
  - "I have 90 minutes, what's the best use of time?"
  - "Rate my last ride"
- Coach can proactively surface insights: "You've been riding 3 days straight at high TSS — consider an easy day tomorrow"

- **Tests**: Chat sends and receives messages. Quick actions produce relevant responses.

#### 5e. Athlete log integration
- Log weight, notes, life events, injuries through the chat or a form
- "Log: 162 lbs this morning" → stored in athlete_log
- "Note: knee felt tight on the descent" → stored and surfaced to coach
- Coach references these in future advice

- **Tests**: Weight entry stored correctly. Coach references recent log entries.

---

## Phase 6: Training Plan Management

**Goal**: Full periodization plan with week-by-week workouts, adaptable to real life.

### Steps:

#### 6a. Periodization engine
- Implement the 5-phase plan from season analysis:
  - Base Rebuild (5 wks) → Build 1 (5 wks) → Build 2 (5 wks) → Peak (5 wks) → Taper (2 wks)
- Each phase has: target weekly hours, TSS range, intensity distribution, key workouts
- Phases auto-adjust dates if the athlete falls behind or gets ahead

- **Tests**: Phase dates calculated correctly from race date. TSS targets match plan.

#### 6b. Weekly workout prescription
- Generate a week of workouts based on:
  - Current phase
  - Current CTL/ATL/TSB
  - Days available (athlete can mark unavailable days)
  - Recent training load (don't pile on if already fatigued)
- Protect "key workouts" — the 2-3 most important sessions of the week
- Flexible days can shift or be dropped

- **Tests**: Week generated with correct number of workouts. Key workouts preserved when days are removed.

#### 6c. Adaptive replanning
- When a workout is missed: redistribute load across remaining days
- When an unplanned ride happens: account for its TSS in the week's budget
- When life happens (travel, illness): drop to maintenance, extend the current phase
- Never panic — the plan adapts, it doesn't break

- **Tests**: Missed workout redistributes correctly. Unplanned high-TSS ride reduces remaining plan.

#### 6d. Plan visualization
- Gantt-style view of phases
- Weekly plan view with drag-and-drop to move workouts
- Compliance tracking: green/yellow/red by week
- Projected CTL curve: "if you follow the plan, here's where your fitness will be on race day"

- **Tests**: Visualization renders phases correctly. CTL projection matches expected curve.

---

## Execution Order & Dependencies

```
Phase 0 (Organize)          ← DO FIRST, no dependencies
    ↓
Phase 1 (Database)          ← depends on organized file structure
    ↓
Phase 2 (API)               ← depends on database
    ↓
Phase 3 (Frontend)          ← depends on API
    ↓
Phase 4a-4d (Analysis)      ← can parallelize, each depends on API
    ↓
Phase 5 (Coaching Chat)     ← depends on API + analysis services
    ↓
Phase 6 (Plan Management)   ← depends on coaching + analysis
```

Estimated effort per phase:
- Phase 0: Small (file moves + CLAUDE.md)
- Phase 1: Medium (schema + ingestion + PMC)
- Phase 2: Medium (API endpoints)
- Phase 3: Medium-Large (frontend + charts)
- Phase 4: Large (4 independent features)
- Phase 5: Medium (Claude API integration)
- Phase 6: Large (planning engine + adaptive logic)

---

## Data Backup

Raw training data is backed up to GCS for safekeeping:

- **Bucket**: `gs://jasondel-coach-data` (project: `jasondel-cloudrun10`, region: `us-central1`)
- **`gs://jasondel-coach-data/fit/`** — 291 raw `.FIT` files from Garmin exports
- **`gs://jasondel-coach-data/json/`** — 291 converted ride `.json` files
- **`gs://jasondel-coach-data/planned_workouts/`** — 176 `.zwo` planned workout files

These are the source-of-truth files. The local SQLite database (Phase 1) is always rebuildable from these. If local files are cleaned up or lost, restore with:
```
gcloud storage cp -r gs://jasondel-coach-data/fit/ data/fit/
gcloud storage cp -r gs://jasondel-coach-data/json/ data/rides/
```

---

## Principles

1. **Test as we go** — every service gets unit tests before the API layer is built on top of it
2. **Small commits** — each step within a phase is a commit point
3. **Data integrity** — the raw FIT/JSON files are never modified; the database is always rebuildable from source
4. **Single athlete** — this is not a multi-user SaaS; keep it simple
5. **Coach-first** — every feature asks "does this help the athlete make a better decision about their next ride?"
6. **Graceful degradation** — missing power data (like March 2026) should show HR-based estimates, not blank screens
7. **The plan is a guide, not a cage** — the system should make replanning feel natural, not punishing
