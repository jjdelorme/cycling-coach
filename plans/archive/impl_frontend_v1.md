# Macro Tracker v1 — Frontend Implementation Plan

> **Single source of truth for the frontend engineer.** Every phase lists exact files, component names, TypeScript types, Tailwind classes, patterns to follow with file:line references, and verification commands.

## Key Design Decisions (resolved from codebase investigation)

### DECISION Q4: React Query v5 confirmed

**Evidence:** `frontend/package.json` lists `"@tanstack/react-query": "^5.95.2"`. All hooks in `frontend/src/hooks/useApi.ts` use the v5 object syntax: `useQuery({ queryKey, queryFn })` (e.g., line 7-10) and `useMutation({ mutationFn, onSuccess })` (e.g., line 23-28). New nutrition hooks must follow this exact pattern.

### DECISION Q5: CoachPanel is a single panel — needs tab switcher added

**Evidence:** `frontend/src/components/CoachPanel.tsx` is a monolithic chat panel with header (line 88), messages area (line 158), and input area (line 223). It has NO tab switcher — just a single "AI Coach" title. The Nutritionist panel will be implemented by adding a tab switcher below the header, with each tab maintaining independent message state and session. This follows the design doc at `plans/design-ux-ui.md` Section 8.

### Navigation: New "Nutrition" bottom tab

**Evidence:** `frontend/src/components/Layout.tsx:18-23` defines the `tabs` array with 4 entries (dashboard, rides, calendar, analysis). `TabKey` at line 25 is `(typeof tabs)[number]['key'] | 'settings' | 'admin'`. The Nutrition tab is added to the `tabs` array (position 4, before Coach button) and `TabKey` union type naturally includes it.

### Frontend-Backend API Contract

All endpoints live under `/api/nutrition/` per the backend plan (`plans/impl_backend_v1.md` Phase 7). Key endpoints:
- `POST /api/nutrition/meals` — multipart upload (photo + optional comment/meal_type)
- `GET /api/nutrition/meals` — list with date filters + pagination
- `GET /api/nutrition/meals/{id}` — single meal with items
- `PUT /api/nutrition/meals/{id}` — update macros
- `DELETE /api/nutrition/meals/{id}` — delete meal
- `GET /api/nutrition/daily-summary?date=` — aggregated daily macros + caloric balance
- `GET /api/nutrition/weekly-summary?date=` — 7-day breakdown
- `GET /api/nutrition/targets` — daily macro targets
- `PUT /api/nutrition/targets` — update targets
- `POST /api/nutrition/chat` — nutritionist agent chat
- `GET /api/nutrition/sessions` — list nutritionist sessions
- `GET /api/nutrition/sessions/{id}` — get session with messages
- `DELETE /api/nutrition/sessions/{id}` — delete session

---

## Phase 1: TypeScript Types

### Target file: `frontend/src/types/api.ts`

**Pattern:** Follow the existing interface definitions. Optional fields use `?` suffix (e.g., `RideSummary.sport?` at line 4). Use `string` for dates/timestamps (matching `RideSummary.date` at line 3). No enums — use union string literals.

**Location:** Append after line 283 (after the `CoachSettings` interface).

**Add these interfaces:**

```typescript
// --- Nutrition Types ---

export interface MealItem {
  id?: number
  name: string
  serving_size?: string
  calories: number
  protein_g: number
  carbs_g: number
  fat_g: number
}

export interface MealSummary {
  id: number
  date: string
  logged_at: string
  meal_type?: string
  description: string
  total_calories: number
  total_protein_g: number
  total_carbs_g: number
  total_fat_g: number
  confidence: 'high' | 'medium' | 'low'
  photo_url?: string
  edited_by_user: boolean
}

export interface MealDetail extends MealSummary {
  items: MealItem[]
  agent_notes?: string
}

export interface MacroTargets {
  calories: number
  protein_g: number
  carbs_g: number
  fat_g: number
  updated_at?: string
}

export interface DailyNutritionSummary {
  date: string
  total_calories_in: number
  total_protein_g: number
  total_carbs_g: number
  total_fat_g: number
  meal_count: number
  target_calories: number
  target_protein_g: number
  target_carbs_g: number
  target_fat_g: number
  remaining_calories: number
  calories_out: {
    rides: number
    estimated_bmr: number
    total: number
  }
  net_caloric_balance: number
}

export interface WeeklyNutritionDay {
  date: string
  calories: number
  protein_g: number
  carbs_g: number
  fat_g: number
  meal_count: number
  calories_out_rides: number
}

export interface WeeklyNutritionSummary {
  week_start: string
  week_end: string
  avg_daily_calories: number
  avg_daily_protein_g: number
  avg_daily_carbs_g: number
  avg_daily_fat_g: number
  days: WeeklyNutritionDay[]
}

export interface MealListResponse {
  meals: MealSummary[]
  total: number
  limit: number
  offset: number
}

export interface NutritionChatRequest {
  message: string
  session_id?: string
  image_data?: string
  image_mime_type?: string
}

export interface NutritionChatResponse {
  response: string
  session_id: string
}
```

### Why these types?

- `MealSummary` vs `MealDetail` mirrors the `RideSummary`/`RideDetail` pattern (`frontend/src/types/api.ts:1-82`). List views get the lighter summary; detail views get items.
- `confidence` uses a union literal type instead of plain `string` — provides autocomplete and compile-time safety for the UI color logic.
- `MealListResponse` wraps the paginated response from `GET /api/nutrition/meals` (backend returns `{ meals, total, limit, offset }`).
- `NutritionChatRequest`/`NutritionChatResponse` mirror `ChatRequest`/`ChatResponse` at lines 178-186, with added `image_data` and `image_mime_type` fields for multimodal chat.

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

---

## Phase 2: API Client Functions + React Query Hooks

### 2A. API Client Functions

**Target file:** `frontend/src/lib/api.ts`

**Pattern:** Follow the existing function export pattern. Use the existing `get<T>()`, `post<T>()`, `put<T>()`, and `request<T>()` helpers (lines 36-54). Each function is a one-liner returning a typed API call.

**Add import** to the existing type import block at line 56-61:

