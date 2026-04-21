# Feature Implementation Plan: Navigation & Deep-Linking Overhaul

## 🔍 Analysis & Context
*   **Objective:** Replace the current state-based tab switcher with real client-side routing (URL-driven, deep-linkable, back/forward-aware) and add breadcrumb navigation.
*   **Affected Files (high level):**
    *   `frontend/package.json` — add `react-router-dom`
    *   `frontend/src/main.tsx` — wrap app in `BrowserRouter`
    *   `frontend/src/App.tsx` — replace tab state with `<Routes>`
    *   `frontend/src/components/Layout.tsx` — replace `onTabChange` callbacks with `<NavLink>` / `useLocation`
    *   `frontend/src/pages/Rides.tsx` — split list vs. detail views, drive selection from `useParams`
    *   `frontend/src/pages/Calendar.tsx` — drive selected day from URL search param
    *   `frontend/src/pages/Nutrition.tsx` — drive `day | week | plan` view from URL; route to meal detail
    *   `frontend/src/components/MealPlanCalendar.tsx` / `MealPlanDayDetail.tsx` — selection by URL
    *   `frontend/src/components/CoachPanel.tsx` — accept `viewContext` derived from `useLocation` + `useParams` instead of prop drilling
    *   `frontend/src/components/LoginPage.tsx` — redirect-on-login support
    *   `frontend/src/components/Breadcrumbs.tsx` — **NEW**
    *   `frontend/src/lib/routes.ts` — **NEW** centralized route table & breadcrumb metadata
    *   `tests/e2e/*.spec.ts` — update to assert URL changes, replace click-only navigation with `page.goto()` deep-link tests
*   **Key Dependencies:**
    *   `react-router-dom` v7+ (matches React 19 in `frontend/package.json`)
    *   No backend changes required — `server/main.py` already serves `index.html` for any non-`/api`, non-`/assets` path (`spa_fallback` at line 299).
    *   Vite dev server already proxies `/api/*` to the backend, so client-side routes won't collide.
*   **Risks/Edge Cases:**
    *   `react-router-dom` is **not currently installed** — Phase 1 must add it.
    *   Existing E2E suite (`tests/e2e/`) navigates exclusively by clicking nav buttons (`navTo()` in `helpers.ts`); they don't yet inspect URLs. Tests still pass because they don't depend on URLs, but they need extending to validate the new contract.
    *   Ride detail is currently rendered **inside** `Rides.tsx` based on local state (`selectedRideId`/`selectedDate`). Going to a route splits this into a list view + a separate detail view; the cross-page handlers (`handleRideSelect`, `handleWorkoutSelect`) used by Dashboard and Calendar will need to issue `navigate()` calls instead of `setTab + setRideId`.
    *   The `CoachPanel` derives a `viewContext` from `App.tsx` state to inject "currently viewing X" hints into the chat prompt (`buildViewHint` in `CoachPanel.tsx:35-54`). This must be re-derived from the URL after the migration; otherwise, the agent loses awareness of the current page.
    *   Auth gating today is a single early-return in `App.tsx` (lines 55-57). Per-route gating (e.g. `/admin` for admins, `/settings` for read+) must be re-implemented using a route guard wrapper.
    *   Sidebar/coach-panel state (`coachOpen`) and nutritionist context are currently hoisted to `App.tsx` and reset on every `onTabChange`. After routing, this reset logic must hook into route changes (e.g. via `useEffect([location.pathname])`).
    *   Mobile bottom-nav and "More" menu in `Layout.tsx` are tightly coupled to `activeTab`; they need the same treatment as the desktop nav.
    *   The Rides detail "Back to List" button (`Rides.tsx:262-267`) calls local state setters; with routing it must call `navigate(-1)` or `navigate('/rides')`.
    *   `useActivityDates` powers prev/next-day navigation in ride detail (`navigateToDate`, `Rides.tsx:216-240`). With routes, this must become `navigate('/rides/by-date/YYYY-MM-DD')` or `navigate('/rides/:id')`.
    *   Meal detail is currently a sub-state of the Plan tab (`MealPlanDayDetail` swapped in via local `selectedDate` in `MealPlanCalendar.tsx`). Promoting it to a route (`/nutrition/plan/:date`) requires the day-data fetch to either move into the detail component or to be hydrated from `useMealPlan` filtered by date.
    *   There are no individual "meal detail" pages today — meals show in `MealTimeline`. Phase 3 introduces a true `/nutrition/meals/:id` route, which means the planner must verify the API returns a single-meal endpoint (audit task in Phase 3).
    *   `Settings.tsx` has internal sub-tabs (`'athlete' | 'coach' | 'nutritionist' | 'system'`) driven by local state. These could optionally be promoted to URL search params (`/settings?section=coach`) — out of scope for v1 but called out below.

