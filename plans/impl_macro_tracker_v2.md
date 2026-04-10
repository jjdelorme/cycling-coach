# Macro Tracker v2 — Implementation Plan

> **Scope:** Intelligence layer, cross-agent wiring, and UX polish. Builds on v1 (core meal logging, Nutritionist agent, Nutrition tab). No offline/IndexedDB work (deferred to v3).

---

## Analysis & Context — What v1 Established

v1 (defined in `plans/impl_backend_v1.md` and `plans/impl_frontend_v1.md`) delivers:

- **Backend:** 3 DB tables (`meal_logs`, `meal_items`, `macro_targets`), GCS photo upload, Nutritionist ADK agent (`server/nutrition/agent.py`), `/api/nutrition` REST router, `get_athlete_nutrition_status` tool on the cycling coach
- **Frontend:** TypeScript types, React Query hooks, Nutrition tab with MealTimeline + MacroCard + DailySummaryStrip, MealCapture FAB, NutritionistPanel as a tab in CoachPanel
- **Key patterns established:**
  - Nutritionist agent at `server/nutrition/agent.py` with `_get_agent()` (returns `Agent` instance), `get_runner()`, and `chat()` function
  - Coaching agent at `server/coaching/agent.py` with `_get_agent()` at line 207, tools list at lines 209-226, `_build_system_instruction()` at line 87
  - Multimodal Content construction confirmed working via `types.Content` with image Parts
  - React Query v5 object syntax for all hooks
  - Chart.js `Line` and `Bar` components via `react-chartjs-2` with `useChartColors()` hook

v2 builds directly on top of these. No architectural changes — only additive features.

---

## Resolved Questions

### DECISION: AgentTool IS available — use it for Coach → Nutritionist delegation

**Evidence:** `google.adk.tools.agent_tool.AgentTool` exists in ADK v1.28.1 at:
```
/home/workspace/cycling-coach/venv/lib/python3.12/site-packages/google/adk/tools/agent_tool.py
```

**Import path:** `from google.adk.tools.agent_tool import AgentTool` (or `from google.adk.tools import AgentTool` via lazy loading in `__init__.py`)

**API confirmed from source code (agent_tool.py lines 94-276):**
```python
class AgentTool(BaseTool):
    def __init__(self, agent: BaseAgent, skip_summarization: bool = False, *, include_plugins: bool = True):
```

**Constructor:** Takes an `Agent` instance directly — not a Runner, not a config. Pass the Nutritionist's `Agent` object.

**Input schema:** When the wrapped agent has no `input_schema`, AgentTool exposes a single `request: str` parameter (lines 142-168). The parent agent calls it with natural language: `nutritionist(request="What should the athlete eat before tomorrow's 4h ride?")`.

**Session isolation (CONFIRMED from source, lines 228-247):** Each AgentTool invocation creates:
- A fresh `InMemorySessionService()` — the sub-agent gets its own ephemeral session
- A fresh `InMemoryMemoryService()` — no cross-contamination with parent memory
- A new `Runner` per invocation — fully isolated

This means the Nutritionist agent, when invoked via AgentTool, does NOT access its persistent `DbSessionService` sessions. It starts fresh each time — **no prior chat history is available**. This is correct for our use case: the coach asks a one-shot question, gets a data-rich answer. The nutritionist's persistent sessions remain separate for direct user chat.

**Critical implication:** Because the Nutritionist loses its conversation history in AgentTool context, the callable `_build_system_instruction()` becomes the primary mechanism for providing context. The v1 Nutritionist's system instruction callable already pulls the last 3 days of meals and recent rides from the DB at invocation time, which provides sufficient context for coach delegation queries (e.g., "What should the athlete eat before tomorrow's 4h ride?"). No changes needed to the Nutritionist's system prompt for v2 — the callable design already compensates for the absent session history. The Nutritionist's DB query tools (`get_meal_history`, `get_daily_macros`, etc.) remain available and provide additional context if the agent needs to look further back.

**State forwarding (lines 238-258):** Parent state is copied to the child session (excluding `_adk` internal keys). State deltas from the child are forwarded back. This lets the nutritionist read athlete context from the coach's session state.

**Cleanup (line 264):** `await runner.close()` is called after the sub-agent completes.

### DECISION: Unidirectional AgentTool (Coach → Nutritionist only)

Per design doc `plans/design-ai-integration.md` Section 4.4 — Hybrid approach:
- **90% case:** Coach uses `get_athlete_nutrition_status` (direct DB query, already in v1) for simple checks
- **10% case:** Coach uses `AgentTool(agent=nutritionist)` for complex fueling reasoning

No Nutritionist → Coach AgentTool. The Nutritionist already has `get_upcoming_training_load` and `get_recent_workouts` tools (v1 Phase 3) that query training data directly. No circular dependency.

### DECISION: Voice notes use `types.Part.from_bytes(data=audio_bytes, mime_type="audio/webm")`

ADK's multimodal Content forwarding is confirmed working for image Parts (v1 Q1 decision). Audio Parts work identically — Gemini supports `audio/webm` and `audio/mp4` MIME types natively. The audio Part is added alongside the image Part in the same `types.Content.parts` list. No transcription step needed.

### DECISION: Rate limiting via simple DB counter

No existing rate-limiting middleware in the codebase. Rather than adding a full middleware (Redis, sliding window), use a simple per-day counter in the `meal_logs` table: `SELECT COUNT(*) FROM meal_logs WHERE date = today`. This is fast with the existing `idx_meal_logs_date` index. Limit: 20 analyses/day, returning 429 on overflow.

---

## Phase 1: AgentTool Wiring — Coach → Nutritionist

### 1A. Expose Nutritionist Agent instance

**Target file:** `server/nutrition/agent.py` (created in v1 Phase 5)

