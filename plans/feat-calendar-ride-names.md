# Feature Implementation Plan: Calendar Ride Names

## Problem & Goal
Today, the Calendar month view (`frontend/src/pages/Calendar.tsx`) shows each ride inside a day cell as a tiny `SportIcon` followed by a rounded TSS number (e.g. `[bike] 78`). The ride's actual name (`r.title`, e.g. "Sweet Spot 2x20") is invisible until the user clicks the cell to open the day detail panel. On wider screens there is plenty of horizontal room inside each cell to surface the name inline alongside the TSS, giving users at-a-glance context about what each session was. The goal is to render `TSS  "Ride Name"` inside the cell when the viewport is wide enough (>= Tailwind `md` breakpoint, matching every other responsive pattern in this app), while leaving the existing TSS-only display untouched on narrow/mobile screens.

## Affected Files
- `frontend/src/pages/Calendar.tsx` — only file that needs editing.
  - Ride-cell render block: **lines 187–198** (the `dayRides.map((r) => ...)` JSX).
  - Specifically the inner `<div>` at **lines 188–192** is the element that needs to gain the optional name span.
- `frontend/src/types/api.ts` — **read-only check**, no edits. `RideSummary.title?: string` already exists at line 33, and the `/api/rides` endpoint (`server/routers/rides.py` line 25–54, `SELECT *`) already returns it. The day-detail panel at `Calendar.tsx` line 234 already uses `r.title`. **No backend changes required.**
- `tests/e2e/04-calendar.spec.ts` — optional new E2E case (see Test Plan).

## Implementation Approach (Decisions)

1. **Data source** — `r.title` is already populated on the `RideSummary` objects the calendar receives via `useRides(...)` (line 100). No API change, no migration, no new query.
2. **Determining "visible space"** — Use a Tailwind responsive utility (`hidden md:inline`) on a new sibling span. This matches the codebase's existing pattern (see `Layout.tsx:75`, `MealCapture.tsx:277`, `Settings.tsx:416`, `Rides.tsx:583`). Container queries are not used anywhere in this codebase, JS measurement is overkill, and we already have `truncate` on the parent row to handle remaining overflow. The breakpoint choice (`md` = 768px) is correct because (a) the calendar grid switches its `min-h-[100px] md:min-h-[130px]` at the same breakpoint and (b) below 768px each of the 7 columns is too narrow (~50px) to show meaningful text.
3. **Truncation safety** — The parent `<div>` at line 189 already has `truncate` and `leading-none`. The new title span will inherit the parent's `flex` row, so any overflow is clipped cleanly. We will additionally set `title={r.title}` on the cell as a native browser tooltip so the full name is recoverable on hover.
4. **Format** — Render as `<TSS> <span class="hidden md:inline">"Title"</span>`. The quotation marks come from the spec ("`TSS: "Ride Name"`"); a colon between TSS and the title is too noisy in 9px font, so use a single space and let the quoted name visually separate itself. (Tweak deferred to implementation review if it looks wrong.)

## Implementation Steps
Each step below is small enough to be a single commit.

### Step 1 — Add inline ride title to calendar cells (md+ only)
- **File:** `frontend/src/pages/Calendar.tsx`
- **Lines:** 188–192 (inside the `dayRides.map` block).
- **Change:** Inside the existing `<div className="flex items-center gap-1 text-[9px] font-bold text-green uppercase tracking-tighter truncate leading-none">`, after the `{Math.round(r.tss ?? 0)}` text node, append:
  ```tsx
  {r.title && (
    <span className="hidden md:inline normal-case font-semibold text-text-muted truncate">
      "{r.title}"
    </span>
  )}
  ```
- **Why these classes:**
  - `hidden md:inline` — only visible on screens >= 768px (the codebase convention).
  - `normal-case` — overrides the parent's `uppercase` so the name reads naturally, not SHOUTED.
  - `font-semibold text-text-muted` — visually subordinate to the bright-green TSS number so TSS remains the primary metric.
  - `truncate` — defense-in-depth against overflow inside the already-`truncate` parent.
