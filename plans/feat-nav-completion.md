# Feature Implementation Plan: Campaign 18 Completion (Phases 4–6)

## 🔍 Analysis & Context

*   **Objective:** Finish Campaign 18 by landing the route guards, breadcrumbs, `/login` route, and dead-state cleanup that were deferred from the v1.13.0-beta ship.
*   **What's already built (don't rebuild):**
    *   Backend RBAC complete: `require_read`, `require_write`, `require_admin` FastAPI dependencies in `server/auth.py:130-148`. All `/api/...` routes are gated. **No backend work is required.**
    *   Roles enum and storage: `users.role` column with `none|read|readwrite|admin`, default `none` (`migrations/0001_baseline.sql:238`).
    *   `roleSatisfies(actual, required)` helper already exists at `frontend/src/lib/routes.ts:135` — used today only in `Layout.tsx:63, 289`. We will lean on this rather than introduce a new helper.
    *   `requireRole?: Role` field already declared on `RouteEntry` (`routes.ts:37`) and populated for `/settings` and `/admin` (`routes.ts:99, 108`). **The route table is already the source of truth — guards just need to consume it.**
    *   `LoginPage.tsx` UI already handles both unauthenticated and `role: 'none'` ("Access Restricted") states.
    *   Admin / Settings nav icons already gated in `Layout.tsx:117, 130, 229, 241` and the More-menu filter at `Layout.tsx:289`.
    *   `AdminRoute` inline check exists at `App.tsx:27-31` — to be replaced by `RequireRole`.
    *   `App.tsx:46-48` early-return for unauthenticated / `role: none` users — to be replaced by `RequireAuth` + `/login` route.
*   **Affected files (high level):**
    *   `frontend/src/components/RequireAuth.tsx` — **NEW**
    *   `frontend/src/components/RequireRole.tsx` — **NEW**
    *   `frontend/src/components/Breadcrumbs.tsx` — **NEW**
    *   `frontend/src/App.tsx` — wire `RequireAuth` around the layout route, `RequireRole` around `/admin`; promote `/login` to a real route; strip the early-return.
    *   `frontend/src/components/LoginPage.tsx` — read `useLocation().state?.from`; redirect on successful auth via `useNavigate`. Keep both render branches (unauth + access-restricted).
    *   `frontend/src/components/Layout.tsx` — mount `<Breadcrumbs />` between header and `<Outlet />` (desktop) / above page content (mobile).
    *   `frontend/src/lib/routes.ts` — extend `RouteEntry` with optional `crumb?: (params: Record<string, string | undefined>) => string` and `parent` chain (already present). Populate `crumb` for parameterized routes.
    *   `frontend/src/pages/Calendar.tsx` — read/write `?date=YYYY-MM-DD` via `useSearchParams`; default to today only when the URL has no `date`.
    *   `frontend/src/pages/Settings.tsx` — replace inline `user?.role === 'admin'` and `=== 'read'` with `roleSatisfies` calls.
    *   `tests/e2e/04-calendar.spec.ts` — add a deep-link case for `?date=`.
    *   `tests/e2e/07-navigation.spec.ts` — add cases for `/login`, `RequireAuth` redirect, and `/admin` 404 for non-admin (in dev mode the dev user is admin, so this is verified via mock or skipped with a comment).
    *   `tests/e2e/11-breadcrumbs.spec.ts` — **NEW** — assert breadcrumbs render on detail pages and parent links navigate.
*   **Key dependencies:**
    *   `react-router-dom@^7.14.1` (already installed). All needed primitives (`useMatches`, `useSearchParams`, `useNavigate`, `useLocation`, `Navigate`) ship with it.