## 📋 Micro-Step Checklist

- [ ] **Phase 0: Investigation & Test Harness**
  - [ ] 0.A: Inventory all current views and confirm SPA fallback works for arbitrary paths in production (`server/main.py:299-304`)
  - [ ] 0.B: Add a baseline E2E test asserting current URL behaviour (today: URL never changes when clicking tabs) — proves the bug
  - [ ] 0.C: Confirm `react-router-dom@latest` is compatible with React 19.2 / TypeScript 5.9
- [ ] **Phase 1: Install Router & Top-Level Routes (no deep links yet)**
  - [ ] 1.A: Install `react-router-dom`
  - [ ] 1.B: Wrap `<App />` in `<BrowserRouter>` in `main.tsx`
  - [ ] 1.C: Create `frontend/src/lib/routes.ts` with the canonical route table
  - [ ] 1.D: Replace `App.tsx` tab switcher with `<Routes>` for the 7 top-level views
  - [ ] 1.E: Replace `Layout.tsx` nav buttons with `<NavLink>`; derive `activeTab` from `useLocation`
  - [ ] 1.F: Add a `<NotFound />` fallback route for unmatched paths
  - [ ] 1.G: Update `tests/e2e/07-navigation.spec.ts` to assert URLs change on nav
- [ ] **Phase 2: Ride & Workout Deep Links**
  - [ ] 2.A: Split `Rides.tsx` into `<RidesList />` and `<RideDetail />` route components
  - [ ] 2.B: Add `/rides/:id` and `/rides/by-date/:date` routes; load via `useParams`
  - [ ] 2.C: Update `Dashboard.tsx` and `Calendar.tsx` "select ride" handlers to `navigate('/rides/:id')` instead of state setters
  - [ ] 2.D: Add `/workouts/:id` route for the planned-workout-only view (currently `WorkoutOnlyDetail` in `Rides.tsx:890`)
  - [ ] 2.E: Update Calendar's workout-select to navigate to `/workouts/:id`
  - [ ] 2.F: Update `tests/e2e/03-rides.spec.ts` and `04-calendar.spec.ts` to assert URL on selection and to test direct deep-link via `page.goto`
- [ ] **Phase 3: Nutrition & Meal Deep Links**
  - [ ] 3.A: Audit `/api/nutrition/meals` — confirm a `GET /api/nutrition/meals/:id` endpoint exists or document a backend follow-up
  - [ ] 3.B: Promote `viewMode` (`day|week|plan`) in `Nutrition.tsx` to URL: `/nutrition`, `/nutrition/week`, `/nutrition/plan`
  - [ ] 3.C: Add `/nutrition/plan/:date` for meal-plan day detail (replacing local `selectedDate` in `MealPlanCalendar.tsx`)
  - [ ] 3.D: Add `/nutrition/meals/:id` for single-meal detail (new view; minimal scaffold if no detail page exists yet)
  - [ ] 3.E: Drive day selection in day-view from `?date=YYYY-MM-DD` search param
  - [ ] 3.F: Update `tests/e2e/08-meal-plan.spec.ts` to use deep links
- [ ] **Phase 4: Calendar, Analysis, Settings, Admin Deep Links**
  - [ ] 4.A: `/calendar?date=YYYY-MM-DD` — drive `selectedDay` and visible month from search params
  - [ ] 4.B: `/analysis` — currently no internal nav; mark complete with a smoke test
  - [ ] 4.C: `/settings` and `/settings/:section` (optional) for internal Settings tabs
  - [ ] 4.D: `/admin` — admin-only, gated; must redirect non-admin users to `/`
  - [ ] 4.E: Add a generic `<RequireRole role="admin|readwrite|read" />` route-guard wrapper
- [ ] **Phase 5: Breadcrumbs**
  - [ ] 5.A: Define breadcrumb metadata per route in `routes.ts` (label, parent)
  - [ ] 5.B: Build `<Breadcrumbs />` component using `useMatches` from React Router
  - [ ] 5.C: Mount `<Breadcrumbs />` in `Layout.tsx` between header and `<main>` (desktop) and as a slim row above the page title (mobile)
  - [ ] 5.D: Resolve dynamic crumbs (e.g. `/rides/:id` → "Rides › 2026-04-18 — Endurance Z2") via lightweight `useRide(id)` lookup with graceful fallback to the raw param
  - [ ] 5.E: Add E2E test asserting breadcrumb appears and links work
