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
1. ~~Create the directory structure~~ DONE
2. ~~Move `.FIT` files to `data/fit/`~~ DONE — backed up to `gs://jasondel-coach-data/fit/`
3. ~~Move ride `.json` files to `data/rides/`~~ DONE — backed up to `gs://jasondel-coach-data/json/`
4. ~~Move `planned_workouts/` to `data/planned_workouts/`~~ DONE — backed up to `gs://jasondel-coach-data/planned_workouts/`
5. ~~Move scripts to `scripts/`~~ DONE
6. ~~Move analysis outputs to `analysis/`~~ DONE (`season_analysis.md`)
7. ~~Delete old snapshots/stray files~~ DONE (snapshots were empty Playwright DOM dumps, deleted)
8. ~~Verify nothing is broken (file counts match)~~ DONE (291 FIT, 291 JSON, 176 ZWO in GCS)
9. ~~Create `.gitignore`~~ DONE
10. ~~Initialize git repo~~ DONE — pushed to `git@github.com:jjdelorme/cycling-coach.git`
11. Create `CLAUDE.md` with project context and coaching knowledge (partially done via `AGENTS.md`)

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

#### 1a. Database schema design (Status: ✅ Implemented)
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

- **Tests**: Schema creation, insert/query round-trip (Passed in `tests/test_database.py`)

#### 1b. Data ingestion script (Status: ✅ Implemented)
- Download source data from GCS bucket (`gs://jasondel-coach-data`):
  - `gs://jasondel-coach-data/json/` → `data/rides/` (291 ride JSON files)
  - `gs://jasondel-coach-data/planned_workouts/` → `data/planned_workouts/` (176 ZWO files)
- Read all ride JSON files, extract session + record data
- Compute derived metrics (power bests, zone distribution per ride)
- Insert into SQLite
- Read all ZWO files, parse and insert
- Compute and store daily PMC (CTL/ATL/TSB)

- **Tests**: Ingestion of a single known ride, verify all fields. Ingestion of a ZWO file. PMC calculation against known values. (Passed in `tests/test_ingestion.py`)

#### 1c. Incremental update support (Status: ✅ Implemented)
- Track which files have been ingested (by filename hash)
- Support adding new rides without re-processing everything
- Script: `python -m server.ingest` or `python scripts/ingest.py`

- **Tests**: Re-run ingestion, verify no duplicates. Add a new file, verify it's picked up. (Passed in `tests/test_incremental_ingestion.py`)

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

## Phase 5: AI Coaching Agent (Google ADK & Tools)

**Goal**: An intelligent coaching agent powered by `google-cloud-aiplatform[agent_engines,adk]`. Instead of cramming all data into a massive system prompt, the agent uses a suite of discrete tools to query metrics, view the calendar, and take action. State and preferences are managed via ADK's native memory.

### Steps:

#### 5a. ADK Foundation & Configuration
We start by wiring up the ADK with environment-based configuration. Emphasize simple, un-fancy, pragmatic design. No hardcoded models.

1.  **Step 5a.1: Dependency and Env Configuration**
    *   *Test:* Write a test in `tests/test_config.py` asserting that `Config.gemini_model` loads from `.env` correctly, and defaults to `"gemini-3.1-flash-lite-preview"` if not present.
    *   *Implementation:* Update `requirements.txt` with `google-cloud-aiplatform[agent_engines,adk]` and `python-dotenv`. Update backend config (`server/config.py`) to load `GEMINI_MODEL`.
    *   *Verification:* Run `pytest tests/test_config.py` and ensure it passes.

2.  **Step 5a.2: Basic Agent Instantiation**
    *   *Test:* Write `tests/test_agent_setup.py` mocking the ADK initialization and verifying the agent is instantiated with the configured model string.
    *   *Implementation:* Create `server/coaching/agent.py`. Initialize the ADK `Agent` using the model from configuration.
    *   *Verification:* Run `pytest tests/test_agent_setup.py`.

#### 5b. Read-Only Context Tools
The agent needs small, specific tools to fetch current data, rather than relying on a bloated prompt.

1.  **Step 5b.1: PMC Metrics Tool**
    *   *Test:* Write `tests/test_tools.py::test_get_pmc_metrics_tool` verifying the tool returns a cleanly formatted string/dict of current CTL, ATL, and TSB from the SQLite database.
    *   *Implementation:* Create `server/coaching/tools.py`. Implement `@tool get_pmc_metrics(date: str)`.
    *   *Verification:* Run `pytest tests/test_tools.py`.

2.  **Step 5b.2: Recent Rides Tool**
    *   *Test:* Write `tests/test_tools.py::test_get_recent_rides_tool` verifying it fetches summaries of completed rides over the last `n` days.
    *   *Implementation:* Implement `@tool get_recent_rides(days_back: int)`.
    *   *Verification:* Run `pytest tests/test_tools.py`.

3.  **Step 5b.3: Upcoming Workouts Tool**
    *   *Test:* Write `tests/test_tools.py::test_get_upcoming_workouts_tool` asserting it retrieves planned ZWO data for the coming days.
    *   *Implementation:* Implement `@tool get_upcoming_workouts(days_ahead: int)`.
    *   *Verification:* Run `pytest tests/test_tools.py`.