```typescript
import type {
  RideSummary, RideDetail, PMCEntry, WeeklySummary,
  WorkoutDetail, WeekPlan, PeriodizationPhase, WeeklyOverview,
  ChatResponse, SessionSummary, SyncOverview, SyncStatus,
  CoachSettings,
  // ADD these:
  MealSummary, MealDetail, MealListResponse, MacroTargets,
  DailyNutritionSummary, WeeklyNutritionSummary,
  NutritionChatResponse,
} from '../types/api'
```

**Add these functions at the end of the file** (after line 183, after `syncSingleRide`):

```typescript
// Nutrition
export const fetchMeals = (params?: { start_date?: string; end_date?: string; limit?: number; offset?: number }) => {
  const q = new URLSearchParams()
  if (params?.start_date) q.set('start_date', params.start_date)
  if (params?.end_date) q.set('end_date', params.end_date)
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.offset) q.set('offset', String(params.offset))
  return get<MealListResponse>(`/api/nutrition/meals?${q}`)
}

export const fetchMeal = (id: number) => get<MealDetail>(`/api/nutrition/meals/${id}`)

export const uploadMealPhoto = async (file: File, comment?: string, mealType?: string) => {
  const form = new FormData()
  form.append('file', file)
  if (comment) form.append('comment', comment)
  if (mealType) form.append('meal_type', mealType)
  return request<MealDetail>('/api/nutrition/meals', {
    method: 'POST',
    body: form,
    // Note: do NOT set Content-Type header — browser sets it with boundary for multipart
  })
}

export const updateMeal = (id: number, body: {
  total_calories?: number; total_protein_g?: number; total_carbs_g?: number;
  total_fat_g?: number; meal_type?: string; items?: MealDetail['items']
}) => put<{ status: string }>(`/api/nutrition/meals/${id}`, body)

export const deleteMeal = (id: number) =>
  request<{ status: string }>(`/api/nutrition/meals/${id}`, { method: 'DELETE' })

export const fetchDailyNutrition = (date?: string) => {
  const q = date ? `?date=${date}` : ''
  return get<DailyNutritionSummary>(`/api/nutrition/daily-summary${q}`)
}

export const fetchWeeklyNutrition = (date?: string) => {
  const q = date ? `?date=${date}` : ''
  return get<WeeklyNutritionSummary>(`/api/nutrition/weekly-summary${q}`)
}

export const fetchMacroTargets = () => get<MacroTargets>('/api/nutrition/targets')

export const updateMacroTargets = (body: MacroTargets) =>
  put<{ status: string }>('/api/nutrition/targets', body)

export const sendNutritionChat = (message: string, sessionId?: string) =>
  post<NutritionChatResponse>('/api/nutrition/chat', { message, session_id: sessionId })

export const fetchNutritionSessions = () => get<SessionSummary[]>('/api/nutrition/sessions')

export const fetchNutritionSession = (id: string) =>
  get<import('../types/api').SessionDetail>(`/api/nutrition/sessions/${id}`)

export const deleteNutritionSession = (id: string) =>
  request<{ status: string }>(`/api/nutrition/sessions/${id}`, { method: 'DELETE' })
```

**Note on `uploadMealPhoto`:** This is the ONE function that does NOT use `post<T>()` because the backend expects `multipart/form-data`, not JSON. The `request<T>()` call omits the `Content-Type` header so the browser auto-sets it with the multipart boundary. The existing `request()` helper at line 14-34 already handles auth headers and error responses, so it works correctly for multipart.

### 2B. React Query Hooks

**Target file:** `frontend/src/hooks/useApi.ts`

**Pattern:** Follow the exact patterns visible at lines 6-11 (query) and lines 21-28 (mutation with invalidation). Mutations that modify meal data must invalidate `['meals']`, `['daily-nutrition']`, and `['weekly-nutrition']` query keys.

**Add these hooks at the end of the file** (after line 193, after `useWeeklySummary`):

```typescript
// Nutrition
export function useMeals(params?: Parameters<typeof api.fetchMeals>[0]) {
  return useQuery({
    queryKey: ['meals', params],
    queryFn: () => api.fetchMeals(params),
  })
}

export function useMeal(id: number | null) {
  return useQuery({
    queryKey: ['meal', id],
    queryFn: () => api.fetchMeal(id!),
    enabled: id !== null,
  })
}

export function useLogMeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, comment, mealType }: { file: File; comment?: string; mealType?: string }) =>
      api.uploadMealPhoto(file, comment, mealType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
      qc.invalidateQueries({ queryKey: ['weekly-nutrition'] })
    },
  })
}

export function useUpdateMeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof api.updateMeal>[1] }) =>
      api.updateMeal(id, body),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['meal', id] })
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
      qc.invalidateQueries({ queryKey: ['weekly-nutrition'] })
    },
  })
}

export function useDeleteMeal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.deleteMeal(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
      qc.invalidateQueries({ queryKey: ['weekly-nutrition'] })
    },
  })
}

export function useDailyNutrition(date?: string) {
  return useQuery({
    queryKey: ['daily-nutrition', date],
    queryFn: () => api.fetchDailyNutrition(date),
  })
}

export function useWeeklyNutrition(date?: string) {
  return useQuery({
    queryKey: ['weekly-nutrition', date],
    queryFn: () => api.fetchWeeklyNutrition(date),
  })
}

export function useMacroTargets() {
  return useQuery({
    queryKey: ['macro-targets'],
    queryFn: api.fetchMacroTargets,
  })
}

export function useUpdateMacroTargets() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.updateMacroTargets,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['macro-targets'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
    },
  })
}

export function useNutritionistChat() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ message, session_id }: { message: string; session_id?: string }) =>
      api.sendNutritionChat(message, session_id),
    onSuccess: () => {
      // Refresh meal data in case the nutritionist modified meals
      qc.invalidateQueries({ queryKey: ['meals'] })
      qc.invalidateQueries({ queryKey: ['daily-nutrition'] })
    },
  })
}

export function useNutritionSessions() {
  return useQuery({
    queryKey: ['nutrition-sessions'],
    queryFn: api.fetchNutritionSessions,
  })
}
```

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