- [ ] **Phase 6: Auth, 404, Redirect-on-Login & Cleanup**
  - [ ] 6.A: Wrap protected routes in `<RequireAuth />`; redirect unauthenticated users to `/login`
  - [ ] 6.B: After login, redirect to the originally requested URL (capture via `location.state.from`)
  - [ ] 6.C: Promote `LoginPage` to a real route at `/login`
  - [ ] 6.D: 404 polish — friendly page with "Go to Dashboard" link
  - [ ] 6.E: Remove dead state in `App.tsx` (rideId/rideDate/calendarDate/nutritionistContext lifted to URL)
  - [ ] 6.F: Update `CoachPanel`'s `buildViewHint` to derive context from `useLocation` + `useParams`
  - [ ] 6.G: Final pass on `tests/e2e/` to add at least one direct-deep-link test per detail route

## 📝 Step-by-Step Implementation Details

### Prerequisites
*   Local Postgres running per `AGENTS.md` (Podman `coach-db` on port 5432).
*   `source venv/bin/activate` for backend; `cd frontend && npm install` for frontend.
*   `./scripts/dev.sh` to verify the app loads at each phase boundary.

---

### Phase 0: Investigation & Test Harness

1.  **Step 0.A (Inventory):** Confirm the table of views below by walking the app (no code change). Expected output: this table, copied into the team chat / commit message for the Phase 1 PR.

| # | View | Today's entry point | Today's URL | Resource ID(s) needed for deep link |
|---|------|---------------------|-------------|--------------------------------------|
| 1 | Dashboard | Header tab "Dashboard" | `/` (state only) | none |
| 2 | Rides — list | Header tab "Rides" | `/` | optional `?start=&end=` filter |
| 3 | Rides — detail (recorded ride) | Click row in Rides list **or** click ride from Dashboard "recent rides" **or** click ride from Calendar day | `/` | `:id` (rides.id) |
| 4 | Rides — detail (workout-only on a date) | Click planned workout in Calendar **or** prev/next-day arrows in ride detail | `/` | `:date` (YYYY-MM-DD) |
| 5 | Workout detail (planned, standalone) | Workout-only path inside Rides | `/` | `:id` (workouts.id) |
| 6 | Calendar — month grid | Header tab "Calendar" | `/` | optional `?date=YYYY-MM-DD` |
| 7 | Calendar — day panel | Click a day cell | `/` (local `selectedDay`) | `:date` |
| 8 | Analysis | Header tab "Analysis" | `/` | none |
| 9 | Nutrition — Day view | Header tab "Nutrition" | `/` | optional `?date=YYYY-MM-DD` |
| 10 | Nutrition — Week view | "Week" toggle inside Nutrition | `/` | optional `?date=YYYY-MM-DD` (Monday) |
| 11 | Nutrition — Plan view (calendar) | "Plan" toggle inside Nutrition | `/` | optional `?date=YYYY-MM-DD` (Monday) |
| 12 | Nutrition — Plan day detail | Click a day in `MealPlanCalendar` | `/` (local `selectedDate`) | `:date` |
| 13 | Meal detail (per-meal) | **does not exist as a page today** — meals appear inline in `MealTimeline`/`MealPlanDayDetail` | n/a | `:id` (meals.id) — new |
| 14 | Settings | Gear icon (header) / "More" menu (mobile) | `/` | optional `?section=athlete\|coach\|nutritionist\|system` |
| 15 | Admin (User Management) | Users icon (admin only) / "More" menu | `/` | none |
| 16 | Login / Access Restricted | Conditional render in `App.tsx` based on `user.role` | `/` | none |
| 17 | Coach panel (chat) | Floating side panel toggled by chat icon | `/` | not a page; **stays modal-style** but can be opened via `?coach=open` |

2.  **Step 0.B (Baseline test):** Add `tests/e2e/09-routing-baseline.spec.ts` (intentionally short-lived) that asserts the current bug: clicking nav tabs leaves `page.url()` pointing at `BASE`. This will be deleted/replaced in Phase 1.
    *   *Action:* Run `./scripts/run_e2e_tests.sh 09-routing-baseline` and confirm it passes.

3.  **Step 0.C (Library compat):** Run `npm view react-router-dom peerDependencies` to confirm React 19 support. As of writing (April 2026), `react-router-dom@7.x` declares `react@>=18` peer.
    *   *Verification:* `npm install --dry-run react-router-dom@latest` exits with no peer warnings.

---

### Phase 1: Install Router & Top-Level Routes

*Branch suggestion:* `feat/nav-phase1-router`

1.  **Step 1.A (Install):**
    *   *Target File:* `frontend/package.json`
    *   *Action:* `cd frontend && npm install react-router-dom`
2.  **Step 1.B (Provider):**
    *   *Target File:* `frontend/src/main.tsx`
    *   *Change:* Wrap `<App />` with `<BrowserRouter>`. Order: `QueryClientProvider > AuthProvider > BrowserRouter > ThemeProvider > UnitsProvider > App`. (Auth must wrap router so route guards can read it.)
