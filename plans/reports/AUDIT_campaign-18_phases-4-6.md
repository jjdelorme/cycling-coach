# Plan Validation Report: Campaign 18 — Phases 4–6 (`feat-nav-completion`)

## Summary

* **Overall Status:** **PASS** (with one minor observation; nothing pre-merge blocking)
* **Completion Rate:** 6/6 phases verified
* **Build:** `npm run build` clean (`tsc -b && vite build`, 0 errors)
* **Unit tests:** `npm test -- --run` — **5 files, 32 tests, 32 passed**
* **Branch / cwd audited:** `worktree-agent-af461ff5` at `/home/workspace/cycling-coach/.claude/worktrees/agent-af461ff5`
* **Working tree:** dirty (8 modified, 8 untracked) — matches the plan's "leave the worktree dirty" deliverable.

## Phase-by-phase Audit

### Phase 4A — `roleSatisfies` consolidation — VERIFIED
* **4A.1 (skipped):** Documented in checklist; the early-return is removed entirely in 6A.2 so a stop-gap `roleSatisfies` swap would be throw-away. Sound.
* **4A.2:** `frontend/src/pages/Settings.tsx:85` — `const isAdmin = roleSatisfies(user?.role, 'admin')`. `isReadOnly` (line 86) intentionally left as `=== 'read'` per plan callout (it asks "is the user *exactly* read-only?", not "satisfies read"). Correct.
* **4A.3:** `frontend/src/components/Layout.tsx:63` — `const isAdmin = roleSatisfies(user?.role, 'admin')`. Confirmed.

### Phase 4B — `RequireRole` + `LoadingScreen` — VERIFIED
* `frontend/src/components/LoadingScreen.tsx` (7 lines) — extracted spinner markup matching the original at the old `App.tsx` lines 36–42.
* `frontend/src/components/RequireRole.tsx` (17 lines) — exact shape: `isLoading → <LoadingScreen />`, `!roleSatisfies → <Navigate to="/" replace />`, else `<>{children}</>`. Imports `Role` type from `routes.ts`. Order of checks is correct (loading first, prevents redirect flash).
* `App.tsx:47–48` — `/settings` and `/admin` routes wrapped: `<RequireRole role="read">` and `<RequireRole role="admin">`.
* Old `AdminRoute` deleted (grep across `frontend/src/` returned 0 hits).

### Phase 4C — Calendar `?date=` URL sync — VERIFIED
* `frontend/src/pages/Calendar.tsx:75–95`:
  * Imports `useSearchParams` (line 2).
  * `validDate` regex-validates `YYYY-MM-DD` before consuming it (line 77).
  * `currentDate` lazy-init seeds from `validDate` if present, else today (lines 79–86).
  * `selectedDay` lazy-init seeds from `validDate` ?? today (lines 87–89).
  * `handleSetSelectedDay` writes `{date}` or `{}` with `replace: true` (lines 91–95) — exactly per plan callout #4 (avoid history pollution).
* `shiftMonth` (lines 135–147) writes the 1st of the new month into `?date=`, clears `selectedDay`, also `replace: true`. Both `prevMonth`/`nextMonth` delegate.
* `tests/e2e/04-calendar.spec.ts:153–162` deep-link assertion present. Looks fine.

### Phase 6A — `/login` route + `RequireAuth` — VERIFIED
* `RequireAuth.tsx` (14 lines) — exact shape from the plan: `isLoading → <LoadingScreen />`, then `!isAuthenticated || !user || user.role === 'none'` → `<Navigate to="/login" state={{from: location}} replace />`, else `<Outlet />`. The `useLocation()` is captured *before* the loading check, so `state.from` always carries the deep link. Auth-race risk addressed.
* `App.tsx:32` — `<Route path="/login" element={<LoginPage />} />` is a top-level sibling, **outside** `<RequireAuth />`, so deep-linking `/login` while unauthenticated does not trigger an infinite redirect.
* `App.tsx:33` — `<Route element={<RequireAuth />}>` wraps the layout subtree.
* `LoginPage.tsx:14–19` — `useEffect` fires when `isAuthenticated && user.role !== 'none'`. Reads `location.state.from.pathname` defensively (`?.from?.pathname`), navigates with `replace: true`. No infinite loop possible because the effect only runs once auth is good, then this component unmounts.
* The existing "Access Restricted" branch (role === 'none') is preserved and rendered before the unauthenticated branch — correct precedence.

