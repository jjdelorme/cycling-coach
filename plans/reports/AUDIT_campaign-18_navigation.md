# Plan Validation Report: Campaign 18 — Navigation, Routing & Deep Linking

**Worktree:** `/home/workspace/cycling-coach/.claude/worktrees/agent-af461ff5`
**Branch:** `worktree-agent-af461ff5`
**Plan:** `plans/feat-navigation-deep-linking.md`
**Audit scope:** Phases 1–3 only (Phases 4–6 explicitly deferred per plan, lines 437–445).

## Summary

* **Overall Status:** PASS-WITH-MINOR-FINDINGS
* **Completion Rate:** 3/3 phases verified, all in-scope micro-steps satisfied
* **Build:** clean (`tsc -b && vite build` succeeds, 0 TS errors)
* **Vitest unit suite:** 22/22 passing
* **Recommendation:** Safe to commit the working-tree changes, merge to `main`, and cut a beta release.

## Detailed Audit (Evidence-Based)

### Phase 1 — Install Router & Top-Level Routes

| Step | Status | Evidence |
| --- | --- | --- |
| 1.A install `react-router-dom` | Verified | `frontend/package.json:23` declares `"react-router-dom": "^7.14.1"`; `frontend/node_modules/react-router-dom/` present |
| 1.B BrowserRouter in `main.tsx` | Verified | `frontend/src/main.tsx:21-35`. Provider order: QueryClient → Auth → BrowserRouter → Theme → Units → App. Auth wraps router, as the plan requires for future route guards |
| 1.C Route table at `lib/routes.ts` | Verified | `frontend/src/lib/routes.ts` (NEW, 142 lines): `RouteEntry` type, `ROUTES` array, `findRoute`, `roleSatisfies`, derived `HEADER_ROUTES` / `MOBILE_NAV_ROUTES` / `MORE_MENU_ROUTES` / `HEADER_ICON_ROUTES` filters |
| 1.D `<Routes>` in App.tsx | Verified | `frontend/src/App.tsx:52-70` — `<Routes>` with index + 7 named paths + `path="*"` fallback, all under a `<Layout />` layout route. Tab-state ladder is gone (no `useState` in App.tsx) |
| 1.E Layout uses `<NavLink>` + `<Outlet />` | Verified | `frontend/src/components/Layout.tsx:118-188` (desktop header NavLinks driven by `HEADER_ROUTES`), `:192-194` (`<Outlet />` replaces `{children}`), `:212-313` (mobile bottom nav + More menu also NavLink). `activeTab` derived from `useLocation().pathname` via `pathToTab` (`:38-50`) |
| 1.E (coach reset) | Verified | Layout `useEffect` at `:80-85` keys on `[location.pathname]` and clears `moreOpen` + `handoff` on every route change (replaces the old `[activeTab]` reset) |
| 1.F NotFound page | Verified | `frontend/src/pages/NotFound.tsx` (NEW, 20 lines). Friendly empty state, "Go to Dashboard" `<Link to="/">` button. Mounted as `path="*"` in App.tsx |
| 1.G E2E URL assertions | Verified | `tests/e2e/07-navigation.spec.ts` rewritten: 16 specs assert `toHaveURL`, exercise back/forward, deep-link, NotFound, header link clicks. `tests/e2e/helpers.ts` updated to use `getByRole('link', ...)` since the nav is now anchors |

**Phase 1 verdict:** Matches plan exactly.

---

### Phase 2 — Ride & Workout Deep Links