---

## Phase 3: Base Components — MealCapture + DailySummaryStrip + MacroAnalysisCard

### 3A. `frontend/src/components/MealCapture.tsx`

This component handles the photo capture flow: hidden file input, FAB trigger, and upload initiation. It's the entry point for Flow A (Quick Capture) from `plans/design-ux-ui.md` Section 2.

**Pattern references:**
- FAB style from `plans/design-ux-ui.md` Section 4: `fixed w-14 h-14 bg-accent text-white rounded-full shadow-lg shadow-accent/20`
- File input pattern from `plans/design-ux-ui.md` Section 9: `<input type="file" accept="image/*" capture="environment">`

```typescript
import { useRef, useState } from 'react'
import { Camera, Loader2 } from 'lucide-react'
import { useLogMeal } from '../hooks/useApi'
import MacroAnalysisCard from './MacroAnalysisCard'
import type { MealDetail } from '../types/api'

interface Props {
  onMealSaved?: (meal: MealDetail) => void
}

export default function MealCapture({ onMealSaved }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const logMeal = useLogMeal()

  const handleCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Show preview immediately
    setPreview(URL.createObjectURL(file))

    try {
      const result = await logMeal.mutateAsync({ file })
      onMealSaved?.(result)
    } finally {
      setPreview(null)
      // Reset input so same file can be re-selected
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleCapture}
        className="hidden"
      />

      {/* Analysis card shown during upload */}
      {(preview || logMeal.isPending) && (
        <MacroAnalysisCard
          photoUrl={preview}
          isPending={logMeal.isPending}
          error={logMeal.error?.message}
          onCancel={() => {
            setPreview(null)
            if (fileRef.current) fileRef.current.value = ''
          }}
        />
      )}

      {/* FAB */}
      <button
        onClick={() => fileRef.current?.click()}
        disabled={logMeal.isPending}
        className="fixed bottom-24 right-6 md:bottom-8 md:right-8 w-14 h-14 bg-accent text-white rounded-full shadow-lg shadow-accent/20 flex items-center justify-center hover:opacity-90 active:scale-95 transition-all z-30 disabled:opacity-50"
        title="Log a meal"
      >
        {logMeal.isPending ? (
          <Loader2 size={24} className="animate-spin" />
        ) : (
          <Camera size={24} />
        )}
      </button>
    </>
  )
}
```

### 3B. `frontend/src/components/DailySummaryStrip.tsx`

Compact horizontal card showing the day's running macro totals and progress toward daily target. Sits at the top of the Nutrition page.

**Pattern references:**
- Card style from `plans/design-ux-ui.md` Section 11: `bg-surface rounded-xl border border-border shadow-sm`
- Micro label from `plans/design-ux-ui.md` Section 11: `text-[10px] font-bold text-text-muted uppercase tracking-widest`
- Metric large number: `text-3xl font-bold` + color class
- Progress bar: `bg-accent` fill on `bg-surface-low` track
- Existing Dashboard metric card pattern from `frontend/src/pages/Dashboard.tsx` grid

```typescript
import type { DailyNutritionSummary } from '../types/api'

interface Props {
  data: DailyNutritionSummary
}

export default function DailySummaryStrip({ data }: Props) {
  const pct = data.target_calories > 0
    ? Math.min(Math.round((data.total_calories_in / data.target_calories) * 100), 100)
    : 0

  return (
    <div className="bg-surface rounded-xl border border-border p-5 shadow-sm">
      {/* Headline */}
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <span className="text-3xl font-bold text-accent">{data.total_calories_in.toLocaleString()}</span>
          <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-2">kcal</span>
        </div>
        <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">
          {data.remaining_calories > 0 ? `${data.remaining_calories} remaining` : 'Target reached'}
        </span>
      </div>

      {/* Macro breakdown */}
      <div className="flex gap-6 mb-3">
        <MacroStat label="Protein" value={data.total_protein_g} unit="g" color="text-green" />
        <MacroStat label="Carbs" value={data.total_carbs_g} unit="g" color="text-yellow" />
        <MacroStat label="Fat" value={data.total_fat_g} unit="g" color="text-blue" />
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-surface-low rounded-full overflow-hidden">
        <div
          className="h-full bg-accent rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest mt-1.5 text-right">
        {pct}% of daily goal
      </p>
    </div>
  )
}

function MacroStat({ label, value, unit, color }: { label: string; value: number; unit: string; color: string }) {
  return (
    <div>
      <span className={`text-lg font-bold ${color}`}>{Math.round(value)}</span>
      <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest ml-1">{unit}</span>
      <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{label}</p>
    </div>
  )
}
```

### 3C. `frontend/src/components/MacroAnalysisCard.tsx`

In-flight analysis state: shows photo thumbnail + skeleton placeholders while the AI is working. Transitions to populated state when complete. Used by `MealCapture` during upload.

**Pattern references:**
- Skeleton: `animate-pulse bg-surface-low rounded` from `plans/design-ux-ui.md` Section 11
- Loading spinner: `animate-spin text-accent opacity-50` (Loader2 icon)

```typescript
import { Sparkles, X } from 'lucide-react'

interface Props {
  photoUrl: string | null
  isPending: boolean
  error?: string
  onCancel: () => void
}

export default function MacroAnalysisCard({ photoUrl, isPending, error, onCancel }: Props) {
  return (
    <div className="bg-surface rounded-xl border border-border p-5 shadow-sm mb-4">
      <div className="flex gap-4">
        {/* Photo thumbnail */}
        {photoUrl && (
          <div className="w-20 h-20 rounded-lg overflow-hidden shrink-0 bg-surface-low">
            <img src={photoUrl} alt="Meal" className="w-full h-full object-cover" />
          </div>
        )}

        <div className="flex-1 min-w-0">
          {isPending ? (
            <>
              <div className="flex items-center gap-2 mb-3">
                <Sparkles size={16} className="text-accent animate-pulse" />
                <span className="text-sm font-bold text-text uppercase tracking-wider">Analyzing...</span>
              </div>
              {/* Skeleton lines */}
              <div className="space-y-2">
                <div className="animate-pulse bg-surface-low rounded h-4 w-3/4" />
                <div className="animate-pulse bg-surface-low rounded h-4 w-1/2" />
                <div className="animate-pulse bg-surface-low rounded h-4 w-2/3" />
              </div>
            </>
          ) : error ? (
            <div className="text-sm text-red">{error}</div>
          ) : null}
        </div>
      </div>

      {/* Cancel button */}
      <div className="mt-3 flex justify-end">
        <button
          onClick={onCancel}
          className="text-text-muted hover:text-text text-xs font-bold uppercase tracking-widest transition-colors flex items-center gap-1"
        >
          <X size={12} />
          Cancel
        </button>
      </div>
    </div>
  )
}
```

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