### Phase 6B — Dead-state removal — VERIFIED
* `frontend/src/App.tsx`: 55 lines (matches engineer's "~55, not ~25" note). `grep useState/useEffect` returns 0 hits. `useAuth` import removed. No leftover `AdminRoute` function. No commented-out code. The remaining ceremony is just `NutritionistHandoffProvider` + the route table — that *is* the floor.
* `tsc -b` exits 0.

### Phase 5 — Breadcrumbs — VERIFIED (with 1 minor note)
* `routes.ts` (lines 47–57): `crumb` and `dynamicCrumb` fields added with proper docstrings explaining the *why* (placeholder-then-replace pattern).
* All routes have a `crumb` resolver. New parameterized routes added: `/rides/:id`, `/rides/by-date/:date`, `/workouts/:id`, `/nutrition/week`, `/nutrition/plan`, `/nutrition/plan/:date`, `/nutrition/meals/:id`. Parent chain consistent (`/workouts/:id` parents to `/calendar`, which is where the user arrived from — sound choice).
* `Breadcrumbs.tsx`:
  * Uses `useLocation` + `matchPath` walking `ROUTES` in order. Matches the documented React Router v7 limitation — `useMatches()` is empty under JSX `<Routes>`.
  * Walks the `parent` chain via `findRoute()` correctly; clears params for ancestors (only the leaf has its own params).
  * **Hooks rule respected:** `useDynamicCrumb` always invokes `useRide`/`useWorkoutDetail`/`useMeal`. Each hook is gated by `enabled: id !== null` inside `useApi.ts`, so only one network call ever fires. No wasted requests.
  * Hidden on `/` (root short-circuit at line 86) and when chain length ≤ 1.
  * ARIA: `<nav aria-label="breadcrumb"><ol>` markup; leaf is `<span aria-current="page">`, ancestors are `<Link>`. Correct.
  * Dynamic-crumb fallback: shows `crumb()` placeholder (e.g. `#42`) until `useRide` resolves, then overrides with the title. Never blocks render.
  * `compact` mobile variant uses smaller font, smaller chevron, truncates the leaf — well-considered.
* `Layout.tsx:194–199` — both desktop (`hidden md:block mb-4`) and mobile (`md:hidden mb-3`) `<Breadcrumbs />` mounted *inside* `<main>` above `<Outlet />`. Slight deviation from the plan's snippet (which placed the desktop crumb *outside* `<main>`), but behaviorally equivalent and arguably tidier. **Note only, not a blocker.**
* `tests/e2e/11-breadcrumbs.spec.ts` covers: hidden on `/`, two-level on `/rides`, parent-link navigation, three-level on `/rides/:id` (skipped if no rides exist).

## Anti-Shortcut & Quality Scan

* **Placeholders / TODOs / FIXME / HACK:** None found in any new or modified file.
* **`console.log` / debug statements:** None.
* **Test integrity:** No tests skipped, gutted, or commented out. The `RequireRole` SSR test is documented (the inline comment correctly explains why "SECRET hidden" *is* the proof of redirect under SSR + MemoryRouter).
* **Dependencies:** `frontend/package.json` unchanged — no new deps added. Confirms the brief.
* **Comments:** All new comments explain *why* (auth-race risk, hooks-rule reason for unconditional hook calls, hierarchy of role checks). No "// adds RequireAuth for Campaign 18" noise.
* **Backend:** Untouched.

## Engineer-Deviation Assessment

1. **`useMatches` → `useLocation` + `matchPath`** — **Sound.** React Router v7's `useMatches()` only returns hydrated route metadata when the routes are defined via `createBrowserRouter` / `RouterProvider`. This app uses the JSX `<Routes>` pattern, so `useMatches()` would return `[]` for nested children. The `matchRouteEntry` walk produces correct trails for parameterized routes (verified for `/rides/:id`, `/workouts/:id`, `/nutrition/meals/:id`).
2. **SSR `react-dom/server` test for `RequireRole`** — **Sound.** `frontend/package.json` has zero `@testing-library/*` packages. Adding one would have violated "no new deps". The SSR approach has a known limitation (MemoryRouter doesn't follow `<Navigate>`, so the redirect target is empty), but the engineer correctly leverages that: asserting "SECRET is absent" *is* proof the children weren't rendered. Five tests cover loading, two flavours of redirect (insufficient role, no user), positive grant, and the hierarchy. Coverage is meaningful.
3. **App.tsx ~55 lines, not ~25** — **Sound.** I counted: 55 lines. The non-route ceremony is `NutritionistHandoffProvider` + the two `*Route` shim functions (`NutritionRoute`, `MealDetailRoute`) needed because `Nutrition` and `MealDetail` take a callback prop that depends on a context only available inside the provider. Could be inlined further, but doing so would muddy the route table. The estimate of ~25 in the original plan didn't account for these legitimate adapters.

## Findings (non-blocking)

* **Minor:** Plan's Phase 5 snippet placed the desktop `<Breadcrumbs />` *outside* `<main>` (margin-bottom row on the page chrome); the implementation places both the desktop and mobile crumb *inside* `<main>` above `<Outlet />`. Behaviorally equivalent — visually identical to the user — and arguably more consistent (both variants live in the same scrollable region). Not a regression.
* **Cosmetic:** `Layout.tsx` still keeps the legacy `pathToTab` / `TabKey` plumbing. This is intentional (called out in the in-file comment line 26) and out of scope for Phases 4–6 — flagged here only so it's not forgotten when planning the eventual Layout cleanup pass.

## Conclusion

**Verdict: PASS — go for commit, full E2E run, and beta release tagging.**

* Plan is fully implemented; every checklist item is backed by code I read.
* Build clean, all 32 vitest tests pass.
* No shortcuts, no placeholders, no commented-out code, no new deps, backend untouched.
* The three engineer-flagged deviations are well-reasoned and documented.
* Anti-`/login`-loop, anti-auth-race, and anti-history-pollution risks called out in the plan are all handled in code.

### Recommendation to parent agent
1. **Commit** the work as-is (the plan's "leave dirty" instruction is satisfied; user asked for review first).
2. **Run the full Playwright suite** before tagging. Confirm `04-calendar` (deep link), `07-navigation` (`/login`), and `11-breadcrumbs` all green; spot-check Phase 1–3 routes (`/rides/:id`, `/workouts/:id`, `/nutrition/plan/:date`, `/nutrition/meals/:id`) still render.
3. **Cut next beta release** (e.g. `v1.13.1-beta`) once Playwright is green.