*   **Risks / edge cases:**
    *   **Auth race on first paint.** `useAuth().isLoading` is briefly `true`. `RequireAuth` must render the existing "Loading..." spinner during that window, **not** redirect to `/login`, otherwise refreshing a deep link bounces to login for a flash.
    *   **Dev mode (no `VITE_GOOGLE_CLIENT_ID`).** `auth.tsx:95` hardcodes `role: 'admin'`. The E2E suite runs in this mode, so any test that asserts a `/admin` 403/redirect for non-admin can't run end-to-end without mocking. Use a unit/component test for the `RequireRole` redirect branch instead.
    *   **`role: 'none'` users hitting deep links.** They should land on the LoginPage's "Access Restricted" branch with the deep link preserved in `location.state.from`, so a "Refresh Status" → admin-promotion flow lands them where they were going.
    *   **Calendar deep-link semantics.** When `?date=2026-04-01` is present, the calendar must (a) show the month containing that date, and (b) select that day in the detail panel. Currently `currentDate` and `selectedDay` are independent local `useState`s — both must seed from the URL param when present.
    *   **Breadcrumb dynamic resolution timing.** For `/rides/:id` the title comes from `useRide(id)`. Show the raw `:id` until the query resolves; never block render on the title fetch.
    *   **`useMatches` returns objects with `pathname` + `params`.** Walk them in order; the last is the leaf. Don't render a `<Link>` for the leaf (it's the current page).
    *   **Don't introduce a new `roleSatisfies` helper.** Use the existing one in `routes.ts`. If the API needs to widen (e.g. accept `RouteEntry` directly), extend it in place rather than fork.
    *   **`Settings.tsx`'s `isReadOnly` check.** It is asking "does the user have *only* read?" not "does the user satisfy read?". Equality stays — don't replace it with `roleSatisfies`.
    *   **`Layout.tsx`'s More-menu filter** currently filters routes by `r.requireRole && roleSatisfies(...)` — that hides routes with no `requireRole`. After this campaign every route in the More menu has a `requireRole` (Settings + Admin), so leave the predicate alone unless adding non-gated More-menu entries.

## 📋 Micro-Step Checklist

- [x] **Phase 4A: `roleSatisfies` consolidation**
  - [x] 4A.1: Skipped intentionally — the early-return is removed entirely in 6A.2, so the interim refactor would have been throw-away churn.
  - [x] 4A.2: `Settings.tsx` `isAdmin` now uses `roleSatisfies(user?.role, 'admin')`; `isReadOnly` left as strict equality.
  - [x] 4A.3: `Layout.tsx`'s `isAdmin` now uses `roleSatisfies(user?.role, 'admin')`.
- [x] **Phase 4B: `RequireRole` component**
  - [x] 4B.1: Added `frontend/src/components/RequireRole.tsx` and `frontend/src/components/LoadingScreen.tsx`.
  - [x] 4B.2: Deleted `AdminRoute`. `/admin` is wrapped in `<RequireRole role="admin">…</RequireRole>` in `App.tsx`.
  - [x] 4B.3: `/settings` route wrapped in `<RequireRole role="read">…</RequireRole>`.
- [x] **Phase 4C: Calendar `?date=` URL param**
  - [x] 4C.1: `Calendar.tsx` imports `useSearchParams`.
  - [x] 4C.2: `currentDate` and `selectedDay` seed from `?date=` when valid, otherwise fall back to today.
  - [x] 4C.3: `handleSetSelectedDay` writes/clears `?date=` with `replace: true`.
  - [x] 4C.4: `prevMonth` / `nextMonth` write the 1st of the new month into `?date=`.
  - [x] 4C.5: Playwright deep-link assertion added to `tests/e2e/04-calendar.spec.ts`.
- [x] **Phase 6A: `/login` route + `RequireAuth`**
  - [x] 6A.1: Added `frontend/src/components/RequireAuth.tsx` (loading → spinner; unauthenticated/role=none → `<Navigate to="/login" state={{from}} replace />`; otherwise `<Outlet />`).
  - [x] 6A.2: `/login` is now a top-level route. The Layout subtree is wrapped in `<Route element={<RequireAuth />}>`. Old early-return removed from `App.tsx`.
  - [x] 6A.3: `LoginPage.tsx` redirects on the first render where `isAuthenticated && user?.role !== 'none'`, honouring `location.state.from.pathname`.
  - [x] 6A.4: Same effect handles authenticated users hitting `/login`.
- [x] **Phase 6B: Dead-state removal**
  - [x] 6B.1: `AdminRoute` and the `useAuth`-driven early-return removed. `App.tsx` is now ~55 lines (the floor is set by the route table itself, not by ceremony).
  - [x] 6B.2: `tsc -b` is clean.