- **Tooltip:** also add `title={r.title}` to the parent `<div>` at line 189 so hover reveals the full name on every breakpoint (including mobile, where the inline text is hidden).

### Step 2 — Verify the change manually
- `./scripts/dev.sh` and load the Calendar.
- Pick a month where rides exist with non-trivial titles (e.g. last completed training month).
- Confirm: at >= 1024px and 768px, ride cells show `[icon] 78 "Sweet Spot 2x20"`.
- Confirm: at < 768px (resize the window), cells still show only `[icon] 78`.
- Confirm: hovering any ride cell shows the full title in a native tooltip.

### Step 3 — Add a small E2E assertion (optional, recommended)
- **File:** `tests/e2e/04-calendar.spec.ts`
- **Where:** Add a new `test(...)` near line 122 (the existing "planned workout cells" test).
- **What to assert:**
  ```ts
  test('ride cells expose full title via title attribute', async ({ page }) => {
    const rideRow = page
      .locator('.grid-cols-7.gap-px > div')
      .filter({ has: page.locator('[class*="text-green"]') })
      .first()
      .locator('div[title]')
      .first()
    if (await rideRow.count() > 0) {
      const t = await rideRow.getAttribute('title')
      expect(t && t.length).toBeTruthy()
    }
  })
  ```
- We assert the `title` attribute (works at any viewport) rather than the visible inline span, because Playwright's default desktop viewport (1280×720) is well above `md` so visibility checks would also pass — but the attribute check is breakpoint-independent and stable.

## Test Plan

### Manual checks (required)
1. **Desktop (>= 1024px):** Open Calendar; rides show `[icon] TSS "Title"` inline; the title is visually muted vs the TSS number; long titles do not overflow into adjacent cells.
2. **Tablet (768–1023px):** Same display as desktop (md breakpoint hit).
3. **Mobile (< 768px):** Display is unchanged from current behavior — only `[icon] TSS`.
4. **Hover on any ride cell (any breakpoint):** native browser tooltip reveals the full ride title.
5. **Day with multiple rides:** Each ride row independently renders its own title; alignment stays clean.
6. **Day with no rides:** No regression; cell is empty as before.
7. **Ride with no title (edge case — older imports, manual rides):** No quotes / empty span rendered (the `r.title && ...` guard).
8. **Planned workouts row:** Unchanged. The change is scoped to the `dayRides.map` block only, not the `dayWOs.map` block at lines 193–197.
9. **Day detail panel:** Unchanged — already showed `r.title` (line 234).

### Automated
- Run `pytest` to confirm no Python tests regressed (none should — this is frontend-only).
- Run `cd frontend && npm run build` to confirm TypeScript type-checks pass (Vite/tsc).
- Run the new Playwright case via `./scripts/run_e2e_tests.sh -- 04-calendar` (if the suite is set up for that flag form) or `npx playwright test --config tests/e2e/playwright.config.ts 04-calendar`.

## Out of Scope
This feature is **NOT**:
- A redesign of the calendar cell layout, font sizes, or color scheme.
- A change to how planned-workout rows render (`dayWOs.map`, lines 193–197) — workouts still show only the first word of the workout name as today. (We can mirror this change to workouts in a follow-up if desired.)
- A change to the day-detail panel below the grid — it already shows full ride names.
- A change to the API surface, schema, ingestion, or DB. `r.title` is already returned by `/api/rides` because of `SELECT *` in `server/routers/rides.py:36`.
- A new responsive system (no container queries, no `useMediaQuery`, no JS-based width measurement). Tailwind's `md:` breakpoint is the established convention in this codebase.
- A change to the cell click/select behavior, or to navigation.
- Truncation/ellipsis customization beyond what the parent `truncate` class already provides.
- Backfilling missing ride titles from FIT/Intervals data — out of scope; rides without `title` simply render as today.

## Branch Name Suggestion
`feat/calendar-ride-names`
