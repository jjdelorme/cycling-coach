# Macro Tracker — UX/UI Design Proposal
> **Version target:** v1.9.x

## Design Philosophy

The existing app has a strong, opinionated visual language: dark-first with light mode, Inter font, uppercase tracking-widest micro-labels, `rounded-xl` cards with `border-border` + `shadow-sm`, accent-red for CTAs, and a bottom-tab mobile nav. The Macro Tracker must feel native to this system — not bolted on. Every new screen reuses the existing component vocabulary: `bg-surface`, `bg-surface-low` section headers, `text-[10px] font-bold uppercase tracking-widest` labels, the same lucide-react icon set, and the same `hover:border-accent/30 transition-all` card interactions.

The key constraint: **this feature is used on a phone, standing in a kitchen, with one hand free.** The capture flow must complete in under 5 seconds from app open to photo taken. Everything else (editing macros, browsing history) can be slower.

---

## 1. Navigation Integration

### Decision: New "Nutrition" bottom tab

Add a 5th tab to the mobile bottom nav and desktop top nav, positioned between "Analysis" and the "Coach" button.

```
Mobile bottom nav (current):
[ Dashboard | Rides | Calendar | Analysis | Coach ]

Mobile bottom nav (new):
[ Dashboard | Rides | Calendar | Nutrition | Coach ]
```

**Icon:** `UtensilsCrossed` from lucide-react.

**Why not a sub-tab or modal?** The feature is a peer of Rides and Calendar — it has its own data model, its own history, its own AI agent. Burying it under Settings or the Coach panel would make the 5-second capture flow impossible. A dedicated tab also gives us room for the meal history timeline without cramping existing views.

**TabKey addition:** `'nutrition'` added to the `TabKey` union type. The `Nutrition` page component lazy-loads to keep the initial bundle small.

### Desktop layout

On desktop, the Nutrition tab shows as a standard nav button alongside Dashboard/Rides/Calendar/Analysis. The Nutritionist chat panel shares the same `CoachPanel` slide-out pattern but with a distinct header icon and color (green accent instead of red) to visually separate it from the cycling coach.

---

## 2. User Flows

### Flow A: Quick Capture (primary — optimized for speed)

```
[Nutrition tab] → tap FAB → [Camera viewfinder / file picker] → photo taken
→ [Analysis card appears with spinner] → [Macro card populates] → [Save]
```

Step-by-step:

1. **User opens Nutrition tab.** Sees today's meal timeline (or empty state prompting first log).
2. **Taps the floating action button (FAB).** Large, always-visible, bottom-right, accent-colored circle with `Camera` icon. On mobile this is the dominant CTA.
3. **Native camera/file picker opens.** Uses `<input type="file" accept="image/*" capture="environment">` for direct camera access on mobile. On desktop, opens standard file picker.
4. **Photo selected → upload begins immediately.** No intermediate "confirm photo" screen. The photo streams to the backend while the UI transitions to the Analysis Card.
5. **Analysis Card shows.** Photo thumbnail on the left, animated skeleton placeholders on the right for calories/protein/carbs/fat. A pulsing `Sparkles` icon indicates AI is working. Typical wait: 3-8 seconds.
6. **Macros populate.** Numbers animate in. Card becomes editable (see Section 4).
7. **User taps "Save".** Meal is persisted. Card slides into the timeline. Done.

Total taps from tab to saved: **3** (FAB → take photo → Save).

### Flow B: Capture with Voice Note

Between steps 3 and 4, user can optionally hold a `Mic` button overlay to add a voice comment ("that's about 6 ounces of chicken, grilled"). The audio blob is uploaded alongside the image and passed **directly to Gemini as a multimodal input** — image + audio as separate `Part` objects in the same content array. This lets Gemini hear the user's description while also seeing the photo, improving identification accuracy without any intermediate transcription step.