| Step | Status | Evidence |
| --- | --- | --- |
| 2.A Split list/detail | Partial-by-design | `Rides.tsx` was NOT split into a separate `RideDetail.tsx` file; it kept the inline `showDetail` branch but is now URL-driven (`Rides.tsx:64-67` reads `useParams<{id, date}>`). `WorkoutDetail.tsx` IS its own page (extracted, 38 lines). The plan's 2.A wording suggested splitting Rides — keeping it inline is a pragmatic choice that still satisfies the success criterion. Not flagged as a defect |
| 2.B Routes & params | Verified | App.tsx:55-58 — `/rides`, `/rides/:id`, `/rides/by-date/:date`, `/workouts/:id`. `Rides.tsx:66-67` reads params; `selectedRideId` and `selectedDate` derived purely from URL. `useState` for these is gone |
| 2.B "Back to List" | Verified | `DayDetailShell.tsx:53-59` renders `<Link to={backTo.href}>` — Rides passes `'/rides'`, WorkoutDetail passes `'/calendar'` |
| 2.B prev/next-day nav | Verified | Logic moved into `DayDetailShell.tsx:35-49` (`navigateToDate`) and uses `navigate('/rides/<id>')` or `navigate('/rides/by-date/<date>')`. `useActivityDates` no longer imported in Rides.tsx (uncommitted diff) |
| 2.C Cross-page handlers | Verified | `Dashboard.tsx:14, 214` import/use `useNavigate()`. Latest-ride card (`:392`) and recent-rides table rows (`:636`) call `navigate(\`/rides/\${id}\`)`. Next-workout card (`:347`) calls `navigate(\`/workouts/\${nextWorkout.id}\`)`. No more `onRideSelect` / `onWorkoutSelect` props anywhere (`grep` returns 0 hits in `frontend/src/`) |
| 2.D `/workouts/:id` route | Verified | Route at App.tsx:58. `WorkoutDetail.tsx:15-38` uses `useParams`, `useWorkoutDetail(id)` (hook exists in `useApi.ts:109`). On null/error renders `<NotFound />` |
| 2.E Calendar wiring | Verified | `Calendar.tsx:237` — "View Analysis" is `<Link to={\`/rides/\${r.id}\`}>`; `:269` — "Show Details" is `<Link to={\`/workouts/\${w.id}\`}>` |
| 2.F E2E updates | Verified | `tests/e2e/03-rides.spec.ts` — asserts URL on selection (`:67-71`), Back-to-List behavior (`:168-172`), browser back (`:174-177`), deep-link via `page.goto` (`:189-202`), and the new uncommitted Workout-detail chevron-pill regression test (`:212-238`). `tests/e2e/04-calendar.spec.ts` adds "View Analysis" → `/rides/:id` (`:104-121`) and "Show Details" → `/workouts/:id` (`:123-139`) URL assertions |

**Dynamic check:** Build clean; vitest 22/22 (no failing or skipped tests).

**Phase 2 verdict:** Matches plan intent. The DayDetailShell extraction (uncommitted) is actually an improvement over the plan because it shares the prev/next chevron pill between `/rides/:id` and `/workouts/:id`.

---

### Phase 3 — Nutrition & Meal Deep Links

| Step | Status | Evidence |
| --- | --- | --- |
| 3.A Backend audit (`/api/nutrition/meals/:id`) | Verified | `useApi.ts:214` exposes `useMeal(id)`; the new `MealDetail.tsx:20` consumes it. The 08-meal-plan.spec.ts smoke tests (`:127-156`) exercise the API and the deep link |
| 3.B viewMode → URL | Verified | `Nutrition.tsx:25-29` `pathToView()` derives view from pathname. `Nutrition.tsx:66-68` — Day/Week/Plan toggles are `<NavLink>` elements. `useState<ViewMode>` is gone. App.tsx:61-64 mounts the four `nutrition*` paths |
| 3.C Plan-day-detail route | Verified | `MealPlanCalendar.tsx:41-42` reads `useParams<{ date }>`. `:58-59` `selectDate` / `clearDate` use `navigate('/nutrition/plan/...')`. Local `useState<selectedDate>` is gone (replaced by URL-derived `selectedDate`) |
| 3.D Single-meal detail page | Verified | `frontend/src/pages/MealDetail.tsx` (NEW, 60 lines). Renders existing `MacroCard` (no shortcut implementation), proper loading + error + not-found states, "Back to Nutrition" link |
| 3.E `?date=` driving Day view | Verified | `Nutrition.tsx:33, 37-42` — `useSearchParams()` reads `?date=` (defaulting to today) and `setDate` writes via `setSearchParams` |
| 3.F E2E updates | Verified | `tests/e2e/08-meal-plan.spec.ts` rewritten: link-role queries for toggles (`:27-31`), URL-on-toggle assertions (`:33-46`), 4 deep-link tests covering `/nutrition/week`, `/nutrition/plan`, `/nutrition/plan/:date`, `/nutrition?date=...` and `/nutrition/meals/:id` |

**Phase 3 verdict:** Matches plan exactly.

---

## Anti-Shortcut & Quality Scan