---

## Phase 4: MacroCard

### Target file: `frontend/src/components/MacroCard.tsx`

The core display/edit unit for a single meal. Serves double duty: compact display in the timeline, and expanded edit mode when tapped. This is the most complex new component.

**Pattern references:**
- Card: `bg-surface rounded-xl border border-border shadow-sm hover:border-accent/30 transition-all` (from `plans/design-ux-ui.md` Section 11)
- Inline editing: same pattern as workout notes editing in Rides page — `<input>` styled to look like display text until focused
- Delete action: `window.confirm()` before executing, same as ride delete
- Macro color coding from `plans/design-ux-ui.md` Section 5:
  - Calories: `text-accent` (red)
  - Protein: `text-green`
  - Carbs: `text-yellow`
  - Fat: `text-blue`
- Input field: `bg-surface-low text-text border border-border rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20`

```typescript
import { useState } from 'react'
import { Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import { useUpdateMeal, useDeleteMeal } from '../hooks/useApi'
import type { MealSummary } from '../types/api'

interface Props {
  meal: MealSummary
  onAskNutritionist?: (mealContext: string) => void
}

export default function MacroCard({ meal, onAskNutritionist }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [editValues, setEditValues] = useState({
    total_calories: meal.total_calories,
    total_protein_g: meal.total_protein_g,
    total_carbs_g: meal.total_carbs_g,
    total_fat_g: meal.total_fat_g,
  })
  const updateMeal = useUpdateMeal()
  const deleteMeal = useDeleteMeal()

  const hasChanges =
    editValues.total_calories !== meal.total_calories ||
    editValues.total_protein_g !== meal.total_protein_g ||
    editValues.total_carbs_g !== meal.total_carbs_g ||
    editValues.total_fat_g !== meal.total_fat_g

  const handleSave = () => {
    updateMeal.mutate({ id: meal.id, body: editValues })
  }

  const handleDelete = () => {
    if (window.confirm('Delete this meal? This cannot be undone.')) {
      deleteMeal.mutate(meal.id)
    }
  }

  const time = new Date(meal.logged_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

  return (
    <div
      className={`bg-surface rounded-xl border shadow-sm transition-all ${
        expanded ? 'border-accent/30' : 'border-border hover:border-accent/30'
      }`}
    >
      {/* Compact display — always visible */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full text-left p-4 flex gap-3"
      >
        {/* Photo thumbnail */}
        {meal.photo_url && (
          <div className="w-16 h-16 rounded-lg overflow-hidden shrink-0 bg-surface-low">
            <img src={meal.photo_url} alt="" className="w-full h-full object-cover" />
          </div>
        )}

        <div className="flex-1 min-w-0">
          {/* Timestamp + confidence */}
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{time}</span>
            {meal.confidence === 'low' && (
              <span className="text-[10px] font-bold text-yellow uppercase tracking-widest">~</span>
            )}
            {meal.edited_by_user && (
              <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">edited</span>
            )}
          </div>

          {/* Description */}
          <p className="text-sm text-text truncate">{meal.description}</p>

          {/* Macro row */}
          <div className="flex gap-4 mt-1.5">
            <span className="text-sm font-bold text-accent">{meal.total_calories} <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest">kcal</span></span>
            <span className="text-xs text-green font-medium">{Math.round(meal.total_protein_g)}g P</span>
            <span className="text-xs text-yellow font-medium">{Math.round(meal.total_carbs_g)}g C</span>
            <span className="text-xs text-blue font-medium">{Math.round(meal.total_fat_g)}g F</span>
          </div>
        </div>

        <div className="shrink-0 self-center text-text-muted">
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </button>

      {/* Expanded edit mode */}
      {expanded && (
        <div className="border-t border-border px-4 pb-4 pt-3">
          {/* Larger photo */}
          {meal.photo_url && (
            <div className="w-full max-h-48 rounded-lg overflow-hidden mb-3 bg-surface-low">
              <img src={meal.photo_url} alt={meal.description} className="w-full h-full object-cover" />
            </div>
          )}

          {/* Description (read-only) */}
          <p className="text-sm text-text-muted mb-3">{meal.description}</p>

          {/* Editable macro inputs */}
          <div className="grid grid-cols-4 gap-2 mb-3">
            <MacroInput label="KCAL" value={editValues.total_calories} color="text-accent"
              onChange={v => setEditValues(prev => ({ ...prev, total_calories: v }))} />
            <MacroInput label="PROT g" value={editValues.total_protein_g} color="text-green" step={0.1}
              onChange={v => setEditValues(prev => ({ ...prev, total_protein_g: v }))} />
            <MacroInput label="CARBS g" value={editValues.total_carbs_g} color="text-yellow" step={0.1}
              onChange={v => setEditValues(prev => ({ ...prev, total_carbs_g: v }))} />
            <MacroInput label="FAT g" value={editValues.total_fat_g} color="text-blue" step={0.1}
              onChange={v => setEditValues(prev => ({ ...prev, total_fat_g: v }))} />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between">
            <button
              onClick={handleDelete}
              className="p-2 text-text-muted hover:text-red hover:bg-red/5 rounded-md transition-all"
              title="Delete meal"
            >
              <Trash2 size={16} />
            </button>

            <div className="flex items-center gap-2">
              {onAskNutritionist && (
                <button
                  onClick={() => onAskNutritionist(
                    `Tell me about this meal: ${meal.description} (${meal.total_calories} kcal, P${Math.round(meal.total_protein_g)}g / C${Math.round(meal.total_carbs_g)}g / F${Math.round(meal.total_fat_g)}g)`
                  )}
                  className="text-text-muted hover:text-accent text-[10px] font-bold uppercase tracking-widest transition-colors"
                >
                  Ask Nutritionist
                </button>
              )}

              {hasChanges && (
                <button
                  onClick={handleSave}
                  disabled={updateMeal.isPending}
                  className="bg-accent text-white rounded-lg px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest hover:opacity-90 shadow-lg shadow-accent/20 disabled:opacity-50"
                >
                  {updateMeal.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MacroInput({ label, value, color, step = 1, onChange }: {
  label: string; value: number; color: string; step?: number
  onChange: (v: number) => void
}) {
  return (
    <div className="text-center">
      <input
        type="number"
        value={value}
        step={step}
        onChange={e => onChange(Number(e.target.value))}
        className={`w-full bg-surface-low border border-border rounded-lg px-2 py-2 text-center text-sm font-bold ${color} focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20`}
      />
      <span className="text-[10px] font-bold text-text-muted uppercase tracking-widest mt-1 block">{label}</span>
    </div>
  )
}
```

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