3.  **Step 1.C (Route table):**
    *   *Target File:* `frontend/src/lib/routes.ts` (NEW)
    *   *Content:* Export a typed const array `ROUTES` listing `{ path, label, icon, parent?, requireRole?, breadcrumbResolver? }` for every entry in the inventory. This is the single source of truth used by `Layout.tsx`, the `<Routes>` block, and `<Breadcrumbs />`.
4.  **Step 1.D (Routes block):**
    *   *Target File:* `frontend/src/App.tsx`
    *   *Change:* Replace the giant `tab === 'X' && <Page />` ladder with:
        ```tsx
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="rides" element={<Rides />} />
            <Route path="calendar" element={<Calendar />} />
            <Route path="analysis" element={<Analysis />} />
            <Route path="nutrition" element={<Nutrition />} />
            <Route path="settings" element={<Settings />} />
            <Route path="admin" element={<Admin />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
        ```
    *   `Layout` becomes a layout route that renders `<Outlet />` where `{children}` used to go.
    *   Drop `useState<TabKey>` and the `onTabChange` callback — let the URL be the truth.
5.  **Step 1.E (Layout adjust):**
    *   *Target File:* `frontend/src/components/Layout.tsx`
    *   *Change:* Replace each tab button with `<NavLink to="/rides" className={({isActive}) => …}>`. Same pattern for the desktop header, the mobile bottom nav, and the "More" dropdown. Replace `{children}` with `<Outlet />` from `react-router-dom`.
    *   Coach panel reset effects: replace `useEffect([activeTab])` with `useEffect([location.pathname])`.
6.  **Step 1.F (404):**
    *   *Target File:* `frontend/src/pages/NotFound.tsx` (NEW)
    *   *Content:* Friendly empty state, "Go to Dashboard" link.
7.  **Step 1.G (Tests):**
    *   *Target File:* `tests/e2e/07-navigation.spec.ts`
    *   *New assertions:*
        ```ts
        await page.locator('header').getByRole('link', { name: 'Rides' }).click()
        await expect(page).toHaveURL(/\/rides$/)
        ```
    *   *Verification:* `./scripts/run_e2e_tests.sh 07-navigation`.

**Phase 1 Success Criteria:** every existing tab still works, but the URL now reflects the active page; back/forward buttons work; deep-link to `/rides` from a fresh tab loads the rides page (not Dashboard).

---

### Phase 2: Ride & Workout Deep Links

*Branch suggestion:* `feat/nav-phase2-rides-deep-link`

1.  **Step 2.A (Split components):**
    *   *Target Files:*
        *   `frontend/src/pages/Rides.tsx` → keep as `RidesList` (list-only)
        *   `frontend/src/pages/RideDetail.tsx` (NEW) → extract the `showDetail` branch (`Rides.tsx:242-573`) including `MetricCard`, `LapsTable`, `WorkoutStepsTable`
        *   `frontend/src/pages/WorkoutDetail.tsx` (NEW) → extract `WorkoutOnlyDetail` (`Rides.tsx:890-962`)
2.  **Step 2.B (Routes & params):**
    *   *Target File:* `frontend/src/App.tsx` (Routes block)
    *   *Add:*
        ```tsx
        <Route path="rides" element={<RidesList />} />
        <Route path="rides/:id" element={<RideDetail />} />
        <Route path="rides/by-date/:date" element={<RideDetail />} />
        <Route path="workouts/:id" element={<WorkoutDetail />} />
        ```
    *   In `RideDetail`, replace `selectedRideId` local state with `const { id, date } = useParams()`.
    *   `navigateToDate` (`Rides.tsx:216`) becomes `navigate('/rides/by-date/' + date)` or `navigate('/rides/' + foundRide.id)`.
    *   "Back to List" button → `<Link to="/rides">`.
3.  **Step 2.C (Cross-page handlers):**
    *   *Target Files:* `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Calendar.tsx`
    *   *Change:* Replace the `onRideSelect={handleRideSelect}` prop pattern with internal `useNavigate()` calls. Drop the `onRideSelect` props entirely (and from `App.tsx`).
4.  **Step 2.D (Workout route):** As above, `/workouts/:id` reuses `useWorkout(id)` (verify hook exists in `useApi.ts` — if not, add one or fetch via `/api/plan/workouts/:id`).
5.  **Step 2.E (Calendar wiring):**
    *   *Target File:* `frontend/src/pages/Calendar.tsx`
    *   *Change:* "View Analysis" button → `<Link to={'/rides/' + r.id}>`; "Show Details" workout button → `<Link to={'/workouts/' + w.id}>`.
6.  **Step 2.F (Tests):**
    *   *Target Files:* `tests/e2e/03-rides.spec.ts`, `tests/e2e/04-calendar.spec.ts`
    *   *New cases:*
        *   "Direct deep-link to `/rides/:id` loads the detail page without going through the list."
        *   "Clicking a row in the rides list updates the URL to `/rides/:id`."
        *   "Browser back from ride detail returns to `/rides` and preserves the filter."