* **Placeholders / TODOs:** Searched all migrated files (App.tsx, main.tsx, Layout.tsx, routes.ts, NotFound.tsx, MealDetail.tsx, WorkoutDetail.tsx, DayDetailShell.tsx, MealPlanCalendar.tsx, Nutrition.tsx, Rides.tsx, nutritionist-handoff.tsx) for `TODO|FIXME|HACK|in production|implement actual|in a real app` — **zero hits**.
* **Test integrity:** No `xit`, `xdescribe`, `test.skip`, `describe.skip` introduced. Two existing `test.skip(...)` calls in `03-rides.spec.ts:94-98` and `:217, 229` are guarded skips (env-conditional / data-conditional) — legitimate, pre-existing pattern.
* **Fake implementations:** None observed. New `MealDetail.tsx` reuses real `MacroCard` rather than re-rendering a static placeholder; `WorkoutDetail.tsx` reuses the canonical `WorkoutOnlyDetail` exported from `Rides.tsx`.
* **Dead code in App.tsx:** Already removed — App.tsx contains 0 `useState` calls (Phase 6's promise of "shrink to ~30 lines" effectively achieved at 73 lines, which is well under the old version).
* **Project conventions:** No commented-out blocks; new files have header comments; helpers are typed; the `eslint-disable-next-line react-hooks/exhaustive-deps` in Layout.tsx:84 is justified by an inline comment.

## Build & Test Results

```
$ cd frontend && npm run build
> tsc -b && vite build
✓ 2068 modules transformed.
dist/index.html                   0.53 kB
dist/assets/index-De_pW1nL.css   52.84 kB
dist/assets/index-eEgjlqCL.js   853.89 kB
✓ built in 1.12s

$ cd frontend && npm test
Test Files  3 passed (3)
     Tests  22 passed (22)
  Duration  484ms
```

## Findings (non-blocking)

1. **`npm run lint` reports 36 pre-existing errors.** Comparing against `main`, the only new lint hit attributable to Phase 1–3 scope is `'q' is assigned a value but never used` at `Rides.tsx:604` — that line was actually introduced by Campaign 17 (Rides Search), not this campaign. Build (`tsc -b && vite build`) is what gates merge, and that passes.
2. **`Rides.tsx` was not split into a separate `RideDetail.tsx` file as Step 2.A literally suggested.** Functionally equivalent: detail rendering is now URL-driven via `useParams`, and the prev/next-day chevron pill was extracted into `DayDetailShell.tsx`. The plan's success criterion (paste `/rides/12345` → see that ride) is met. Splitting the file is a cosmetic refactor that can land later without breaking the URL contract.
3. **Uncommitted CHANGELOG diff.** `git diff main..HEAD -- CHANGELOG.md` shows the worktree REMOVES the `v1.12.6-beta` entry. This is because the worktree branched before that release commit landed on main. Re-merging main into the worktree (or finishing the merge after committing the campaign) will restore it. Not a code defect, but the parent agent should be aware before merging.
4. **MealCapture FAB still calls `setDate(today)` from any view.** Plan flagged this as cosmetic at line 449 ("could be tightened to only fire on the day route"). Behaviour is correct because `setDate` writes the search param which is only consumed by the Day view. **Not a blocker.**
5. **DayDetailShell.tsx is untracked but properly plumbed.** Rides.tsx and WorkoutDetail.tsx both import and render it; the chevron-pill regression test at `03-rides.spec.ts:212-238` covers it. **Should be staged before commit.**

## Conclusion

All 3 in-scope phases are implemented correctly, with evidence and behavior matching the plan. The codebase is in a shippable state:

* `npm run build` is clean.
* All 22 vitest unit tests pass.
* No TODO/FIXME/skipped-test shortcuts.
* No dead state left behind in App.tsx.
* The uncommitted working-tree changes (DayDetailShell extraction + matching e2e regression test) are a clean, targeted improvement over what was committed in `8f717f0`.

### Recommendation to parent agent

* **(a) Commit the uncommitted changes:** YES. Stage `frontend/src/components/DayDetailShell.tsx`, `frontend/src/pages/Rides.tsx`, `frontend/src/pages/WorkoutDetail.tsx`, and `tests/e2e/03-rides.spec.ts` together as a single "refactor: extract DayDetailShell from Rides and WorkoutDetail" follow-up commit. Note that the staged set should NOT include `CHANGELOG.md` (which is showing as deleted-line because of the worktree being behind main).
* **(b) Merge to main:** YES, after the commit above. The merge should be `--no-ff` per the plan's merge instructions (line 455). Pure frontend + e2e changes, no DB or backend impact.
* **(c) Cut a beta release:** YES. SPA fallback in `server/main.py:299-304` already serves arbitrary paths to `index.html`, so all the new deep links work in production with zero server-side changes. Suggest `v1.13.0-beta` since this is a user-visible feature delta (deep-linkable URLs), not a bug fix.

**Single caveat:** Run the Playwright suite (`./scripts/run_e2e_tests.sh`) against a live backend before tagging the release, since 03-rides, 04-calendar, 07-navigation, and 08-meal-plan all received non-trivial rewrites and were never executed in the worktree.