---

## Phase 5: MealTimeline + Nutrition Page

### 5A. `frontend/src/components/MealTimeline.tsx`

Scrollable list of MacroCards for a given date, with date navigation.

**Pattern references:**
- Date navigation: ChevronLeft/ChevronRight flanking a date display (same pattern as Rides page)
- Empty state: centered icon + uppercase text, from `plans/design-ux-ui.md` Section 4

```typescript
import { ChevronLeft, ChevronRight, UtensilsCrossed } from 'lucide-react'
import MacroCard from './MacroCard'
import type { MealSummary } from '../types/api'

interface Props {
  meals: MealSummary[]
  date: string
  onDateChange: (date: string) => void
  onAskNutritionist?: (context: string) => void
}

export default function MealTimeline({ meals, date, onDateChange, onAskNutritionist }: Props) {
  const d = new Date(date + 'T12:00:00') // noon to avoid timezone shift
  const today = new Date().toISOString().slice(0, 10)
  const isToday = date === today

  const formatDate = () => {
    if (isToday) return 'Today'
    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)
    if (date === yesterday.toISOString().slice(0, 10)) return 'Yesterday'
    return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
  }

  const shiftDate = (delta: number) => {
    const next = new Date(d)
    next.setDate(next.getDate() + delta)
    onDateChange(next.toISOString().slice(0, 10))
  }

  return (
    <div>
      {/* Date nav */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => shiftDate(-1)} className="p-2 text-text-muted hover:text-text rounded-md transition-colors">
          <ChevronLeft size={20} />
        </button>
        <div className="text-center">
          <span className="text-sm font-bold text-text uppercase tracking-wider">{formatDate()}</span>
          {!isToday && (
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">
              {d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          )}
        </div>
        <button
          onClick={() => shiftDate(1)}
          disabled={isToday}
          className="p-2 text-text-muted hover:text-text rounded-md transition-colors disabled:opacity-30"
        >
          <ChevronRight size={20} />
        </button>
      </div>

      {/* Meal list */}
      {meals.length > 0 ? (
        <div className="space-y-3">
          {meals.map(meal => (
            <MacroCard key={meal.id} meal={meal} onAskNutritionist={onAskNutritionist} />
          ))}
        </div>
      ) : (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <UtensilsCrossed size={64} className="text-text-muted mx-auto opacity-10 mb-4" />
          <p className="text-text-muted font-bold uppercase tracking-widest text-xs mb-1">
            No meals logged {isToday ? 'today' : 'this day'}
          </p>
          <p className="text-text-muted text-xs">Snap a photo to get started</p>
        </div>
      )}
    </div>
  )
}
```

### 5B. `frontend/src/pages/Nutrition.tsx`

Top-level page for the Nutrition tab. Composes DailySummaryStrip, MealTimeline, and MealCapture FAB.

**Pattern references:**
- Page layout from `frontend/src/pages/Dashboard.tsx` — top-level `<div>` with content sections
- Data fetching via custom hooks (same as Dashboard uses `usePMC()`, `useRides()`, etc.)
- Section headers: `px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2`

```typescript
import { useState } from 'react'
import { useMeals, useDailyNutrition } from '../hooks/useApi'
import DailySummaryStrip from '../components/DailySummaryStrip'
import MealTimeline from '../components/MealTimeline'
import MealCapture from '../components/MealCapture'
import { Loader2 } from 'lucide-react'

interface Props {
  onOpenNutritionist?: (context?: string) => void
}

export default function Nutrition({ onOpenNutritionist }: Props) {
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))

  const { data: dailyData, isLoading: dailyLoading } = useDailyNutrition(date)
  const { data: mealsData, isLoading: mealsLoading } = useMeals({
    start_date: date,
    end_date: date,
    limit: 50,
  })

  const isLoading = dailyLoading || mealsLoading

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-sm font-bold text-text uppercase tracking-wider">Nutrition</h1>
      </div>

      {/* Daily summary strip */}
      {dailyData && <DailySummaryStrip data={dailyData} />}

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={24} className="animate-spin text-accent opacity-50" />
        </div>
      )}

      {/* Meal timeline */}
      {!isLoading && (
        <MealTimeline
          meals={mealsData?.meals ?? []}
          date={date}
          onDateChange={setDate}
          onAskNutritionist={onOpenNutritionist}
        />
      )}

      {/* FAB for meal capture */}
      <MealCapture
        onMealSaved={() => {
          // Reset to today if viewing a different date
          const today = new Date().toISOString().slice(0, 10)
          if (date !== today) setDate(today)
        }}
      />
    </div>
  )
}
```

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

---

## Phase 6: Nutritionist Panel (CoachPanel Tab Extension)

### Decision: Modify CoachPanel.tsx to add a tab switcher

Per `plans/design-ux-ui.md` Section 8, the Nutritionist shares the CoachPanel slide-out shell with a tab switcher at the top. Each tab maintains independent message/session state.