**Implementation:** `MediaRecorder` API, push-to-talk UX (hold to record, release to stop). Visual feedback: red pulsing ring around the mic icon + elapsed time counter. Max 15 seconds. Audio is sent as `audio/webm` (or `audio/mp4` on iOS) — both are supported Gemini MIME types.

### Flow C: AI Clarification Dialog

If the AI returns a `confidence: "low"` flag (e.g., can't identify a dish, ambiguous portion size):

1. The Analysis Card renders normally but with an amber `AlertTriangle` warning badge.
2. Below the macro numbers, a clarification prompt appears: *"I'm not sure about the portion size. Is this roughly 1 cup or 2 cups of rice?"*
3. User types or speaks a response in a single-line input.
4. AI re-analyzes with the additional context. Numbers update in-place.
5. If still uncertain, the AI makes its best guess and marks the entry with a `~` approximate indicator.

**Design tradeoff:** I considered a multi-step wizard for clarification but rejected it — too many taps. A single inline text field keeps the user on the same screen and preserves the "one-shot" feel.

### Flow D: Manual Edit After Save

Any saved meal can be tapped to re-open the Macro Card in edit mode. Numbers are inline-editable (tap to type). Changes auto-save on blur. This covers the case where the AI was wrong and the user knows the actual values.

---

## 3. Component Breakdown

### New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `Nutrition` | `pages/Nutrition.tsx` | Top-level page, meal timeline + FAB |
| `MealCapture` | `components/MealCapture.tsx` | Camera/upload trigger + voice note |
| `MacroCard` | `components/MacroCard.tsx` | Single meal display: photo + macros, editable |
| `MacroAnalysisCard` | `components/MacroAnalysisCard.tsx` | In-flight analysis state (skeleton → populated) |
| `MealTimeline` | `components/MealTimeline.tsx` | Day/week scrollable meal list |
| `DailySummaryStrip` | `components/DailySummaryStrip.tsx` | Horizontal summary bar: total cal/protein/carbs/fat for the day |
| `NutritionDashboardWidget` | `components/NutritionDashboardWidget.tsx` | "Calories In vs Out" card for the main Dashboard |
| `NutritionistPanel` | `components/NutritionistPanel.tsx` | Nutritionist AI chat (extends CoachPanel pattern) |
| `VoiceNoteButton` | `components/VoiceNoteButton.tsx` | Push-to-talk mic button |

### Modified Components

| Component | Change |
|-----------|--------|
| `Layout.tsx` | Add `'nutrition'` tab, add `UtensilsCrossed` icon import, add Nutritionist panel toggle |
| `App.tsx` | Add `Nutrition` page render branch, add `TabKey` update |
| `Dashboard.tsx` | Add `NutritionDashboardWidget` in the grid |

### New Hooks

| Hook | Purpose |
|------|---------|
| `useMeals(params?)` | Fetch meal history (date-filtered) |
| `useMeal(id)` | Fetch single meal detail |
| `useLogMeal()` | Mutation: upload photo + optional audio, receive AI analysis |
| `useUpdateMeal()` | Mutation: edit macro values on a saved meal |
| `useDeleteMeal()` | Mutation: remove a meal |
| `useDailyNutrition(date)` | Aggregated daily totals |
| `useNutritionistChat()` | Separate chat mutation for the Nutritionist agent |

### New Types

```typescript
interface Meal {
  id: number
  logged_at: string          // ISO timestamp
  image_url: string          // GCS signed URL
  calories: number
  protein_g: number
  carbs_g: number
  fat_g: number
  description?: string       // AI-generated meal description
  confidence: 'high' | 'medium' | 'low'
  voice_note_url?: string
  user_edited: boolean       // true if user manually adjusted macros
}

interface DailyNutrition {
  date: string
  total_calories: number
  total_protein_g: number
  total_carbs_g: number
  total_fat_g: number
  meal_count: number
  calories_out?: number      // from rides on this date
}

interface MealAnalysisResponse {
  meal_id: number
  calories: number
  protein_g: number
  carbs_g: number
  fat_g: number
  description: string
  confidence: 'high' | 'medium' | 'low'
  clarification_prompt?: string
}
```

---

## 4. Meal Logging Screen (Nutrition Page)

### Layout — Mobile (primary)

```
┌──────────────────────────────────┐
│ ▼ NUTRITION          [filter] [🧑‍🍳]│  ← page header + nutritionist toggle
├──────────────────────────────────┤
│ ┌────────────────────────────┐   │
│ │ TODAY · Apr 9              │   │
│ │ 1,847 kcal  ·  142g P     │   │  ← DailySummaryStrip
│ │ 218g C  ·  62g F           │   │
│ │ ████████████░░░░ 78% goal  │   │  ← progress bar vs daily target
│ └────────────────────────────┘   │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ 🕐 12:34 PM                  │ │
│ │ ┌──────┐  Grilled chicken   │ │  ← MacroCard
│ │ │ 📷   │  salad w/ quinoa   │ │
│ │ │ thumb│  ───────────────── │ │
│ │ └──────┘  487 kcal          │ │
│ │           38g P · 42g C · 18g F│
│ └──────────────────────────────┘ │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ 🕐 8:15 AM                   │ │
│ │ ┌──────┐  Oatmeal w/ banana │ │  ← MacroCard
│ │ │ 📷   │  and peanut butter │ │
│ │ │ thumb│  ───────────────── │ │
│ │ └──────┘  520 kcal          │ │
│ │           18g P · 72g C · 16g F│
│ └──────────────────────────────┘ │
│                                  │
│                          ┌─────┐ │
│                          │ 📷  │ │  ← FAB (floating action button)
│                          │     │ │
│                          └─────┘ │
├──────────────────────────────────┤
│ [Dash] [Rides] [Cal] [Nutr] [Coach]│ ← bottom nav
└──────────────────────────────────┘
```

### DailySummaryStrip

A compact horizontal card at the top of the page showing the day's running totals. Matches the existing metric card pattern (`bg-surface rounded-xl border border-border p-5 shadow-sm`).

- **Headline number:** Total calories in large bold (`text-3xl font-bold text-accent`)
- **Macro breakdown:** Protein / Carbs / Fat in the standard `text-[10px] font-bold text-text-muted uppercase tracking-widest` micro-label style
- **Progress bar:** Thin rounded bar showing % of daily calorie target (target comes from athlete settings). Uses `bg-accent` fill on `bg-surface-low` track.

### Date Navigation

Same pattern as the Rides page date navigator: `ChevronLeft` / `ChevronRight` buttons flanking a date display. Swipe gestures on mobile for day-to-day navigation (using touch events, no external swipe library).

### Empty State

When no meals are logged:
```
┌──────────────────────────────────┐
│         [UtensilsCrossed icon]   │
│     (large, opacity-10)         │
│                                  │
│   NO MEALS LOGGED TODAY          │  ← text-text-muted font-bold
│   Snap a photo to get started   │     uppercase tracking-widest text-xs
│                                  │
│        [ 📷 Log a Meal ]         │  ← accent button, same style as
│                                  │     "Analyze" button in Rides
└──────────────────────────────────┘
```

### FAB (Floating Action Button)

- **Size:** 56px circle (`w-14 h-14`)
- **Position:** `fixed bottom-24 right-6` on mobile (above the bottom nav), `fixed bottom-8 right-8` on desktop
- **Style:** `bg-accent text-white rounded-full shadow-lg shadow-accent/20`
- **Icon:** `Camera` (24px)
- **Animation:** Subtle scale pulse on idle (`animate-pulse` but gentle, 0.97-1.03 scale)
- **Tap behavior:** Opens native file picker with `capture="environment"` attribute

### In-Flight Analysis State

When a photo is captured, the MacroAnalysisCard slides up from the bottom (mobile) or appears inline (desktop):

```
┌──────────────────────────────────┐
│ ┌──────┐  ✨ Analyzing...       │
│ │      │  ░░░░░░░░░░░░░░░░░░░  │  ← skeleton lines
│ │ photo│  ░░░░░░░░░░░           │
│ │      │  ░░░░░░░░░░░░░░░       │
│ └──────┘                         │
│                                  │
│           [Cancel]               │
└──────────────────────────────────┘
```

Uses the existing skeleton/pulse animation pattern (`animate-pulse bg-surface-low rounded`). The `Sparkles` icon from lucide-react provides the "AI working" visual cue — same approach the Coach panel uses with its bouncing dots.

---

## 5. MacroCard — Detailed Design

The MacroCard is the core display unit. It serves double duty: display mode in the timeline, and edit mode when tapped.

### Display Mode

```
┌──────────────────────────────────┐
│ 🕐 12:34 PM                ~    │  ← timestamp + optional ~ for low confidence
│ ┌──────┐                         │
│ │      │  Grilled chicken salad  │  ← AI-generated description
│ │ 72x72│  with quinoa and        │
│ │ thumb│  mixed greens           │
│ └──────┘                         │
│ ┌────────┬────────┬────────┬────────┐
│ │  487   │  38g   │  42g   │  18g   │  ← macro values
│ │  KCAL  │ PROTEIN│ CARBS  │  FAT   │  ← micro-labels
│ │ accent │ green  │ yellow │ blue   │  ← color coding
│ └────────┴────────┴────────┴────────┘
└──────────────────────────────────┘
```

**Macro color coding** (consistent throughout the app):
- Calories: `text-accent` (red) — the hero number
- Protein: `text-green` — matches existing CTL/fitness color
- Carbs: `text-yellow` — matches existing warning/alert color
- Fat: `text-blue` — matches existing power color

This reuses the existing color palette without introducing new tokens.

### Edit Mode (tap to expand)

When a MacroCard is tapped, it expands inline (no modal, no new screen):

```
┌──────────────────────────────────┐
│ 🕐 12:34 PM         [🗑️ Delete] │
│ ┌──────────────────┐             │
│ │                  │             │
│ │   full photo     │             │  ← larger photo preview
│ │   (tappable to   │             │
│ │    view full)    │             │
│ │                  │             │
│ └──────────────────┘             │
│ Grilled chicken salad...         │  ← description (read-only)
│                                  │
│ ┌────────┬────────┬────────┬────────┐
│ │ [487 ] │ [38  ] │ [42  ] │ [18  ] │ ← editable inputs
│ │  KCAL  │ PROT g │ CARBS g│  FAT g │
│ └────────┴────────┴────────┴────────┘
│                                  │
│ ┌──────────────────────────────┐ │
│ │ Ask the nutritionist about   │ │  ← quick action: opens
│ │ this meal →                  │ │     nutritionist chat with
│ └──────────────────────────────┘ │     meal context pre-filled
│                                  │
│         [Save Changes]           │  ← only visible if values changed
└──────────────────────────────────┘
```

**Inline editing:** Each macro value is a `<input type="number">` styled to look like the display value until focused. On focus, it gains the standard `focus:border-accent focus:ring-1 focus:ring-accent/20` treatment. Changes are tracked locally and a "Save Changes" button appears when any value differs from the stored value. This mirrors the athlete notes editing pattern in `Rides.tsx`.

**Delete action:** Small `Trash2` icon button in the header, same pattern as the ride delete button — prompts `window.confirm()` before executing.

---

## 6. Meal History View

### Default View: Today

The Nutrition page defaults to showing today's meals in reverse chronological order (most recent first). The DailySummaryStrip at the top shows running totals.

### Date Filtering

A date picker control at the top of the page, reusing the Rides page filter pattern:

```
┌─────────────────────────────────────────────┐
│ [Filter icon] [date picker] [← →] [Go]     │
└─────────────────────────────────────────────┘
```

Additional filter option: **Week view** toggle. When toggled, shows a 7-day summary with a stacked bar chart (Chart.js `Bar`, horizontal, one bar per day, segments colored by P/C/F ratio).

### Week Summary View

```
┌──────────────────────────────────┐
│ WEEKLY NUTRITION · Apr 7-13      │
├──────────────────────────────────┤
│ Avg Daily: 2,150 kcal            │
│ Avg Protein: 155g · Carbs: 245g  │  ← weekly averages
│ Avg Fat: 72g                     │
│                                  │
│ Mon ████████████████░░░  2,340   │
│ Tue ██████████████░░░░░  1,980   │  ← daily bar chart
│ Wed ███████████████████  2,450   │     (stacked P/C/F colors)
│ Thu ████████████░░░░░░░  1,750   │
│ Fri ██████████████████░  2,200   │
│ Sat ░░░░░░░░░░░░░░░░░░░  --     │  ← no meals logged
│ Sun ░░░░░░░░░░░░░░░░░░░  --     │
└──────────────────────────────────┘
```

Implemented with Chart.js `Bar` (horizontal), matching the Weekly Training Load chart pattern from Dashboard.tsx. Same tooltip styling, same axis formatting.

---

## 7. Dashboard Integration: "Calories In vs Out" Widget

A new card added to the Dashboard grid, positioned after "Next Workout" and "Latest Ride" in the `grid-cols-1 lg:grid-cols-2` layout.

### Widget Design

```
┌──────────────────────────────────┐
│ 🍎 ENERGY BALANCE · Today       │  ← section header (bg-surface-low)
├──────────────────────────────────┤
│                                  │
│    IN          OUT        NET    │
│  1,847       2,340       -493   │  ← large bold numbers
│   kcal        kcal        kcal  │
│  ●●●○○       ██████      ▼ red  │
│  3 meals     Morning Ride       │
│                                  │
│  ┌─────────────────────────────┐│
│  │▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░ ││ ← ratio bar (in vs out)
│  │  in: 44%        out: 56%   ││
│  └─────────────────────────────┘│
│                                  │
│  This Week ──────────────────── │
│  ┌─ mini sparkline chart ─────┐ │  ← 7-day trend (small Line chart)
│  │  net cal balance per day   │ │
│  └────────────────────────────┘ │
│                                  │
│  [ Log a Meal → ]                │  ← CTA to Nutrition tab
└──────────────────────────────────┘
```

**Data sources:**
- "Calories In" — summed from today's meals (`useDailyNutrition(today)`)
- "Calories Out" — `total_calories` from today's ride(s) (already in `RideSummary.total_calories`) plus estimated BMR (from athlete settings or a simple estimate)
- "Net" — difference, colored green (surplus) or red (deficit)

**Sparkline:** A tiny Chart.js `Line` showing the last 7 days of net calorie balance. Uses the same minimal chart options as the PMC chart but at small scale (`h-16`). No axis labels, just the trend line.

**"Log a Meal" CTA:** Routes to the Nutrition tab. Same button style as other dashboard CTAs (`text-accent text-xs font-bold uppercase tracking-widest`).

### This Week Compact Strip

Extends the existing weekly summary pattern. If the user has no meals logged, the widget shows an empty state with a prompt instead.

---

## 8. Nutritionist Chat

### Decision: Separate chat panel, shared shell

The Nutritionist is a **separate tab within the CoachPanel slide-out**, not a separate panel. This avoids adding a second slide-out mechanism and keeps the UI clean.

### Implementation

Modify `CoachPanel.tsx` to support two modes:

```
┌─────────────────────────────────────┐
│ [🚴 Coach] [🧑‍🍳 Nutritionist]       │  ← tab switcher at top
│─────────────────────────────────────│
│                                     │
│  (chat messages for active agent)   │
│                                     │
│─────────────────────────────────────│
│ [ Ask your nutritionist... ]  [▶]  │
└─────────────────────────────────────┘
```

**Tab switcher:** Two pill buttons at the top of the panel, below the header. Active tab uses `bg-accent text-white`, inactive uses `text-text-muted hover:text-text`. Each tab maintains its own message history and session.

**Color differentiation:**
- Coach: red accent (existing `#e94560`)
- Nutritionist: green accent (`#00d4aa`, the existing `--color-green`)

When the Nutritionist tab is active, the send button and user message bubbles use `bg-green` instead of `bg-accent`. The bot avatar shows `UtensilsCrossed` instead of `Bot`.

**Context passing:** When the Nutritionist chat opens from a MacroCard's "Ask about this meal" button, the meal context (photo URL, macro values, description) is automatically prepended to the first message as a view hint, similar to how `buildViewHint` works for the Coach today.

**Agent-to-Agent (A2A):** The cycling coach and nutritionist can consult each other server-side via the ADK Agent2Agent protocol. This is transparent to the UI — from the user's perspective, they chat with one agent at a time, and the agents coordinate behind the scenes. No UI representation needed for A2A communication.

### Why not a fully separate panel?

A second slide-out panel would:
1. Complicate the Layout component significantly
2. Create awkward states when both panels are open
3. Require a second mobile bottom-nav button (already tight on space)

A tabbed approach within the existing panel shell is simpler, consistent, and scales if we add more agents later.

### Alternative considered: Inline chat on Nutrition page

I considered embedding a chat widget directly on the Nutrition page (below the meal timeline). Rejected because:
- It duplicates the chat UI code
- It breaks the established "chat is in the side panel" mental model
- It wastes vertical space on the most scroll-heavy page

---

## 9. Mobile-First Design Details

### Touch Targets

All interactive elements meet 44x44px minimum tap targets (Apple HIG / Material Design). The FAB is oversized at 56px. Macro value inputs expand to full-width on focus with `text-lg` font size to prevent iOS zoom.

### Camera Integration

```html
<input
  type="file"
  accept="image/*"
  capture="environment"
  onChange={handleCapture}
  className="hidden"
  ref={fileInputRef}
/>
```

The `capture="environment"` attribute opens the rear camera directly on mobile. The FAB's `onClick` triggers `fileInputRef.current?.click()`. No custom camera UI — native is faster and more reliable.

### Image Optimization

Before upload, the captured image is resized client-side to max 1200px on the longest edge using `<canvas>`. This:
- Reduces upload time on cellular connections
- Reduces GCS storage costs
- Is sufficient resolution for the AI to analyze food

### Offline Resilience

If the upload/analysis fails (poor connectivity), the meal is saved locally (IndexedDB) with the photo blob and retried when connectivity returns. The MacroCard shows an amber `CloudOff` icon and "Pending analysis" text. The user can still manually enter macros while offline.

### Bottom Sheet Pattern for Analysis

On mobile, the analysis result slides up as a bottom sheet (CSS transform, no library needed) rather than inserting inline. This keeps the photo visible behind a semi-transparent backdrop and feels native:

```
┌──────────────────────────────────┐
│                                  │
│     (photo visible behind        │
│      semi-transparent overlay)   │
│                                  │
├──── drag handle ─────────────────┤
│ ✨ Analysis Complete             │
│                                  │
│ ┌────────┬────────┬────────┬────────┐
│ │  487   │  38g   │  42g   │  18g   │
│ │  KCAL  │ PROTEIN│ CARBS  │  FAT   │
│ └────────┴────────┴────────┴────────┘
│                                  │
│ Grilled chicken salad with       │
│ quinoa and mixed greens          │
│                                  │
│         [ Save Meal ]            │
│         [ Edit Macros ]          │
└──────────────────────────────────┘
```

### Gesture Support

- **Swipe left on a MacroCard** → reveals delete action (red `Trash2` icon slide-out, same pattern as iOS mail)
- **Swipe left/right on the date header** → navigate to previous/next day
- **Pull-to-refresh on the timeline** → re-fetches meal data

---

## 10. Design Tradeoffs & Alternatives Considered

### 1. Bottom tab vs. sub-page

**Chosen:** Bottom tab.
**Alternative:** Nutrition as a sub-section of the Dashboard.
**Why:** Nutrition is a top-level concern, not a Dashboard widget. Users will access it multiple times daily (every meal). It needs its own real estate and its own FAB. The existing 5-slot bottom nav (with Coach) has room for one more; on small phones, this is tight but viable with slightly narrower icons.

### 2. FAB vs. inline "Add" button

**Chosen:** Floating action button.
**Alternative:** A button in the page header or an inline card.
**Why:** The FAB is the fastest tap target — it's always visible, always in the same position, and doesn't scroll away. Google's Material Design uses FABs for exactly this pattern (primary creation action). The cycling app doesn't currently have a FAB, so this is additive, not conflicting.

### 3. Bottom sheet vs. new page for analysis results

**Chosen:** Bottom sheet on mobile, inline card on desktop.
**Alternative:** Navigate to a dedicated "Review Meal" page.
**Why:** Navigation creates a context switch. The bottom sheet keeps the user in the timeline context and feels like an overlay, not a destination. If the analysis is wrong, they edit in-place and save. No back-button confusion.

### 4. Macro color scheme

**Chosen:** Reuse existing palette (accent/green/yellow/blue).
**Alternative:** Introduce nutrition-specific colors (standard nutrition label colors: blue protein, green carbs, etc.).
**Why:** Introducing new color tokens would fragment the design system. The existing four accent colors map cleanly to the four macro values and feel native to the app.

### 5. Separate Nutritionist panel vs. tabbed Coach panel

**Chosen:** Tabbed within existing CoachPanel.
**Alternative:** Completely separate panel, or a chat embedded in the Nutrition page.
**Why:** Minimizes code duplication and cognitive overhead. Users already understand the slide-out panel pattern. Adding a tab is a minor extension, not a new paradigm.

### 6. Voice input method

**Chosen:** Push-to-talk button on the capture screen.
**Alternative:** Always-on voice recognition, or a separate voice input step.
**Why:** Always-on is a battery drain and privacy concern. A separate step adds friction. Push-to-talk is explicit, familiar (walkie-talkie pattern), and only activates when needed.

---

## 11. Tailwind Component Patterns Reference

For implementers — map of design tokens to use, matching existing patterns:

| Element | Classes |
|---------|---------|
| Page card | `bg-surface rounded-xl border border-border shadow-sm` |
| Section header | `px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2` |
| Section title | `text-sm font-bold text-text uppercase tracking-wider` |
| Micro label | `text-[10px] font-bold text-text-muted uppercase tracking-widest` |
| Metric large number | `text-3xl font-bold` + color class |
| Input field | `bg-surface-low text-text border border-border rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20` |
| Primary button | `bg-accent text-white rounded-lg text-[10px] font-bold uppercase tracking-widest hover:opacity-90 shadow-lg shadow-accent/20` |
| Ghost button | `text-text-muted hover:text-accent hover:bg-accent/5 rounded-md transition-all` |
| FAB | `fixed w-14 h-14 bg-accent text-white rounded-full shadow-lg shadow-accent/20 flex items-center justify-center` |
| Card hover | `hover:border-accent/30 transition-all` |
| Empty state icon | `text-text-muted mx-auto opacity-10` + large size |
| Empty state text | `text-text-muted font-bold uppercase tracking-widest text-xs` |
| Loading spinner | `animate-spin text-accent opacity-50` (using `RefreshCw` or `Loader2`) |
| Skeleton block | `animate-pulse bg-surface-low rounded h-4 w-full` |

---

## 12. Responsive Breakpoints

| Breakpoint | Behavior |
|------------|----------|
| Mobile (<768px / `md:`) | Single column, bottom nav, FAB at bottom-right, bottom sheet for analysis, swipe gestures active |
| Tablet/Desktop (>=768px) | Two-column grid for meal cards, top nav, inline analysis card, Nutritionist panel slides from right |

The Nutrition page follows the same responsive patterns as the Rides page — single column mobile list with card-based items, expanding to a wider layout on desktop.