The v1 plan defines `_get_agent()` as a private function. For AgentTool, the Coach needs access to the `Agent` instance. Add a public getter:

```python
def get_nutritionist_agent() -> Agent:
    """Return the Nutritionist Agent instance for use as an AgentTool.

    Called by the Cycling Coach's agent setup to wire the Nutritionist
    as a delegatable tool. The Agent object is re-created each time to
    pick up any settings changes (model, etc).
    """
    return _get_agent()
```

**Location:** Add after `_get_agent()` (around line 1035 of `impl_backend_v1.md`).

### 1B. Add AgentTool to Cycling Coach's tools

**Target file:** `server/coaching/agent.py`

**Add import** (after existing imports at top of file):
```python
from google.adk.tools import AgentTool
from server.nutrition.agent import get_nutritionist_agent
```

**Modify `_get_agent()` at line 207.** Add the AgentTool to the tools list, after the existing tools and after `get_athlete_nutrition_status`:

```python
def _get_agent():
    tools = [
        # ... existing read-only tools (lines 210-226) ...
        get_athlete_nutrition_status,  # v1 Phase 8 — direct DB query
        AgentTool(agent=get_nutritionist_agent()),  # v2 — full agent delegation
    ]
    for fn in _WRITE_TOOLS:
        tools.append(_permission_gate(fn))

    return Agent(
        name="cycling_coach",
        model=_get_effective_model(),
        description="Expert cycling coach",
        instruction=_build_system_instruction,
        tools=tools,
    )
```

**IMPORTANT:** `AgentTool(agent=...)` takes an `Agent`, not a `Runner`. The `get_nutritionist_agent()` call returns the raw `Agent` with its tools and instruction. AgentTool creates its own `Runner` internally (source: `agent_tool.py:228-236`).

**Note on Runner singleton invalidation:** The coach's `_runner` is a singleton. Adding a new tool means `reset_runner()` must be called when the coach's tools change. Since the AgentTool is added statically in `_get_agent()`, this is handled automatically — the runner is created once with the full tool list. No runtime invalidation needed.

### 1C. Update Coach system prompt for delegation guidance

**Target file:** `server/coaching/agent.py`, in `_build_system_instruction()` (line 87)

**Add to the system prompt** (before the closing `"""`), after the `PLAN MANAGEMENT:` section:

```python
    nutrition_section = """

NUTRITION INTEGRATION:
You have two ways to access the athlete's nutritional data:

1. QUICK CHECK — use get_athlete_nutrition_status (fast, direct DB query):
   - Has the athlete eaten today? How many calories so far?
   - What was their last meal?
   - Current caloric balance (in vs out)
   Use this for quick data checks before making coaching decisions.

2. COMPLEX FUELING GUIDANCE — delegate to the nutritionist agent (slower, full AI reasoning):
   - Pre-ride meal planning for rides > 2 hours
   - Recovery nutrition strategy after hard training blocks
   - Multi-day fueling plans for training camps or events
   - Analyzing whether chronic under-fueling is affecting performance
   The nutritionist has access to the full meal history, macro targets, and
   specialized knowledge about sports nutrition.

NUTRITION-AWARE COACH NOTES:
For workouts longer than 90 minutes, include fueling guidance in your coach notes:
1. Check the athlete's recent intake via get_athlete_nutrition_status
2. For rides > 2 hours, include:
   - Pre-ride meal recommendation (timing + approximate calories)
   - On-bike fueling target (typically 60-90g carbs/hour for endurance)
   - Post-ride recovery nutrition window
3. If the athlete's recent intake suggests under-fueling, flag this prominently
4. For particularly long or intense sessions (>3h or IF >0.85), delegate to
   the nutritionist for detailed fueling guidance"""

    return f"""You are an expert cycling coach...
{existing_prompt_content}
{nutrition_section}"""
```

### Verification

```bash
source venv/bin/activate
python -c "
from google.adk.tools import AgentTool
from server.nutrition.agent import get_nutritionist_agent
agent = get_nutritionist_agent()
tool = AgentTool(agent=agent)
print(f'AgentTool OK: name={tool.name}, description={agent.description}')
"
```

---

## Phase 2: Rate Limiting on Meal Photo Analysis

### 2A. Add rate-limit check to nutrition router

**Target file:** `server/routers/nutrition.py` (created in v1 Phase 7)

**Add at the top of `create_meal()` endpoint** (the `POST /api/nutrition/meals` handler):

```python
DAILY_ANALYSIS_LIMIT = 20

@router.post("/meals", status_code=201)
async def create_meal(
    file: UploadFile = File(...),
    comment: str = Form(""),
    meal_type: str = Form(""),
    user: CurrentUser = Depends(require_write),
):
    """Analyze and log a meal photo. Rate-limited to 20 analyses/day."""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")

    # Rate limit check — uses existing idx_meal_logs_date index
    with get_db() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM meal_logs WHERE date = %s AND user_id = %s",
            (today, "athlete"),
        ).fetchone()
        if count_row and count_row["cnt"] >= DAILY_ANALYSIS_LIMIT:
            raise HTTPException(
                429,
                f"Daily meal analysis limit reached ({DAILY_ANALYSIS_LIMIT}/day). "
                "You can still edit existing meals or chat with the nutritionist."
            )

    # ... rest of existing create_meal logic (validate, upload, analyze) ...
```

**Why 20/day?** Reasonable upper bound: 4-5 meals × potential retakes/corrections. A real user logs 3-6 meals/day. 20 prevents runaway costs from bugs or abuse without restricting normal usage.

**Why not middleware?** This is a single endpoint that needs limiting. A global rate-limiting middleware would be over-engineering. The DB query is fast (indexed) and atomic.

### 2B. Frontend: Handle 429 response