### 6A. Create `frontend/src/components/NutritionistPanel.tsx`

This is a self-contained chat component that renders inside the CoachPanel when the "Nutritionist" tab is active. It mirrors the chat logic from `CoachPanel.tsx` (lines 49-78 for state + send logic, lines 158-220 for message rendering) but uses the `useNutritionistChat` hook and `fetchNutritionSession` API.

```typescript
import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { useNutritionistChat, useNutritionSessions } from '../hooks/useApi'
import { fetchNutritionSession } from '../lib/api'
import {
  UtensilsCrossed,
  Plus,
  Send,
  History,
  RefreshCw,
  User as UserIcon,
  ChevronRight,
} from 'lucide-react'

interface Props {
  initialContext?: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function NutritionistPanel({ initialContext }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [loadingSession, setLoadingSession] = useState(false)
  const [showAllSessions, setShowAllSessions] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const chat = useNutritionistChat()
  const { data: sessions } = useNutritionSessions()
  const sentInitialRef = useRef(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-send initial context if provided (from "Ask Nutritionist" on a MacroCard)
  useEffect(() => {
    if (initialContext && !sentInitialRef.current) {
      sentInitialRef.current = true
      sendMessage(initialContext)
    }
  }, [initialContext])

  const sendMessage = async (msg: string) => {
    if (!msg.trim() || chat.isPending) return
    setMessages(prev => [...prev, { role: 'user', content: msg.trim() }])

    try {
      const res = await chat.mutateAsync({ message: msg.trim(), session_id: sessionId })
      setSessionId(res.session_id)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error getting response. Please try again.' }])
    }
  }

  const send = () => {
    if (!input.trim()) return
    const msg = input.trim()
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    sendMessage(msg)
  }

  const newSession = () => {
    setMessages([])
    setSessionId(undefined)
    sentInitialRef.current = false
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Session toolbar */}
      <div className="flex items-center justify-end px-5 py-2 border-b border-border bg-surface-low/30">
        <button
          onClick={newSession}
          className="p-1.5 text-text-muted hover:text-green hover:bg-green/5 rounded-md transition-all"
          title="New Nutritionist Chat"
        >
          <Plus size={16} />
        </button>
      </div>

      {/* Recent sessions */}
      {messages.length === 0 && sessions && sessions.length > 0 && (
        <div className="border-b border-border px-5 py-4 bg-surface-low/30">
          <div className="flex items-center gap-2 mb-3 text-text-muted">
            <History size={12} />
            <span className="text-[10px] font-bold uppercase tracking-widest">Recent Sessions</span>
          </div>
          <div className={`space-y-2 ${showAllSessions ? 'max-h-60 overflow-y-auto pr-1' : ''}`}>
            {sessions.slice(0, showAllSessions ? undefined : 4).map(s => (
              <button
                key={s.session_id}
                onClick={async () => {
                  setLoadingSession(true)
                  try {
                    const detail = await fetchNutritionSession(s.session_id)
                    setSessionId(s.session_id)
                    const loaded: Message[] = detail.messages
                      .filter(m => m.content_text)
                      .map(m => ({
                        role: m.role === 'user' ? 'user' : 'assistant',
                        content: m.content_text!,
                      }))
                    setMessages(loaded)
                  } finally {
                    setLoadingSession(false)
                  }
                }}
                className="group flex items-center justify-between w-full px-3 py-2 bg-surface border border-border rounded-lg text-xs text-text-muted hover:text-text hover:border-green hover:bg-surface-high transition-all shadow-sm"
              >
                <span className="truncate pr-4 font-medium">{s.title || 'Untitled Session'}</span>
                <ChevronRight size={12} className="opacity-0 group-hover:opacity-100 transition-opacity text-green" />
              </button>
            ))}
          </div>
          {sessions.length > 4 && (
            <button
              onClick={() => setShowAllSessions(prev => !prev)}
              className="w-full text-center text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-green mt-3 py-1 transition-colors"
            >
              {showAllSessions ? 'Show Less' : 'Show More'}
            </button>
          )}
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-5 py-6 space-y-6 bg-surface">
        {loadingSession && (
          <div className="flex flex-col items-center justify-center py-12 space-y-3">
            <RefreshCw size={24} className="animate-spin text-green opacity-40" />
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest italic">Restoring context...</p>
          </div>
        )}

        {messages.length === 0 && !loadingSession && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="w-16 h-16 bg-surface-low rounded-full flex items-center justify-center mb-4 border border-border">
              <UtensilsCrossed size={24} className="text-green opacity-20" />
            </div>
            <p className="text-sm font-bold text-text uppercase tracking-widest mb-1">Nutritionist is ready</p>
            <p className="text-xs text-text-muted font-medium px-8 leading-relaxed">
              Ask about meal planning, fueling strategy, or macro targets.
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center border shadow-sm ${
              m.role === 'user'
                ? 'bg-green/10 border-green/20 text-green'
                : 'bg-surface-high border-border text-text-muted'
            }`}>
              {m.role === 'user' ? <UserIcon size={14} /> : <UtensilsCrossed size={14} />}
            </div>
            <div className={`max-w-[85%] text-sm leading-relaxed ${
              m.role === 'user'
                ? 'bg-green text-white rounded-2xl rounded-tr-none px-4 py-2.5 shadow-md shadow-green/10'
                : 'text-text'
            }`}>
              {m.role === 'assistant' ? (
                <div className="prose prose-sm prose-invert max-w-none 
                  [&_p]:my-1.5 [&_ul]:my-2 [&_li]:my-1 [&_strong]:text-green [&_strong]:font-bold
                  [&_code]:bg-surface-low [&_code]:px-1 [&_code]:rounded [&_code]:text-blue">
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{m.content}</p>
              )}
            </div>
          </div>
        ))}

        {chat.isPending && (
          <div className="flex gap-3 animate-pulse">
            <div className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-surface-high border border-border text-text-muted">
              <UtensilsCrossed size={14} />
            </div>
            <div className="flex items-center gap-1 px-4 py-2 text-text-muted italic text-xs bg-surface-low rounded-2xl rounded-tl-none">
              <span className="w-1.5 h-1.5 bg-green rounded-full animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 bg-green rounded-full animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 bg-green rounded-full animate-bounce" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="p-5 bg-surface-low border-t border-border">
        <div className="relative group">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => {
              setInput(e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px'
            }}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Ask your nutritionist..."
            rows={1}
            className="w-full bg-surface text-text border border-border rounded-xl px-4 py-3.5 pr-12 text-sm placeholder:text-text-muted/40 focus:outline-none focus:border-green focus:ring-1 focus:ring-green/20 transition-all shadow-sm resize-none overflow-y-auto"
            style={{ maxHeight: 150 }}
          />
          <button
            onClick={send}
            disabled={chat.isPending || !input.trim()}
            className="absolute right-2.5 bottom-2.5 p-2 bg-green text-white rounded-lg disabled:opacity-30 disabled:grayscale hover:opacity-90 active:scale-95 transition-all shadow-lg shadow-green/20"
          >
            {chat.isPending ? <RefreshCw size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
        <p className="text-[9px] font-bold text-text-muted uppercase tracking-widest mt-2 text-center opacity-30">Press Enter to send</p>
      </div>
    </div>
  )
}
```

### 6B. Modify `frontend/src/components/CoachPanel.tsx`

Add a tab switcher below the header. Each tab renders its own chat content. The Coach tab keeps all its existing logic; the Nutritionist tab renders `NutritionistPanel`.

**Changes to make:**

1. **Add imports** at the top (after line 16):
   ```typescript
   import NutritionistPanel from './NutritionistPanel'
   import { UtensilsCrossed } from 'lucide-react'
   ```

2. **Add state for active agent tab** inside the component (after line 53, near other `useState` calls):
   ```typescript
   const [agentTab, setAgentTab] = useState<'coach' | 'nutritionist'>('coach')
   ```

3. **Accept optional prop for nutritionist context.** Update the `Props` interface (at line 18):
   ```typescript
   interface Props {
     onClose: () => void
     viewContext?: ViewContext
     nutritionistContext?: string  // Pre-filled context from "Ask Nutritionist" on a MacroCard
   }
   ```
   And destructure it:
   ```typescript
   export default function CoachPanel({ onClose, viewContext, nutritionistContext }: Props) {
   ```

4. **When nutritionistContext is provided, auto-switch to Nutritionist tab:**
   ```typescript
   useEffect(() => {
     if (nutritionistContext) setAgentTab('nutritionist')
   }, [nutritionistContext])
   ```

5. **Insert the tab switcher** right after the header `</div>` (after line 110, after the header block closing):
   ```typescript
   {/* Agent tab switcher */}
   <div className="flex border-b border-border bg-surface-low/30 px-5 py-2 gap-2">
     <button
       onClick={() => setAgentTab('coach')}
       className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest transition-all ${
         agentTab === 'coach'
           ? 'bg-accent text-white'
           : 'text-text-muted hover:text-text'
       }`}
     >
       <Bot size={12} />
       Coach
     </button>
     <button
       onClick={() => setAgentTab('nutritionist')}
       className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest transition-all ${
         agentTab === 'nutritionist'
           ? 'bg-green text-white'
           : 'text-text-muted hover:text-text'
       }`}
     >
       <UtensilsCrossed size={12} />
       Nutritionist
     </button>
   </div>
   ```

6. **Conditionally render content.** Wrap the existing Coach chat content (Recent Sessions + Messages + Input area, lines 112-248) in `{agentTab === 'coach' && ( ... )}`. After it, add:
   ```typescript
   {agentTab === 'nutritionist' && (
     <NutritionistPanel initialContext={nutritionistContext} />
   )}
   ```

**Key design notes:**
- The Coach tab retains 100% of its existing code — no logic changes, just wrapped in a conditional.
- The Nutritionist tab uses `bg-green` instead of `bg-accent` for its send button, user message bubbles, and tab pill — providing the visual differentiation specified in `plans/design-ux-ui.md` Section 8.
- The `UtensilsCrossed` icon replaces `Bot` in the Nutritionist's avatar, matching the design spec.

### Verification

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20
```

---

## Phase 7: Navigation Integration (Layout.tsx + App.tsx)

### 7A. Modify `frontend/src/components/Layout.tsx`

**Change 1: Add `UtensilsCrossed` to lucide imports** (line 6-16).

Add `UtensilsCrossed` to the import from `lucide-react`:
```typescript
import {
  LayoutDashboard,
  Bike,
  CalendarDays,
  TrendingUp,
  UtensilsCrossed,   // ADD
  MessageSquare,
  Sun,
  Moon,
  Users,
  Settings,
} from 'lucide-react'
```

**Change 2: Add 'nutrition' to the `tabs` array** (line 18-23).

Insert the nutrition tab after `analysis`:
```typescript
const tabs = [
  { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { key: 'rides', label: 'Rides', icon: Bike },
  { key: 'calendar', label: 'Calendar', icon: CalendarDays },
  { key: 'analysis', label: 'Analysis', icon: TrendingUp },
  { key: 'nutrition', label: 'Nutrition', icon: UtensilsCrossed },  // ADD
] as const
```

**Change 3: Update TabKey type** (line 25).

The TabKey type is derived from the `tabs` array: `(typeof tabs)[number]['key']`. Since we added `'nutrition'` to the array, it's automatically included. No manual change needed — the type derives from the data.

**Change 4: Pass nutritionist context prop to CoachPanel** (line 131).

Update the CoachPanel render to pass the nutritionistContext:
```typescript
{coachOpen && (
  <CoachPanel
    onClose={() => setCoachOpen(false)}
    viewContext={viewContext}
    nutritionistContext={nutritionistContext}
  />
)}
```

This requires adding state and a callback prop to Layout:

Add to `LayoutProps` interface (line 34-39):
```typescript
interface LayoutProps {
  activeTab: TabKey
  onTabChange: (tab: TabKey) => void
  viewContext?: ViewContext
  nutritionistContext?: string             // ADD
  onOpenNutritionist?: (context?: string) => void  // ADD
  children: ReactNode
}
```

Destructure the new props:
```typescript
export default function Layout({ activeTab, onTabChange, viewContext, nutritionistContext, onOpenNutritionist, children }: LayoutProps) {
```

**Change 5: Add 'nutrition' to the `buildViewHint` function** in `CoachPanel.tsx` (line 28-46).

Add a case in the switch:
```typescript
case 'nutrition': parts.push('Viewing: Nutrition'); break
```

### 7B. Modify `frontend/src/App.tsx`

**Change 1: Add Nutrition page import** (after line 10):
```typescript
import Nutrition from './pages/Nutrition'
```

**Change 2: Add nutritionist context state** (after line 17):
```typescript
const [nutritionistContext, setNutritionistContext] = useState<string | undefined>()
```

**Change 3: Create handler to open nutritionist with context:**
```typescript
const handleOpenNutritionist = (context?: string) => {
  setNutritionistContext(context)
  // CoachPanel opens automatically via Layout — the nutritionistContext triggers the Nutritionist tab
}
```

**Change 4: Pass new props to Layout** (line 52):
```typescript
<Layout
  activeTab={tab}
  onTabChange={t => { setTab(t); setRideId(undefined); setRideDate(undefined); setCalendarDate(undefined); setNutritionistContext(undefined) }}
  viewContext={viewContext}
  nutritionistContext={nutritionistContext}
  onOpenNutritionist={handleOpenNutritionist}
>
```

**Change 5: Add Nutrition page render branch** (after line 69, before `{tab === 'settings'...}`):
```typescript
{tab === 'nutrition' && (
  <Nutrition onOpenNutritionist={handleOpenNutritionist} />
)}
```

### 7C. Modify `CoachPanel.tsx` — buildViewHint

Add the `'nutrition'` case to the switch statement in `buildViewHint()` at line 31-44:

```typescript
case 'nutrition': parts.push('Viewing: Nutrition'); break
```

### Verification

```bash
cd frontend && npm run build 2>&1 | tail -5
# Should complete with no errors
```

---

## Phase 8: Build Verification + Final Checklist

### 8A. TypeScript Compilation Check

```bash
cd frontend && npx tsc --noEmit --pretty
```

Expected: zero errors. If there are type errors, they'll point to exact file:line. Common issues:
- Missing import for a new type → add to the import block
- Property mismatch between API response and TypeScript type → align with backend schema
- Missing `MealItem` import in `api.ts` → add to the type import line

### 8B. Vite Build Check

```bash
cd frontend && npm run build
```

Expected: successful build with bundle output. This catches:
- JSX syntax errors
- Missing module imports
- CSS class conflicts (unlikely with Tailwind)

### 8C. Lint Check (if ESLint is configured)

```bash
cd frontend && npx eslint src/types/api.ts src/lib/api.ts src/hooks/useApi.ts src/components/MealCapture.tsx src/components/DailySummaryStrip.tsx src/components/MacroAnalysisCard.tsx src/components/MacroCard.tsx src/components/MealTimeline.tsx src/components/NutritionistPanel.tsx src/pages/Nutrition.tsx src/components/CoachPanel.tsx src/components/Layout.tsx src/App.tsx --quiet
```

### 8D. New File Inventory

| File | Type | Action |
|------|------|--------|
| `frontend/src/types/api.ts` | Types | MODIFY — add nutrition interfaces at end |
| `frontend/src/lib/api.ts` | API client | MODIFY — add nutrition API functions at end |
| `frontend/src/hooks/useApi.ts` | Hooks | MODIFY — add nutrition hooks at end |
| `frontend/src/components/MealCapture.tsx` | Component | NEW — camera FAB + upload trigger |
| `frontend/src/components/DailySummaryStrip.tsx` | Component | NEW — daily macro totals bar |
| `frontend/src/components/MacroAnalysisCard.tsx` | Component | NEW — in-flight analysis skeleton |
| `frontend/src/components/MacroCard.tsx` | Component | NEW — single meal display/edit card |
| `frontend/src/components/MealTimeline.tsx` | Component | NEW — scrollable meal list + date nav |
| `frontend/src/components/NutritionistPanel.tsx` | Component | NEW — nutritionist chat content |
| `frontend/src/pages/Nutrition.tsx` | Page | NEW — top-level Nutrition tab page |
| `frontend/src/components/CoachPanel.tsx` | Component | MODIFY — add tab switcher (Coach/Nutritionist) |
| `frontend/src/components/Layout.tsx` | Component | MODIFY — add 'nutrition' tab + icon |
| `frontend/src/App.tsx` | App root | MODIFY — add Nutrition page render branch |

### 8E. Deferred to v2 (NOT in this plan)

Per `plans/macro-tracker-design.md` v1/v2/v3 scope split:

**Deferred to v2 (Intelligence Layer):**
- Dashboard energy balance widget with sparkline (`NutritionDashboardWidget`)
- Weekly summary stacked bar chart (Chart.js)
- Voice note recording (`VoiceNoteButton`)
- Swipe gestures on MacroCards
- Bottom sheet animation for analysis results on mobile
- Pull-to-refresh on timeline

**Deferred to v3 (Offline Support):**
- IndexedDB meal queuing and retry on connectivity
- `CloudOff` indicator on pending meals
- Background sync for photos
- Offline macro entry without AI analysis

These are tracked in the Master Roadmap under Campaigns 2 and 3 respectively.

### 8F. Dependency Check

No new npm packages are required. All functionality uses existing dependencies:
- `@tanstack/react-query` ^5.95.2 — already installed (React Query v5)
- `lucide-react` ^1.7.0 — already installed (`UtensilsCrossed`, `Camera`, `Sparkles` icons are in the set)
- `react-markdown` — already installed (used by `CoachPanel.tsx`)
- `chart.js` ^4.5.1 — already installed (for future v2 charts, not needed in v1)

Verify:
```bash
cd frontend && node -e "const p = require('./package.json'); console.log('@tanstack/react-query:', p.dependencies['@tanstack/react-query']); console.log('lucide-react:', p.dependencies['lucide-react']); console.log('react-markdown:', p.dependencies['react-markdown'])"
```