**Phase 2 Success Criteria:** A user can paste `/rides/12345` into the address bar, share it, and see the same ride detail page. Browser back works. Calendar's "View Analysis" button changes the URL.

---

### Phase 3: Nutrition & Meal Deep Links

*Branch suggestion:* `feat/nav-phase3-nutrition-deep-link`

1.  **Step 3.A (Backend audit):**
    *   *Action:* `grep -n "meals/" server/routers/nutrition.py` and confirm a single-meal endpoint exists. If not, file a follow-up issue (`feat-nutrition-single-meal-endpoint`) but do **not** block this phase — render meal detail by filtering the day's meals client-side as a fallback.
2.  **Step 3.B (View mode → URL):**
    *   *Target File:* `frontend/src/pages/Nutrition.tsx`
    *   *Routes added:* `/nutrition` (day), `/nutrition/week`, `/nutrition/plan`. Drop `useState<'day'|'week'|'plan'>`.
    *   `<button onClick={() => setViewMode('plan')}>` becomes `<NavLink to="/nutrition/plan">`.
3.  **Step 3.C (Plan day detail route):**
    *   *Target Files:* `frontend/src/components/MealPlanCalendar.tsx`, `MealPlanDayDetail.tsx`
    *   *Change:* Promote `selectedDate` to `/nutrition/plan/:date`. Calendar grid renders `<Link to={'/nutrition/plan/' + date}>` per day cell. `MealPlanDayDetail` reads `useParams()` and finds its day from `useMealPlan`. Back button → `navigate('/nutrition/plan')`.
4.  **Step 3.D (Meal detail route, scaffold):**
    *   *Target File:* `frontend/src/pages/MealDetail.tsx` (NEW — minimal: title, macros, raw description; iterate later)
    *   *Route:* `/nutrition/meals/:id`
    *   Hook into `MealTimeline` so each meal card links here.
5.  **Step 3.E (Day-view date param):** `/nutrition?date=2026-04-18` drives `useDailyNutrition(date)` and `useMeals({start_date, end_date})`. Use `useSearchParams`.
6.  **Step 3.F (Tests):** `tests/e2e/08-meal-plan.spec.ts` — replace toggle clicks with `page.goto('/nutrition/plan')` for one of the cases; add a deep-link case for `/nutrition/plan/2026-04-18`.

**Phase 3 Success Criteria:** Sharing a URL like `/nutrition/plan/2026-04-18` opens that day directly. Toggling Day/Week/Plan changes the URL.

---

### Phase 4: Calendar, Analysis, Settings, Admin

*Branch suggestion:* `feat/nav-phase4-remaining-routes`

1.  **Step 4.A (Calendar `?date=`):**
    *   *Target File:* `frontend/src/pages/Calendar.tsx`
    *   Use `useSearchParams` to read/write `?date=`. Selecting a day cell does `setSearchParams({ date })`. Month nav (`prevMonth`, `nextMonth`) updates the date param to the 1st of the new month so the URL shows what the user is viewing.
2.  **Step 4.B (Analysis):** No interactive sub-state today; just confirm `/analysis` direct nav works (smoke test).
3.  **Step 4.C (Settings sub-routes):** Optional. If shipped, `/settings/athlete`, `/settings/coach`, `/settings/nutritionist`, `/settings/system`. The internal `Tab` state in `Settings.tsx:37` becomes `useParams<'section'>`. Recommended deferring to a follow-up to keep this phase small.
4.  **Step 4.D (Admin gating):** `/admin` route renders only if `user.role === 'admin'`; otherwise `<Navigate to="/" replace />`.
5.  **Step 4.E (Route guard):**
    *   *Target File:* `frontend/src/components/RequireRole.tsx` (NEW)
    *   *Signature:* `function RequireRole({ role, children }: { role: 'admin' | 'readwrite' | 'read'; children: ReactNode })`
    *   Wrap `<Route path="admin" element={<RequireRole role="admin"><Admin /></RequireRole>} />`.

**Phase 4 Success Criteria:** All routes are deep-linkable. Non-admin users hitting `/admin` are bounced to `/`.

---

### Phase 5: Breadcrumbs

*Branch suggestion:* `feat/nav-phase5-breadcrumbs`

1.  **Step 5.A (Metadata):** Extend `routes.ts` entries with `crumb: (params) => string | Promise<string>`. Examples:
    *   `{ path: '/rides', crumb: () => 'Rides' }`
    *   `{ path: '/rides/:id', parent: '/rides', crumb: ({ id }) => useRide(id).data?.title ?? `#${id}` }`
2.  **Step 5.B (Component):**
    *   *Target File:* `frontend/src/components/Breadcrumbs.tsx` (NEW)
    *   Implementation uses React Router's `useMatches` to walk the matched route chain, then renders a `<nav aria-label="breadcrumb">` with `<Link>` for every ancestor and plain text for the current leaf.