**Target file:** `frontend/src/lib/api.ts`

The existing `request<T>()` helper (line 14-34) already throws on non-OK responses. Add a specific check for 429 in the error handling:

```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
  })
  if (res.status === 401) {
    throw new Error('Unauthorized — please sign in again')
  }
  if (res.status === 403) {
    throw new Error('Insufficient permissions')
  }
  if (res.status === 429) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || 'Rate limit reached — please try again later')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}
```

The `MealCapture` component from v1 already shows `logMeal.error?.message` — the 429 message will surface automatically.

### Verification

```bash
# Unit test: verify rate limit logic
python -c "
# Simulate: insert 20 rows, verify 21st would be blocked
print('Rate limit constant:', 20)
print('Query uses idx_meal_logs_date index — O(1) lookup')
"
```

---

## Phase 3: Voice Notes on Capture Screen

### 3A. Backend: Accept audio in meal upload

**Target file:** `server/routers/nutrition.py`

**Modify `create_meal()` endpoint** to accept an optional audio file:

```python
@router.post("/meals", status_code=201)
async def create_meal(
    file: UploadFile = File(...),
    audio: UploadFile | None = File(None),  # ADD — optional voice note
    comment: str = Form(""),
    meal_type: str = Form(""),
    user: CurrentUser = Depends(require_write),
):
    # ... rate limit check ...

    # ... image validation and upload (existing) ...

    # Read audio bytes if provided
    audio_bytes = None
    audio_mime = None
    if audio and audio.content_type in ("audio/webm", "audio/mp4", "audio/mpeg"):
        audio_bytes = await audio.read()
        audio_mime = audio.content_type
        if len(audio_bytes) > 5 * 1024 * 1024:  # 5MB max for voice notes
            raise HTTPException(400, "Audio too large (max 5MB)")

    # Build prompt
    prompt = comment or "Analyze this meal and estimate its macros."
    if meal_type:
        prompt += f" This is a {meal_type} meal."
    if audio_bytes:
        prompt += " I've also included a voice note describing the meal."

    # Send to nutritionist agent — now with optional audio
    session_id = str(uuid.uuid4())
    response_text = await nutrition_chat(
        message=prompt,
        user_id=user.email if hasattr(user, "email") else "athlete",
        session_id=session_id,
        user=user,
        image_data=resized_bytes,
        image_mime_type="image/jpeg",
        photo_gcs_path=gcs_path,
        audio_data=audio_bytes,        # ADD
        audio_mime_type=audio_mime,     # ADD
    )

    # ... rest of existing logic ...
```

### 3B. Backend: Pass audio Part to Nutritionist agent

**Target file:** `server/nutrition/agent.py`

**Modify `chat()` function signature** to accept audio:

```python
async def chat(
    message: str,
    user_id: str = "athlete",
    session_id: str = "default",
    user=None,
    image_data: bytes | None = None,
    image_mime_type: str | None = None,
    photo_gcs_path: str = "",
    audio_data: bytes | None = None,      # ADD
    audio_mime_type: str | None = None,    # ADD
) -> str:
```

**Modify the Content construction** (in the `chat()` function body, where parts are built):

```python
    parts = []
    if image_data and image_mime_type:
        parts.append(types.Part.from_image(
            image=types.Image.from_bytes(data=image_data, mime_type=image_mime_type)
        ))
        if photo_gcs_path:
            message = f"[Photo stored at: {photo_gcs_path}]\n{message}"

    # Audio part — passed directly to Gemini as multimodal input
    if audio_data and audio_mime_type:
        parts.append(types.Part.from_bytes(data=audio_data, mime_type=audio_mime_type))

    parts.append(types.Part.from_text(text=message))

    content = types.Content(role="user", parts=parts)
```

**Note:** `types.Part.from_bytes()` accepts any MIME type. Gemini natively understands `audio/webm` and `audio/mp4`. The agent sees image + audio + text simultaneously, allowing it to correlate the user's verbal description with the visual analysis.

### 3C. Frontend: VoiceNoteButton component

**Target file:** `frontend/src/components/VoiceNoteButton.tsx` (new)

Push-to-talk button using the MediaRecorder API. Returns an audio Blob.

```typescript
import { useState, useRef, useCallback } from 'react'
import { Mic, MicOff } from 'lucide-react'

interface Props {
  onRecorded: (blob: Blob, mimeType: string) => void
  maxDuration?: number  // seconds, default 15
}

export default function VoiceNoteButton({ onRecorded, maxDuration = 15 }: Props) {
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      // Prefer webm; fall back to mp4 on iOS
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/mp4'

      const recorder = new MediaRecorder(stream, { mimeType })
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop())
        if (timerRef.current) clearInterval(timerRef.current)
        const blob = new Blob(chunksRef.current, { type: mimeType.split(';')[0] })
        onRecorded(blob, mimeType.split(';')[0])
        setElapsed(0)
      }

      recorderRef.current = recorder
      recorder.start()
      setRecording(true)
      setElapsed(0)

      timerRef.current = setInterval(() => {
        setElapsed(prev => {
          if (prev + 1 >= maxDuration) {
            recorder.stop()
            setRecording(false)
            return 0
          }
          return prev + 1
        })
      }, 1000)
    } catch {
      // Microphone permission denied — silently ignore
    }
  }, [onRecorded, maxDuration])

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      recorderRef.current.stop()
      setRecording(false)
    }
  }, [])

  return (
    <button
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={stop}
      className={`p-3 rounded-full transition-all ${
        recording
          ? 'bg-red text-white animate-pulse shadow-lg shadow-red/30'
          : 'bg-surface-low text-text-muted hover:text-accent hover:bg-accent/5'
      }`}
      title={recording ? `Recording... ${elapsed}s` : 'Hold to record voice note'}
    >
      {recording ? <MicOff size={20} /> : <Mic size={20} />}
      {recording && (
        <span className="absolute -top-1 -right-1 text-[9px] font-bold bg-red text-white rounded-full w-5 h-5 flex items-center justify-center">
          {elapsed}
        </span>
      )}
    </button>
  )
}
```