4.  **Step 5b.4: Agent Tool Registration**
    *   *Test:* Write a test in `tests/test_agent_setup.py` asserting the Agent's `tools` list contains the newly created functions.
    *   *Implementation:* Register these tools with the ADK `Agent` in `server/coaching/agent.py`.
    *   *Verification:* Run `pytest tests/test_agent_setup.py`.

#### 5c. ADK Memory Integration
Use ADK's native memory systems to maintain conversation history and athlete context. We will not use a rigid SQLite `athlete_log` table.

1.  **Step 5c.1: InMemoryMemoryService Setup**
    *   *Test:* Write `tests/test_memory.py` asserting that messages added to the memory service can be retrieved accurately.
    *   *Implementation:* Initialize ADK's `InMemoryMemoryService` (or `PreloadMemoryTool` if persistent long-term context is needed) in `server/coaching/agent.py` and attach it to the Agent instance.
    *   *Verification:* Run `pytest tests/test_memory.py`.

2.  **Step 5c.2: System Prompt Refactoring**
    *   *Test:* Write a test asserting the agent's core system instructions initialize correctly.
    *   *Implementation:* Define a concise, static system instruction focused *only* on the persona (expert cycling coach, direct, focuses on 50yo MTB athlete) rather than injecting massive data sets. The agent must rely on its tools for data.
    *   *Verification:* Run `pytest tests/test_agent_setup.py`.

#### 5d. Chat API Endpoint
Expose the agent to the frontend.

1.  **Step 5d.1: Chat Endpoint Scaffold**
    *   *Test:* Write `tests/test_coaching_api.py::test_chat_endpoint_success`. Mock the ADK agent response and assert a 200 OK with the proper JSON format.
    *   *Implementation:* Implement `POST /api/coaching/chat` in `server/routers/coaching.py`. Extract the user message and pass it to the ADK agent.
    *   *Verification:* Run `pytest tests/test_coaching_api.py`.

2.  **Step 5d.2: Frontend Chat Interface Integration**
    *   *Test:* No automated UI test, but explicitly log response object in dev tools to ensure tool-calling latency is handled gracefully.
    *   *Implementation:* Update `web/js/coaching.js` to send/receive data to the new endpoint. Handle loading states while the agent thinks or calls tools.

---

## Phase 6: AI-Driven Training Plan Management

**Goal**: The agent actively manages the periodization and weekly planning using action-oriented tools, making the plan naturally adaptable to real-life interruptions.

### Steps:

#### 6a. Plan Modification Tools (Agent Actions)
Provide the agent with tools to manipulate the calendar directly.

1.  **Step 6a.1: Tool - Replan Missed Day**
    *   *Test:* Write `tests/test_planning_tools.py::test_replan_missed_day`. Assert it successfully shifts a key workout to a new date in the SQLite DB and resolves conflicts.
    *   *Implementation:* Implement `@tool replan_missed_day(missed_date: str, new_target_date: str)` in `server/coaching/tools.py`.
    *   *Verification:* Run `pytest tests/test_planning_tools.py`.

2.  **Step 6a.2: Tool - Generate Weekly Plan**
    *   *Test:* Write `tests/test_planning_tools.py::test_generate_weekly_plan`. Assert it writes a sequence of workouts to the database for a given week based on the target hours.
    *   *Implementation:* Implement `@tool generate_weekly_plan(start_date: str, focus: str, hours: float)`.
    *   *Verification:* Run `pytest tests/test_planning_tools.py`.

#### 6b. Periodization Phase Management
Allow the agent to look at the macro picture and adjust.

1.  **Step 6b.1: Tool - Get Periodization Status**
    *   *Test:* Write a test asserting the tool returns the current phase (e.g., 'Build 1') and dates.
    *   *Implementation:* Implement `@tool get_periodization_status()`.
    *   *Verification:* Run `pytest tests/test_planning_tools.py`.

2.  **Step 6b.2: Tool - Adjust Periodization Phase**
    *   *Test:* Write a test verifying the tool extends or shortens a phase's end date in the database based on the provided reason.
    *   *Implementation:* Implement `@tool adjust_phase(phase_name: str, new_end_date: str, reason: str)`.
    *   *Verification:* Run `pytest tests/test_planning_tools.py`.

#### 6c. Plan Visualization (Frontend)
Display the current state of the plan to the athlete, ensuring it updates when the AI takes action.

1.  **Step 6c.1: Macro Plan View**
    *   *Test:* Verify API endpoint `GET /api/plan/macro` returns periodization data correctly.
    *   *Implementation:* Build Gantt-style view in the UI showing Base → Build 1 → Build 2 → Peak → Taper.

2.  **Step 6c.2: Weekly Calendar Sync**
    *   *Test:* Verify calendar UI fetches new data after a chat message is sent.
    *   *Implementation:* Ensure `web/js/calendar.js` re-fetches plan data if the chat interaction involves plan modification tool calls.

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