3.  **Step 5.C (Mount):**
    *   *Target File:* `frontend/src/components/Layout.tsx`
    *   *Insert:* `<Breadcrumbs />` between the desktop `<header>` (line 75-147) and `<main>` (line 151). On mobile, render as a slim row above page content (single-line, ellipsis on overflow).
4.  **Step 5.D (Dynamic resolution):** For `/rides/:id` use a small wrapper that runs `useRide(id)` and renders the title once loaded; show the raw `:id` while loading. Same pattern for `/workouts/:id`, `/nutrition/plan/:date`, `/nutrition/meals/:id`.
5.  **Step 5.E (Tests):** New `tests/e2e/10-breadcrumbs.spec.ts` — assert breadcrumb shows on each detail page; clicking the parent crumb navigates back; trail length matches expectation.

**Example breadcrumb trails:**
*   `/` → `Dashboard`
*   `/rides` → `Dashboard › Rides`
*   `/rides/12345` → `Dashboard › Rides › 2026-04-18 — Endurance Z2`
*   `/nutrition/plan/2026-04-18` → `Dashboard › Nutrition › Plan › Sat, Apr 18`

**Phase 5 Success Criteria:** Every page shows a breadcrumb that reflects the URL hierarchy and is clickable.

---

### Phase 6: Auth, 404, Redirect-on-Login & Cleanup

*Branch suggestion:* `feat/nav-phase6-auth-and-cleanup`

1.  **Step 6.A (RequireAuth):** Wrap the layout route in `<RequireAuth />`; unauthenticated users redirect to `/login` with `state={{ from: location }}`.
2.  **Step 6.B (Redirect-on-login):** `LoginPage` reads `location.state.from` and `navigate(from ?? '/', { replace: true })` after a successful token exchange. This means a user who pastes `/rides/12345` while logged out lands on that ride after signing in.
3.  **Step 6.C (Login route):** Convert `LoginPage.tsx` from an early-return component into a proper `/login` route. Authenticated users hitting `/login` redirect to `/`.
4.  **Step 6.D (404 polish):** Update `NotFound.tsx` from Phase 1 with branded styling and a "Go to Dashboard" link.
5.  **Step 6.E (Dead state removal):** Delete the `rideId`, `rideDate`, `calendarDate`, `nutritionistContext`, `nutritionistSessionId`, and `tab` `useState`s from `App.tsx`. The file should shrink to ~30 lines.
6.  **Step 6.F (CoachPanel context):**
    *   *Target File:* `frontend/src/components/CoachPanel.tsx`
    *   *Change:* Replace the `viewContext` prop with a `useViewContext()` hook backed by `useLocation()` and `useParams()`. Update `buildViewHint` to read those.
7.  **Step 6.G (Final test sweep):** Add at least one direct-deep-link test (`page.goto`) per detail route. Run `./scripts/run_e2e_tests.sh` end-to-end.

**Phase 6 Success Criteria:** `App.tsx` has no UI state. `/login` is a real route. Pasting a deep link while logged out redirects to login then back. 404s render the friendly page.

---

### 🧪 Global Testing Strategy
*   **Unit Tests:** Pure helpers in `routes.ts` (path-builder, breadcrumb resolver) tested via Vitest.
*   **Integration Tests:** Not directly affected — this is a pure frontend change. Existing `tests/integration/` suite must continue to pass after each phase (run `./scripts/run_integration_tests.sh`).
*   **E2E Tests:** Each phase ships with updated `tests/e2e/` assertions. Specifically:
    *   `01-api-health.spec.ts` — no changes expected.
    *   `02-dashboard.spec.ts` — assert `/` is the dashboard URL.
    *   `03-rides.spec.ts` — Phase 2 updates (URL changes; deep link).
    *   `04-calendar.spec.ts` — Phase 4 updates (search-param URL).
    *   `05-analysis.spec.ts` — Phase 1 update (assert `/analysis`).
    *   `06-settings.spec.ts` — Phase 4 update (assert `/settings`).
    *   `07-navigation.spec.ts` — Phase 1 rewrite (button → link, URL assertions).
    *   `08-meal-plan.spec.ts` — Phase 3 updates.
    *   `09-routing-baseline.spec.ts` — Phase 0 only; deleted in Phase 1.
    *   `10-breadcrumbs.spec.ts` — Phase 5.

---

## 🌐 Proposed URL Scheme