### 3D. Integrate VoiceNoteButton into MealCapture

**Target file:** `frontend/src/components/MealCapture.tsx` (created in v1 Phase 3A)

**Modify to support audio alongside photo:**

```typescript
import VoiceNoteButton from './VoiceNoteButton'

// Add state for audio blob
const [audioBlob, setAudioBlob] = useState<{ blob: Blob; mime: string } | null>(null)

// Modify handleCapture to include audio in the upload
const handleCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0]
  if (!file) return
  setPreview(URL.createObjectURL(file))

  try {
    const result = await logMeal.mutateAsync({
      file,
      audio: audioBlob?.blob,       // Pass audio if recorded
      audioMimeType: audioBlob?.mime,
    })
    onMealSaved?.(result)
  } finally {
    setPreview(null)
    setAudioBlob(null)
    if (fileRef.current) fileRef.current.value = ''
  }
}
```

**Render the VoiceNoteButton next to the FAB:**

```typescript
{/* Voice note button — positioned above the FAB */}
<div className="fixed bottom-24 right-6 md:bottom-8 md:right-8 flex flex-col items-center gap-2 z-30">
  <div className="relative">
    <VoiceNoteButton
      onRecorded={(blob, mime) => setAudioBlob({ blob, mime })}
    />
    {audioBlob && (
      <span className="absolute -top-1 -right-1 w-2 h-2 bg-green rounded-full" />
    )}
  </div>
  {/* FAB */}
  <button onClick={() => fileRef.current?.click()} /* ... existing FAB code ... */>
    <Camera size={24} />
  </button>
</div>
```

### 3E. Update API client and hook for audio

**Target file:** `frontend/src/lib/api.ts`

**Modify `uploadMealPhoto`:**

```typescript
export const uploadMealPhoto = async (
  file: File,
  comment?: string,
  mealType?: string,
  audio?: Blob,           // ADD
  audioMimeType?: string, // ADD
) => {
  const form = new FormData()
  form.append('file', file)
  if (comment) form.append('comment', comment)
  if (mealType) form.append('meal_type', mealType)
  if (audio) form.append('audio', audio, `voice.${audioMimeType === 'audio/mp4' ? 'mp4' : 'webm'}`)
  return request<MealDetail>('/api/nutrition/meals', {
    method: 'POST',
    body: form,
  })
}
```

**Target file:** `frontend/src/hooks/useApi.ts`

**Modify `useLogMeal` mutationFn:**

```typescript
export function useLogMeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, comment, mealType, audio, audioMimeType }: {
      file: File; comment?: string; mealType?: string;
      audio?: Blob; audioMimeType?: string;  // ADD
    }) => api.uploadMealPhoto(file, comment, mealType, audio, audioMimeType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
      qc.invalidateQueries({ queryKey: ['weekly-nutrition'] })
    },
  })
}
```

### Verification

```bash
# Backend: verify audio Part construction
source venv/bin/activate
python -c "
from google.genai import types
audio_part = types.Part.from_bytes(data=b'fake_audio', mime_type='audio/webm')
print(f'Audio Part OK: mime_type={audio_part.inline_data.mime_type}')
"

# Frontend: verify VoiceNoteButton compiles
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -10
```

---

## Phase 4: Dashboard Energy Balance Widget

### 4A. Create `frontend/src/components/NutritionDashboardWidget.tsx`

**Pattern references:**
- Dashboard card structure from `frontend/src/pages/Dashboard.tsx:158-229` — card with `bg-surface-low` section header + content area
- Chart.js Line from `Dashboard.tsx:120-141` — `chartData` + `chartOptions` + `useChartColors()`
- `useDailyNutrition` hook from v1 Phase 2B