- [x] **Phase 5: Breadcrumbs**
  - [x] 5A: `RouteEntry` extended with optional `crumb` and `dynamicCrumb`. Static crumbs populated for every route; dynamic flag set on `/rides/:id`, `/workouts/:id`, `/nutrition/meals/:id`. Parameterised routes (`/rides/:id`, `/rides/by-date/:date`, `/workouts/:id`, `/nutrition/week`, `/nutrition/plan`, `/nutrition/plan/:date`, `/nutrition/meals/:id`) added so the breadcrumb chain can resolve them.
  - [x] 5B: `Breadcrumbs.tsx` uses `useLocation` + `matchPath` (React Router v7's JSX `<Routes>` does not feed `useMatches`, hence the more direct lookup) and walks the `parent` chain. WAI-ARIA `<nav aria-label="breadcrumb"><ol>` markup; leaf is plain text with `aria-current="page"`; root is hidden.
  - [x] 5C: Dynamic crumbs resolved via `useRide` / `useWorkoutDetail` / `useMeal`; falls back to the static `crumb()` placeholder while pending.
  - [x] 5D: Mounted in `Layout.tsx` (desktop margin-bottom row above `<Outlet />`, compact mobile variant just above the same).
  - [x] 5E: `tests/e2e/11-breadcrumbs.spec.ts` covers the four cases.

## ✅ Status

Phases 4–6 implemented. `npm run build` passes (0 TS errors). `vitest` passes (32 tests, 5 files). Worktree left dirty for the auditor and the user.

## 📝 Step-by-Step Implementation Details

### Phase 4A: `roleSatisfies` consolidation

*Why first:* Reduces churn — the `RequireRole` component built next can rely on a single role-comparison function used everywhere.

1. **Settings.tsx:84:** Change `const isAdmin = user?.role === 'admin'` to `const isAdmin = roleSatisfies(user?.role, 'admin')`. Leave `isReadOnly` (line 85) as `=== 'read'` — that's intentional strict equality. Add `import { roleSatisfies } from '../lib/routes'`.
2. **Layout.tsx:62:** Change `const isAdmin = user?.role === 'admin'` to `const isAdmin = roleSatisfies(user?.role, 'admin')`. (Line 63 already uses `roleSatisfies`.)
3. **App.tsx:46:** No-op for now — about to be deleted in 6A.2. Skip.

### Phase 4B: `RequireRole` component

```tsx
// frontend/src/components/RequireRole.tsx
import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../lib/auth'
import { roleSatisfies, type Role } from '../lib/routes'
import LoadingScreen from './LoadingScreen'

export default function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <LoadingScreen />
  if (!roleSatisfies(user?.role, role)) return <Navigate to="/" replace />
  return <>{children}</>
}
```

Extract the loading-screen markup from `App.tsx:36-42` into `frontend/src/components/LoadingScreen.tsx` and reuse from both `RequireRole` and `RequireAuth`.

### Phase 4C: Calendar URL sync

```tsx
// In Calendar.tsx
import { useSearchParams } from 'react-router-dom'

const [searchParams, setSearchParams] = useSearchParams()
const dateParam = searchParams.get('date')
const validDate = dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) ? dateParam : null

const [currentDate, setCurrentDate] = useState(() => {
  if (validDate) {
    const d = new Date(validDate + 'T00:00:00')
    return { year: d.getFullYear(), month: d.getMonth() }
  }
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() }
})

const [selectedDay, setSelectedDay] = useState<string | null>(() => validDate ?? toDateStr(new Date()))

const handleSetSelectedDay = (date: string | null) => {
  setSelectedDay(date)
  if (date) setSearchParams({ date }, { replace: true })
  else setSearchParams({}, { replace: true })
}
```

Month-nav handlers should also write `?date=YYYY-MM-01` for the visible month.

### Phase 6A: `/login` route + `RequireAuth`

`App.tsx` after this phase should look like:

```tsx
import { Routes, Route } from 'react-router-dom'
import RequireAuth from './components/RequireAuth'
import Layout from './components/Layout'
import LoginPage from './components/LoginPage'
import RequireRole from './components/RequireRole'
// ... page imports

export default function App() {
  return (
    <NutritionistHandoffProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="rides" element={<Rides />} />
            {/* ... */}
            <Route path="settings" element={<RequireRole role="read"><Settings /></RequireRole>} />
            <Route path="admin" element={<RequireRole role="admin"><Admin /></RequireRole>} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Route>
      </Routes>
    </NutritionistHandoffProvider>
  )
}
```

`RequireAuth` renders `<Outlet />` (not `children`) since it's used as a layout route.

`LoginPage.tsx` adds:

```tsx
const navigate = useNavigate()
const location = useLocation()

useEffect(() => {
  if (isAuthenticated && user?.role && user.role !== 'none') {
    const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname
    navigate(from ?? '/', { replace: true })
  }
}, [isAuthenticated, user?.role, navigate, location.state])
```

### Phase 5: Breadcrumbs

`routes.ts` extension:

```ts
export interface RouteEntry {
  // ... existing fields
  /** Static crumb resolver. Receives matched params. Returns the visible label. */
  crumb?: (params: Record<string, string | undefined>) => string
  /** True if the crumb requires async data (ride title, etc.). The component
   *  will render the param verbatim until the lookup resolves. */
  dynamicCrumb?: boolean
}
```

For `/rides/:id` set `crumb: ({ id }) => '#' + id, dynamicCrumb: true`. The `<Breadcrumbs />` component then uses `useRide(Number(id))` to look up the title and overrides the static crumb when data arrives.

Mount in `Layout.tsx` after the desktop `<header>`:

```tsx
<div className="hidden md:block px-6 pt-4 max-w-7xl mx-auto w-full">
  <Breadcrumbs />
</div>
<main className="...">
  <div className="md:hidden px-4 pt-3">
    <Breadcrumbs compact />
  </div>
  <Outlet />
</main>
```

### 🧪 Testing

- **Unit:** Add `frontend/src/lib/__tests__/roleSatisfies.test.ts` if not present (the function is in `routes.ts`; ensure coverage). Verify: `none → false`, `read → satisfies read but not write`, `admin → satisfies all`, `undefined → false`.
- **E2E:** New `tests/e2e/11-breadcrumbs.spec.ts`. Update `04-calendar` for `?date=`. Add `/login` smoke case to `07-navigation`. Skip the role-redirect E2E (dev-mode is admin) but cover the redirect logic in a Vitest component test for `RequireRole`.

## ⚠️ Risks & Open Questions

1. **`LoginPage`'s `useEffect` redirect timing.** In dev mode the user becomes admin instantly on first render. The effect will fire on the same render and redirect to `/` — but if the user had no `from` in state, this is correct behavior. Confirm there's no flash by writing the effect carefully.
2. **`/admin` E2E coverage** can't assert the redirect branch in dev mode (no `none` role). Capture this in a Vitest test that mocks `useAuth` to return `{ user: { role: 'read' }, ... }`.
3. **Breadcrumb on `/nutrition/plan/:date` for invalid date strings.** The route accepts any path segment. Render the raw param verbatim — don't try to parse and fall back to `Invalid date`.
4. **Browser history pollution from `Calendar` `?date=` writes.** Use `replace: true` so back/forward isn't littered with one entry per day clicked.

## 🚫 Out of Scope

- **`Settings/:section` sub-routes** (Phase 4.C in the original plan, marked optional). Skip.
- **`?coach=open` for the Coach panel.** Skip.
- **`useDocumentTitle` from breadcrumb leaf.** Nice-to-have; defer.
- **Per-route code splitting / lazy loading.** Out of scope.
- **Backend changes.** None needed.

## 🎯 Success Criteria

- `App.tsx` is a thin Routes container — no `useState`, no role-check ladders, no early-return.
- Pasting `/admin` while logged out → bounced to `/login` → after login → land on `/admin`.
- Pasting `/admin` while logged in as `read` user → redirected to `/`.
- Pasting `/calendar?date=2026-03-15` → calendar opens to March 2026 with the 15th selected.
- Breadcrumbs render on every non-root view, link to ancestors, and reflect dynamic resource names (ride title, etc.) once loaded.
- All existing E2E tests pass; new deep-link / breadcrumb tests pass.
- `npm run build` clean; vitest 22+ pass; pytest 390+ pass; Playwright 100% pass.

## 📦 Deliverables

1. Implementation per the checklist above.
2. Updated `plans/feat-navigation-deep-linking.md` Status section noting Phases 4–6 complete.
3. No commits — leave the worktree dirty for the auditor and the user to review.