| Path | View | Notes |
|------|------|-------|
| `/` | Dashboard | Index route |
| `/login` | Login page | Phase 6 |
| `/rides` | Rides list | Supports `?start_date&end_date` filters |
| `/rides/:id` | Ride detail (recorded) | Phase 2 |
| `/rides/by-date/:date` | Ride/workout detail by date | Used for prev/next-day arrows |
| `/workouts/:id` | Standalone workout detail | Phase 2 |
| `/calendar` | Calendar month grid | Supports `?date=YYYY-MM-DD` |
| `/analysis` | Analysis dashboard | |
| `/nutrition` | Nutrition — Day | Supports `?date=YYYY-MM-DD` |
| `/nutrition/week` | Nutrition — Week | |
| `/nutrition/plan` | Nutrition — Plan calendar | |
| `/nutrition/plan/:date` | Plan day detail | Phase 3 |
| `/nutrition/meals/:id` | Meal detail | Phase 3 (new view) |
| `/settings` | Settings (default section) | |
| `/settings/:section` | Settings sub-tab (optional, deferrable) | Phase 4 |
| `/admin` | User management | Admin only |
| `/*` | Not Found | Friendly fallback |

## 🍞 Breadcrumb Design

**Source of truth:** Per-route metadata in `frontend/src/lib/routes.ts`.
**Why:** A flat metadata table is simpler than walking React Router's nested `<Outlet>` tree and lets us render dynamic crumbs (ride title, meal name) by attaching a `crumb` resolver function per route.

**Component contract:**
```ts
interface CrumbEntry { label: string; to?: string }  // omit `to` for the leaf
function useBreadcrumbs(): CrumbEntry[]
```

**Examples:**
1. `/` → `[{ label: 'Dashboard' }]`  (root suppresses crumbs visually but data is there for screen readers)
2. `/rides` → `[{ label: 'Dashboard', to: '/' }, { label: 'Rides' }]`
3. `/rides/12345` (loaded ride titled "Endurance Z2 · 2026-04-18") → `[{ label: 'Dashboard', to: '/' }, { label: 'Rides', to: '/rides' }, { label: 'Endurance Z2 · 2026-04-18' }]`
4. `/nutrition/plan/2026-04-18` → `[{ label: 'Dashboard', to: '/' }, { label: 'Nutrition', to: '/nutrition' }, { label: 'Plan', to: '/nutrition/plan' }, { label: 'Sat, Apr 18' }]`

**Rendering rules:**
*   Hide on `/` to reduce noise.
*   Truncate to last 3 crumbs on mobile, with a `…` collapsing the middle.
*   Use the accent color for the current leaf (no link).
*   ARIA: `<nav aria-label="breadcrumb"><ol>…</ol></nav>` per WAI-ARIA APG.

## ⚠️ Risks & Open Questions

1.  **Coach Panel as a route vs. modal.** Today the coach side panel coexists with any page. We keep it as a side panel (not a route) but optionally support `?coach=open` so a user can share a "page + coach open" URL. Decision: defer until Phase 6, then open coach via search param.
2.  **Ride detail vs. modal.** Confirmed it's a full-page swap today, not a modal — Phase 2 cleanly promotes it to a route.
3.  **Single-meal endpoint missing.** Phase 3 must verify `GET /api/nutrition/meals/:id` exists; if not, the meal-detail page either filters from the day's meal list or we add a backend route in a sibling plan.
4.  **Auth race on first paint.** `useAuth` returns `isLoading: true` briefly on mount. `<RequireAuth />` must render a spinner during this window, **not** redirect — otherwise refreshing a deep link bounces to `/login` for a flash.
5.  **Existing E2E selector fragility.** `helpers.ts` uses `getByRole('button', { name: 'Rides' })`. After Phase 1, those are `<a>`/`<NavLink>` elements with role `link`. The helper must update or use a role-agnostic selector.
6.  **Vite dev proxy.** Already configured to send `/api/*` to backend. Client routes will resolve through Vite's history-fallback middleware automatically. Confirm no custom `historyApiFallback: false` setting (we don't have one).
7.  **Browser scroll restoration.** React Router v7 doesn't restore scroll on back navigation by default. Add a `<ScrollRestoration />` component in Phase 1 to avoid surprising scroll positions when returning to long lists (Rides, Calendar).
8.  **Query-string vs. path for filters.** Decision: use search params for **filters** (`?date`, `?start_date`) and path for **resources** (`/rides/:id`). This keeps URLs shareable but the route tree small.
9.  **Document title.** Currently static. Plan to add `useDocumentTitle(crumbLabel)` in Phase 5 alongside breadcrumbs so the browser tab shows the deepest crumb.
10. **Analytics/telemetry.** None today. If/when added, page-view tracking now has a real `location.pathname` to send.

## 🚫 Out of Scope