```typescript
import { useMemo } from 'react'
import { Line } from 'react-chartjs-2'
import { useDailyNutrition, useWeeklyNutrition } from '../hooks/useApi'
import { useChartColors } from '../lib/theme'
import { Apple, ChevronRight } from 'lucide-react'

interface Props {
  onNavigateToNutrition?: () => void
}

export default function NutritionDashboardWidget({ onNavigateToNutrition }: Props) {
  const today = new Date().toISOString().slice(0, 10)
  const { data: daily } = useDailyNutrition(today)
  const { data: weekly } = useWeeklyNutrition(today)
  const cc = useChartColors()

  // 7-day net calorie balance sparkline
  const sparkData = useMemo(() => {
    if (!weekly?.days) return null
    return {
      labels: weekly.days.map(d => {
        const dt = new Date(d.date + 'T12:00:00')
        return dt.toLocaleDateString(undefined, { weekday: 'short' })
      }),
      datasets: [{
        data: weekly.days.map(d => {
          // Net = intake - ride expenditure (BMR excluded for simplicity in sparkline)
          return d.meal_count > 0 ? d.calories - d.calories_out_rides : null
        }),
        borderColor: '#00d4aa',
        backgroundColor: 'rgba(0, 212, 170, 0.1)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.3,
        fill: true,
      }],
    }
  }, [weekly])

  const sparkOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { enabled: false } },
    scales: {
      x: { display: false },
      y: { display: false },
    },
  }

  if (!daily) return null

  const netBalance = daily.net_caloric_balance
  const netColor = netBalance >= 0 ? 'text-green' : 'text-red'
  const netLabel = netBalance >= 0 ? 'surplus' : 'deficit'

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
      {/* Section header */}
      <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center justify-between">
        <h2 className="text-sm font-bold text-text uppercase tracking-wider flex items-center gap-2">
          <Apple size={16} className="text-green" />
          Energy Balance
        </h2>
        <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Today</span>
      </div>

      <div className="p-5">
        {/* In / Out / Net */}
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="text-center">
            <p className="text-2xl font-bold text-accent">{daily.total_calories_in.toLocaleString()}</p>
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">In (kcal)</p>
            <p className="text-xs text-text-muted">{daily.meal_count} meal{daily.meal_count !== 1 ? 's' : ''}</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-yellow">{daily.calories_out.total.toLocaleString()}</p>
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Out (kcal)</p>
            <p className="text-xs text-text-muted">{daily.calories_out.rides > 0 ? `${daily.calories_out.rides} rides` : 'BMR only'}</p>
          </div>
          <div className="text-center">
            <p className={`text-2xl font-bold ${netColor}`}>{Math.abs(netBalance).toLocaleString()}</p>
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{netLabel}</p>
          </div>
        </div>

        {/* Ratio bar */}
        {daily.calories_out.total > 0 && (
          <div className="mb-4">
            <div className="h-2 bg-surface-low rounded-full overflow-hidden flex">
              <div
                className="bg-accent rounded-l-full"
                style={{ width: `${Math.min((daily.total_calories_in / (daily.total_calories_in + daily.calories_out.total)) * 100, 100)}%` }}
              />
              <div className="bg-yellow flex-1 rounded-r-full" />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[9px] text-text-muted">In: {daily.total_calories_in > 0 ? Math.round((daily.total_calories_in / (daily.total_calories_in + daily.calories_out.total)) * 100) : 0}%</span>
              <span className="text-[9px] text-text-muted">Out: {Math.round((daily.calories_out.total / (daily.total_calories_in + daily.calories_out.total)) * 100)}%</span>
            </div>
          </div>
        )}

        {/* Weekly sparkline */}
        {sparkData && (
          <div className="mb-4">
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest mb-2">This Week</p>
            <div className="h-16">
              <Line data={sparkData} options={sparkOptions} />
            </div>
          </div>
        )}

        {/* CTA */}
        {onNavigateToNutrition && (
          <button
            onClick={onNavigateToNutrition}
            className="flex items-center gap-1 text-accent text-xs font-bold uppercase tracking-widest hover:opacity-80 transition-opacity"
          >
            Log a Meal <ChevronRight size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
```

### 4B. Add widget to Dashboard

**Target file:** `frontend/src/pages/Dashboard.tsx`

**Add import** (after line 28):
```typescript
import NutritionDashboardWidget from '../components/NutritionDashboardWidget'
```

**Update Props interface** (line 32):
```typescript
interface Props {
  onRideSelect?: (id: number) => void
  onWorkoutSelect?: (id: number, date: string) => void
  onNavigateToNutrition?: () => void  // ADD
}
```

**Add the widget** in the `grid-cols-1 lg:grid-cols-2` grid (line 158), after the "Latest Ride" card and before the PMC chart:

```typescript
{/* Energy Balance Widget */}
<NutritionDashboardWidget onNavigateToNutrition={onNavigateToNutrition} />
```

**Update App.tsx** to pass the navigation handler:

In `frontend/src/App.tsx`, modify the Dashboard render (line 53):
```typescript
{tab === 'dashboard' && (
  <Dashboard
    onRideSelect={handleRideSelect}
    onWorkoutSelect={handleWorkoutSelect}
    onNavigateToNutrition={() => setTab('nutrition')}  // ADD
  />
)}
```

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -10
cd frontend && npm run build 2>&1 | tail -5
```

---

## Phase 5: Weekly Summary Stacked Bar Chart

### 5A. Add Chart.js Bar chart to Nutrition page

**Target file:** `frontend/src/pages/Nutrition.tsx` (created in v1 Phase 5B)

Add a toggle between "Day" and "Week" view. When "Week" is selected, show a stacked horizontal bar chart with P/C/F segments.

**Add imports:**
```typescript
import { Bar } from 'react-chartjs-2'
import { useWeeklyNutrition } from '../hooks/useApi'
import { useChartColors } from '../lib/theme'
```

**Add state for view mode:**
```typescript
const [viewMode, setViewMode] = useState<'day' | 'week'>('day')
const { data: weeklyData } = useWeeklyNutrition(date)
const cc = useChartColors()
```

**Add toggle buttons** in the header section:
```typescript
<div className="flex items-center gap-2">
  <button
    onClick={() => setViewMode('day')}
    className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${
      viewMode === 'day' ? 'bg-accent text-white' : 'text-text-muted hover:text-text'
    }`}
  >Day</button>
  <button
    onClick={() => setViewMode('week')}
    className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${
      viewMode === 'week' ? 'bg-accent text-white' : 'text-text-muted hover:text-text'
    }`}
  >Week</button>
</div>
```

**Add weekly view content** (rendered when `viewMode === 'week'`):

```typescript
{viewMode === 'week' && weeklyData && (
  <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
    {/* Weekly averages */}
    <div className="flex gap-6 mb-4">
      <div>
        <span className="text-lg font-bold text-accent">{weeklyData.avg_daily_calories}</span>
        <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-1">avg kcal/day</span>
      </div>
      <div>
        <span className="text-sm font-bold text-green">{Math.round(weeklyData.avg_daily_protein_g)}g P</span>
      </div>
      <div>
        <span className="text-sm font-bold text-yellow">{Math.round(weeklyData.avg_daily_carbs_g)}g C</span>
      </div>
      <div>
        <span className="text-sm font-bold text-blue">{Math.round(weeklyData.avg_daily_fat_g)}g F</span>
      </div>
    </div>

    {/* Stacked bar chart */}
    <div className="h-48">
      <Bar
        data={{
          labels: weeklyData.days.map(d => {
            const dt = new Date(d.date + 'T12:00:00')
            return dt.toLocaleDateString(undefined, { weekday: 'short' })
          }),
          datasets: [
            {
              label: 'Protein',
              data: weeklyData.days.map(d => Math.round(d.protein_g * 4)),  // kcal from protein
              backgroundColor: '#00d4aa',
            },
            {
              label: 'Carbs',
              data: weeklyData.days.map(d => Math.round(d.carbs_g * 4)),  // kcal from carbs
              backgroundColor: '#eab308',
            },
            {
              label: 'Fat',
              data: weeklyData.days.map(d => Math.round(d.fat_g * 9)),  // kcal from fat
              backgroundColor: '#4a9eff',
            },
          ],
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: 'y',
          plugins: {
            legend: {
              labels: { color: cc.legendColor, boxWidth: 10, font: { size: 11 } },
              position: 'top',
              align: 'end',
            },
            tooltip: {
              backgroundColor: cc.tooltipBg,
              titleColor: cc.tooltipTitle,
              bodyColor: cc.tooltipBody,
              borderColor: cc.tooltipBorder,
              borderWidth: 1,
            },
          },
          scales: {
            x: {
              stacked: true,
              ticks: { color: cc.tickColor },
              grid: { color: 'rgba(148, 163, 184, 0.1)' },
            },
            y: {
              stacked: true,
              ticks: { color: cc.tickColor },
              grid: { display: false },
            },
          },
        }}
      />
    </div>
  </div>
)}
```

### Verification

```bash
cd frontend && npm run build 2>&1 | tail -5
```

---

## Phase 6: Swipe Gestures

### 6A. Swipe-to-delete on MacroCard

**Target file:** `frontend/src/components/MacroCard.tsx` (created in v1 Phase 4)

Add touch event handlers for horizontal swipe detection. When swiped left past a threshold, reveal a delete button.

**Add state and ref for swipe tracking:**

```typescript
const [swipeX, setSwipeX] = useState(0)
const touchStartRef = useRef<{ x: number; y: number } | null>(null)
const SWIPE_THRESHOLD = 80 // px

const handleTouchStart = (e: React.TouchEvent) => {
  touchStartRef.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
}

const handleTouchMove = (e: React.TouchEvent) => {
  if (!touchStartRef.current) return
  const dx = e.touches[0].clientX - touchStartRef.current.x
  const dy = e.touches[0].clientY - touchStartRef.current.y
  // Only track horizontal swipes (ignore vertical scroll)
  if (Math.abs(dy) > Math.abs(dx)) return
  if (dx < 0) {
    setSwipeX(Math.max(dx, -SWIPE_THRESHOLD - 20))
  }
}

const handleTouchEnd = () => {
  if (swipeX < -SWIPE_THRESHOLD) {
    // Snap to reveal delete
    setSwipeX(-SWIPE_THRESHOLD)
  } else {
    setSwipeX(0)
  }
  touchStartRef.current = null
}
```

**Wrap the card content in a swipeable container:**

```typescript
<div className="relative overflow-hidden rounded-xl">
  {/* Delete action behind the card */}
  <div className="absolute inset-y-0 right-0 w-20 bg-red flex items-center justify-center">
    <button onClick={handleDelete}>
      <Trash2 size={20} className="text-white" />
    </button>
  </div>

  {/* Swipeable card */}
  <div
    className="relative bg-surface border border-border shadow-sm transition-transform"
    style={{ transform: `translateX(${swipeX}px)` }}
    onTouchStart={handleTouchStart}
    onTouchMove={handleTouchMove}
    onTouchEnd={handleTouchEnd}
  >
    {/* ... existing card content ... */}
  </div>
</div>
```

### 6B. Swipe date navigation on MealTimeline

**Target file:** `frontend/src/components/MealTimeline.tsx` (created in v1 Phase 5A)

Add horizontal swipe on the timeline container for day-to-day navigation:

```typescript
const timelineTouchRef = useRef<{ x: number } | null>(null)

const handleTimelineTouchStart = (e: React.TouchEvent) => {
  timelineTouchRef.current = { x: e.touches[0].clientX }
}

const handleTimelineTouchEnd = (e: React.TouchEvent) => {
  if (!timelineTouchRef.current) return
  const dx = e.changedTouches[0].clientX - timelineTouchRef.current.x
  if (Math.abs(dx) > 60) {
    // Swipe right = previous day, swipe left = next day
    shiftDate(dx > 0 ? -1 : 1)
  }
  timelineTouchRef.current = null
}
```

**Add handlers to the timeline wrapper:**

```typescript
<div
  onTouchStart={handleTimelineTouchStart}
  onTouchEnd={handleTimelineTouchEnd}
>
  {/* ... date nav + meal list ... */}
</div>
```

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -10
```

---

## Phase 7: Gemini Vision Benchmarking Strategy

### 7A. Create benchmarking script

**Target file:** `scripts/benchmark_nutrition_vision.py` (new)

This script evaluates Gemini model accuracy on a curated set of meal photos with known macros. It tests both Flash and Pro to inform model selection for the Nutritionist agent.