*   **Server-side rendering / SEO.** This app is fully behind Google sign-in and serves authenticated users only — there is no SEO benefit to SSR, and the SPA fallback in `server/main.py:299-304` is sufficient.
*   **Hash-based routing.** Browser URL routing (HTML5 History API) only; the SPA fallback supports it.
*   **i18n / localized URLs.** App is English-only.
*   **Permalink redirect of legacy in-app links.** No external system links into the app; nothing to redirect from.
*   **Migrating internal `Settings` sub-tabs to URLs (Phase 4.C).** Marked optional; recommended deferred to a follow-up.
*   **Tracking unsaved-changes prompts on navigation** (e.g. dirty Athlete Notes textarea). Optional v2 polish.
*   **Per-route code splitting / lazy loading.** Not required by user request; revisit if bundle size grows.

## 🌿 Branch Naming Convention

*   `feat/nav-phase1-router` — install React Router and top-level routes
*   `feat/nav-phase2-rides-deep-link` — `/rides/:id`, `/workouts/:id`
*   `feat/nav-phase3-nutrition-deep-link` — meal/plan deep links
*   `feat/nav-phase4-remaining-routes` — calendar params, admin guard
*   `feat/nav-phase5-breadcrumbs` — breadcrumb component
*   `feat/nav-phase6-auth-and-cleanup` — RequireAuth, /login, dead-state removal

Each branch ships independently as its own PR, and each leaves the app in a working state.

## 🎯 Success Criteria

*   The address bar reflects the user's current view at all times (Dashboard = `/`, every other view has its own path).
*   Browser back/forward navigates between visited views correctly.
*   Pasting `/rides/12345`, `/workouts/42`, `/nutrition/plan/2026-04-18`, or `/nutrition/meals/789` into a fresh tab loads the corresponding resource (after auth).
*   Breadcrumbs appear on every non-root view, link to ancestors, and reflect dynamic resource names where applicable.
*   `/admin` is unreachable (redirects to `/`) for non-admins.
*   404s render the friendly NotFound page, not a blank screen.
*   All existing E2E tests pass; new deep-link tests pass.
*   `App.tsx` no longer holds page/tab state — URL is the single source of truth.

---

## Status / Execution Notes

*Last updated: 2026-04-21 — Phases 1–3 complete in worktree, Phases 4–6 explicitly deferred.*

**Worktree:** `/home/workspace/cycling-coach/.claude/worktrees/agent-af461ff5`
**Branch:** `worktree-agent-af461ff5`
**Status:** Phases 1–3 ready for review and merge. Together they form a complete, shippable deep-linking story (top-level routes + ride/workout deep links + nutrition deep links). Phases 4–6 are independent enhancements queued for follow-up work.

### Commits (newest first)

| SHA | Phase | Summary |
| --- | --- | --- |
| `8f717f0` | Phase 3 | Nutrition deep links: `/nutrition/week`, `/nutrition/plan`, `/nutrition/plan/:date`, `/nutrition/meals/:id`. New `MealDetail.tsx` page; `MealPlanCalendar` selected day driven by `useParams`; Day/Week/Plan toggles became `<NavLink>`. |
| `4663b0a` | Phase 2 | Ride and workout deep links (`/rides/:id`, `/workouts/:id`). |
| `9632bd2` | Phase 1 | Install `react-router-dom`; replace tab state with top-level `<Routes>`; mobile + desktop nav driven by URL. |

### Verification

- `npm run build`: clean (tsc + vite, 0 errors).
- Vitest unit suite: 22/22 pass.
- E2E test file `tests/e2e/08-meal-plan.spec.ts` updated to use `link` role queries and asserts URL changes; **Playwright not run in worktree** (requires a live backend at `:8080`).
- Backend `pytest` skipped in this worktree (no `venv`); no backend changes were made so no regressions expected.

### Deferred (queued as separate follow-ups)

| Phase | Scope | Notes |
| --- | --- | --- |
| Phase 4 | Route guards (`RequireRole`), Calendar `?date=` query param, Settings/Admin per-route gating | Scaffolding partly in place: `roleSatisfies` helper and `ROUTES` table already exist in `frontend/src/lib/routes.ts`; `AdminRoute` does an inline role check today. |
| Phase 5 | Breadcrumb component on every non-root view | Not started. |
| Phase 6 | `/login` route, `RequireAuth` wrapper, refactor `LoginPage` early-return, lift coach-panel context out of `Layout` | Not started. |

Each deferred phase is independently shippable per the original branch convention (`feat/nav-phase4-*`, etc.), and can be picked up by a fresh team or follow-up worktree.

### Minor Open Item

- The `MealCapture` FAB still calls `setDate(today)` after meal save. Works correctly because the Day view is now URL-bound, but could be tightened to only fire on the day route. Cosmetic — does not block merge.

### Merge Instructions

Pure frontend + e2e test changes. No DB migrations, no env-var changes, no backend changes. SPA fallback at `server/main.py:299-304` already serves arbitrary paths to `index.html`, so all new deep links work in prod without server changes.

```bash
git checkout main
git merge --no-ff worktree-agent-af461ff5
```