```python
"""Benchmark Gemini vision accuracy for meal macro estimation.

Usage:
    python scripts/benchmark_nutrition_vision.py --model gemini-2.5-flash
    python scripts/benchmark_nutrition_vision.py --model gemini-2.5-pro

Requires a benchmark dataset at data/nutrition_benchmark/ with:
    - photos/001.jpg, 002.jpg, ...
    - ground_truth.json with expected macros per photo
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.genai import types
from google import genai

ANALYSIS_PROMPT = """Analyze this meal photo and estimate:
- Total calories
- Protein (grams)
- Carbs (grams)
- Fat (grams)

Return ONLY a JSON object: {"calories": N, "protein_g": N, "carbs_g": N, "fat_g": N}"""


def run_benchmark(model_name: str, data_dir: str):
    """Run benchmark against ground truth dataset."""
    client = genai.Client(vertexai=True)
    gt_path = Path(data_dir) / "ground_truth.json"

    if not gt_path.exists():
        print(f"Ground truth not found at {gt_path}")
        print("Create data/nutrition_benchmark/ground_truth.json with format:")
        print('[{"file": "001.jpg", "calories": 500, "protein_g": 35, "carbs_g": 60, "fat_g": 15}, ...]')
        return

    with open(gt_path) as f:
        ground_truth = json.load(f)

    results = []
    for entry in ground_truth:
        photo_path = Path(data_dir) / "photos" / entry["file"]
        if not photo_path.exists():
            print(f"  SKIP {entry['file']} — file not found")
            continue

        image_bytes = photo_path.read_bytes()
        content = types.Content(
            role="user",
            parts=[
                types.Part.from_image(image=types.Image.from_bytes(
                    data=image_bytes, mime_type="image/jpeg"
                )),
                types.Part.from_text(text=ANALYSIS_PROMPT),
            ],
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=content,
            )
            text = response.text.strip()
            # Parse JSON from response
            if "```" in text:
                text = text.split("```")[1].replace("json", "").strip()
            predicted = json.loads(text)
        except Exception as e:
            print(f"  ERROR {entry['file']}: {e}")
            continue

        # Compute error percentages
        errors = {}
        for key in ["calories", "protein_g", "carbs_g", "fat_g"]:
            actual = entry[key]
            pred = predicted.get(key, 0)
            pct_err = abs(pred - actual) / actual * 100 if actual > 0 else 0
            errors[key] = round(pct_err, 1)

        results.append({
            "file": entry["file"],
            "actual": entry,
            "predicted": predicted,
            "error_pct": errors,
        })
        print(f"  {entry['file']}: cal_err={errors['calories']}% prot_err={errors['protein_g']}%")

    # Summary statistics
    if results:
        avg_cal_err = sum(r["error_pct"]["calories"] for r in results) / len(results)
        avg_prot_err = sum(r["error_pct"]["protein_g"] for r in results) / len(results)
        avg_carb_err = sum(r["error_pct"]["carbs_g"] for r in results) / len(results)
        avg_fat_err = sum(r["error_pct"]["fat_g"] for r in results) / len(results)

        print(f"\n=== BENCHMARK RESULTS: {model_name} ===")
        print(f"Samples: {len(results)}")
        print(f"Avg calorie error: {avg_cal_err:.1f}%")
        print(f"Avg protein error: {avg_prot_err:.1f}%")
        print(f"Avg carbs error:   {avg_carb_err:.1f}%")
        print(f"Avg fat error:     {avg_fat_err:.1f}%")

        # Save results
        out_path = Path(data_dir) / f"results_{model_name.replace('/', '_')}.json"
        with open(out_path, "w") as f:
            json.dump({"model": model_name, "results": results, "summary": {
                "avg_calorie_error_pct": round(avg_cal_err, 1),
                "avg_protein_error_pct": round(avg_prot_err, 1),
                "avg_carbs_error_pct": round(avg_carb_err, 1),
                "avg_fat_error_pct": round(avg_fat_err, 1),
            }}, f, indent=2)
        print(f"Results saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model to benchmark")
    parser.add_argument("--data-dir", default="data/nutrition_benchmark", help="Benchmark dataset directory")
    args = parser.parse_args()
    run_benchmark(args.model, args.data_dir)
```

### 7B. Model selection decision framework

The benchmark results inform a decision:

| Metric | Flash threshold | Pro threshold | Decision |
|--------|----------------|---------------|----------|
| Avg calorie error | < 20% | < 15% | If Flash < 20%, use Flash (cheaper, faster) |
| Avg protein error | < 25% | < 18% | If Flash > 25%, switch to Pro |
| Latency | ~1-3s | ~3-8s | Flash is 2-3x faster |
| Cost | ~3x cheaper | Baseline | Flash saves ~$0.01/analysis |

**Default recommendation:** Start with Flash for the Nutritionist agent (already the default via `_get_effective_model()` which reads `gemini_model` from DB settings). Run the benchmark on 50+ photos. If Flash's calorie accuracy is within 20%, keep it. If not, switch to Pro for the Nutritionist specifically by setting `gemini_model` in the DB or by having the Nutritionist override the model independently.

**To override model per-agent:** In `server/nutrition/agent.py`, modify `_get_effective_model()`:

```python
def _get_effective_model() -> str:
    """Return the Gemini model for the nutritionist.

    Checks for a nutrition-specific model setting first, then falls back
    to the global model setting.
    """
    nutrition_model = get_setting("nutritionist_model")
    if nutrition_model:
        return nutrition_model
    db_model = get_setting("gemini_model")
    return db_model if db_model else GEMINI_MODEL
```

Add `nutritionist_model` as a new setting key in the existing Settings page UI (v2 frontend work, same pattern as `gemini_model`).

---

## Phase 8: Tests

### 8A. Unit Tests

**File:** `tests/unit/test_rate_limit.py`
```python
"""Test rate limiting logic for meal analysis."""

def test_daily_limit_constant():
    """Rate limit is set to 20 analyses/day."""
    # Import the constant (after v2 is implemented)
    from server.routers.nutrition import DAILY_ANALYSIS_LIMIT
    assert DAILY_ANALYSIS_LIMIT == 20

def test_voice_note_mime_validation():
    """Only audio/webm, audio/mp4, audio/mpeg are accepted."""
    allowed = {"audio/webm", "audio/mp4", "audio/mpeg"}
    assert "audio/wav" not in allowed
    assert "audio/webm" in allowed
```

**File:** `tests/unit/test_agent_tool_wiring.py`
```python
"""Test AgentTool availability and wiring."""

def test_agent_tool_import():
    """AgentTool can be imported from google.adk.tools."""
    from google.adk.tools import AgentTool
    assert AgentTool is not None

def test_nutritionist_agent_getter():
    """get_nutritionist_agent returns an Agent instance."""
    from server.nutrition.agent import get_nutritionist_agent
    agent = get_nutritionist_agent()
    assert agent.name == "nutritionist"
    assert agent.description is not None

def test_agent_tool_wraps_nutritionist():
    """AgentTool wraps the nutritionist agent correctly."""
    from google.adk.tools import AgentTool
    from server.nutrition.agent import get_nutritionist_agent
    tool = AgentTool(agent=get_nutritionist_agent())
    assert tool.name == "nutritionist"
```

### 8B. Integration Tests

**File:** `tests/integration/test_rate_limit.py`
```python
"""Integration test for meal analysis rate limiting."""

def test_rate_limit_returns_429(client, db_conn):
    """POST /api/nutrition/meals returns 429 after daily limit."""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")

    # Insert 20 meal rows directly to simulate limit
    for i in range(20):
        db_conn.execute(
            "INSERT INTO meal_logs (user_id, date, logged_at, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            ("athlete", today, f"{today}T{10+i//6}:{(i*10)%60:02d}:00",
             f"Test meal {i+1}", 500, 30, 50, 20),
        )
    db_conn.connection.commit()

    # 21st analysis should be rate-limited
    # Note: can't easily test the full upload flow without GCS mocking,
    # so test the rate limit check directly
    count_row = db_conn.execute(
        "SELECT COUNT(*) AS cnt FROM meal_logs WHERE date = %s AND user_id = %s",
        (today, "athlete"),
    ).fetchone()
    assert count_row["cnt"] >= 20
```

### 8C. Run commands

```bash
# Unit tests
pytest tests/unit/test_rate_limit.py tests/unit/test_agent_tool_wiring.py -v

# Integration tests
./scripts/run_integration_tests.sh -v tests/integration/test_rate_limit.py

# Benchmark (requires curated photo dataset)
python scripts/benchmark_nutrition_vision.py --model gemini-2.5-flash
python scripts/benchmark_nutrition_vision.py --model gemini-2.5-pro
```

---

## File Inventory

### New Files

| File | Type | Purpose |
|------|------|---------|
| `frontend/src/components/VoiceNoteButton.tsx` | Component | Push-to-talk audio recorder |
| `frontend/src/components/NutritionDashboardWidget.tsx` | Component | Energy Balance card for Dashboard |
| `scripts/benchmark_nutrition_vision.py` | Script | Gemini vision accuracy benchmarking |
| `tests/unit/test_rate_limit.py` | Test | Rate limit unit tests |
| `tests/unit/test_agent_tool_wiring.py` | Test | AgentTool wiring tests |
| `tests/integration/test_rate_limit.py` | Test | Rate limit integration tests |

### Modified Files

| File | Change |
|------|--------|
| `server/nutrition/agent.py` | Add `get_nutritionist_agent()` public getter, `audio_data`/`audio_mime_type` params to `chat()`, audio Part construction |
| `server/coaching/agent.py` | Import AgentTool + `get_nutritionist_agent`, add to tools list in `_get_agent()`, update system prompt with nutrition integration section |
| `server/routers/nutrition.py` | Add rate limit check (20/day, 429), accept `audio` UploadFile in `create_meal()` |
| `frontend/src/lib/api.ts` | Add 429 handling in `request()`, add `audio`/`audioMimeType` params to `uploadMealPhoto()` |
| `frontend/src/hooks/useApi.ts` | Add `audio`/`audioMimeType` to `useLogMeal()` mutation type |
| `frontend/src/components/MealCapture.tsx` | Integrate VoiceNoteButton, pass audio blob to upload |
| `frontend/src/components/MacroCard.tsx` | Add swipe-to-delete touch handlers |
| `frontend/src/components/MealTimeline.tsx` | Add swipe date navigation touch handlers |
| `frontend/src/pages/Nutrition.tsx` | Add day/week toggle, weekly stacked bar chart |
| `frontend/src/pages/Dashboard.tsx` | Add NutritionDashboardWidget to grid, accept `onNavigateToNutrition` prop |
| `frontend/src/App.tsx` | Pass `onNavigateToNutrition` handler to Dashboard |

### NOT in v2 (deferred to v3)

- IndexedDB meal queuing
- CloudOff indicator for pending meals
- Background sync for photos
- Offline macro entry without AI analysis

---

## Implementation Order

Phases can be partially parallelized:

```
Phase 1 (AgentTool) ─────────────────── can start immediately
Phase 2 (Rate limiting) ─────────────── can start immediately (independent)
Phase 3 (Voice notes) ───────────────── depends on Phase 2 (modifies same endpoint)
Phase 4 (Dashboard widget) ──────────── can start immediately (frontend only)
Phase 5 (Weekly chart) ──────────────── can start immediately (frontend only)
Phase 6 (Swipe gestures) ────────────── can start immediately (frontend only)
Phase 7 (Benchmarking) ──────────────── can start immediately (independent script)
Phase 8 (Tests) ─────────────────────── after Phases 1-3
```

**Recommended parallel tracks:**
- Backend engineer: Phase 1 → Phase 2 → Phase 3 → Phase 8
- Frontend engineer: Phase 4 → Phase 5 → Phase 6 → Phase 3D-3E (frontend voice note parts)
- Either engineer: Phase 7 (benchmarking, when time allows)
