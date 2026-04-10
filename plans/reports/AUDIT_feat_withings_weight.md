# Plan Validation Report: feat_withings_weight

## 📊 Summary
*   **Overall Status:** FAIL
*   **Completion Rate:** 26/30 Steps verified — 4 failures / partial issues

---

## 🕵️ Detailed Audit (Evidence-Based)

### Step 1.A: Add `body_measurements` table DDL to `_SCHEMA`
*   **Status:** ✅ Verified
*   **Evidence:** `server/database.py` lines 235–246 — `body_measurements` table with all required columns (`id`, `date`, `source`, `weight_kg`, `fat_percent`, `created_at`, `UNIQUE(date, source)`), plus both indexes.
*   **Dynamic Check:** Static verification only (no DB runtime available).
*   **Notes:** Matches plan exactly.

### Step 1.B: Add Withings token keys to `SETTINGS_DEFAULTS`
*   **Status:** ✅ Verified
*   **Evidence:** `server/database.py` lines 410–414 — all 5 keys present: `withings_access_token`, `withings_refresh_token`, `withings_token_expiry`, `withings_user_id`, `withings_oauth_state`.
*   **Dynamic Check:** N/A.
*   **Notes:** Matches plan exactly.

### Step 1.C: Add Withings migration to `init_db()`
*   **Status:** ✅ Verified
*   **Evidence:** `server/database.py` lines 548–569 — `withings_migrations` list with CREATE TABLE IF NOT EXISTS and both indexes, iterated with try/except and rollback on failure.
*   **Dynamic Check:** N/A.
*   **Notes:** Matches plan exactly.

### Step 1.D: Add Withings env vars to `server/config.py`
*   **Status:** ✅ Verified
*   **Evidence:** `server/config.py` lines 26–29 — `WITHINGS_CLIENT_ID`, `WITHINGS_CLIENT_SECRET`, `WITHINGS_REDIRECT_URI` all present with correct defaults.
*   **Dynamic Check:** N/A.
*   **Notes:** Matches plan exactly.

### Step 2.A/2.B: `is_configured` / `is_connected` — tests and implementation
*   **Status:** ✅ Verified
*   **Evidence:** `tests/unit/test_withings.py` lines 10–30; `server/services/withings.py` lines 20–25.
*   **Dynamic Check:** `test_is_configured_false_when_no_env`, `test_is_configured_true_when_env_set`, `test_is_connected_false_when_no_token`, `test_is_connected_true_when_token_present` — all PASSED.
*   **Notes:** None.

### Step 2.C/2.D: `get_auth_url` — tests and implementation
*   **Status:** ⚠️ Partial
*   **Evidence:** `server/services/withings.py` line 28 — `def get_auth_url(redirect_uri: str) -> str` (takes `redirect_uri` as a parameter). Plan specified `def get_auth_url() -> str` (no argument, reads `WITHINGS_REDIRECT_URI` from module-level config). The engineer chose to pass `redirect_uri` explicitly from the router (`server/routers/withings.py` line 26: `svc.get_auth_url(WITHINGS_REDIRECT_URI)`).
*   **Dynamic Check:** `test_get_auth_url_contains_required_params` PASSED — but the test passes `"http://localhost:8000/api/withings/callback"` as an argument, matching the actual signature. The test does NOT verify `set_setting` was called to store the CSRF state (plan Step 2.C specified this assertion).
*   **Notes:** Signature deviation from plan is deliberate and functionally acceptable. Missing test coverage: the unit test does not assert that `set_setting("withings_oauth_state", ...)` was called — only that URL params are present.

### Step 2.E/2.F: `exchange_code` — tests and implementation
*   **Status:** ⚠️ Partial
*   **Evidence:** `server/services/withings.py` lines 41–64. Signature is `exchange_code(code, state, redirect_uri)` — plan specified `exchange_code(code, state)` with `WITHINGS_REDIRECT_URI` read internally. Engineer made `redirect_uri` an explicit param (consistent with `get_auth_url`). Tests at lines 104–135 cover both success and bad-state cases.
*   **Dynamic Check:** `test_exchange_code_stores_tokens` PASSED; `test_exchange_code_rejects_bad_state` PASSED.
*   **Notes:** The `exchange_code` implementation at line 53–55 reads `body = resp.json()` then checks `body.get("status") != 0` — but does NOT check `resp.status_code != 200` before parsing JSON. If the HTTP call fails with a non-JSON response (network timeout, 5xx), it will raise an unhandled exception. Plan's implementation included HTTP status check. Minor robustness gap.

### Step 2.G/2.H: `_get_valid_access_token` / `_refresh_tokens` — tests and implementation
*   **Status:** ❌ Failed
*   **Evidence:**
    1.  **`_refresh_tokens()` uses wrong Withings API action parameter.** `server/services/withings.py` line 70: `"action": "requesttoken"`. The Withings API spec (plan line 23) requires `action=refreshaccesstoken` for token refresh. Using `requesttoken` for a refresh request will result in a Withings API error at runtime — token refresh will never succeed. This is a functional bug that breaks all long-lived connections (tokens expire in ~3 hours).
    2.  **`_refresh_tokens()` signature deviates from plan.** Plan: `_refresh_tokens(refresh_token: str) -> str | None`. Implementation: `_refresh_tokens() -> str` (no parameter; fetches token internally; raises RuntimeError instead of returning None on failure). This is a design choice but the return type difference (`str | None` vs always raises on failure) means callers behave differently.
    3.  **`_get_valid_access_token()` does not check for empty token.** Plan: check `if not access_token: return None` before expiry check. Implementation line 93: `if time.time() >= expiry - 300:` always fires when expiry=0 (empty token_expiry setting), triggering `_refresh_tokens()` on every call even when no token exists. This is a logic error for the disconnected state.
*   **Dynamic Check:** `test_get_valid_access_token_returns_valid_token` PASSED; `test_get_valid_access_token_refreshes_expired_token` PASSED. Tests mock `httpx.post` so the wrong action param is invisible in tests.
*   **Notes:** The `action=requesttoken` bug will cause silent API failures in production for any session lasting more than 3 hours.

### Step 2.I/2.J: `fetch_weight_measurements` — tests and implementation
*   **Status:** ⚠️ Partial
*   **Evidence:** `server/services/withings.py` line 102: `def fetch_weight_measurements(start_date: str, end_date: str) -> list[dict]`. Plan specified `def fetch_weight_measurements(days: int = 90) -> list[dict]`. Engineer redesigned the signature to take explicit date strings — a functional deviation from the plan.
*   **Dynamic Check:** `test_fetch_weight_measurements_decodes_correctly` PASSED; `test_fetch_weight_measurements_skips_non_weight_types` PASSED. Tests cover the actual (string-based) signature.
*   **Notes:**
    - `datetime.utcfromtimestamp()` at line 118 is deprecated (Python 3.12+) — shows as a DeprecationWarning in test output. Should use `datetime.fromtimestamp(ts, tz=timezone.utc)`.
    - The implementation does NOT raise `RuntimeError` when not connected (unlike plan); instead it always calls `_get_valid_access_token()` which will attempt a refresh. No guard for disconnected state.
    - The plan's test for "raises when not connected" (`test_fetch_weight_measurements_raises_when_not_connected`) was not implemented.

### Step 2.K/2.L: `store_measurements` — tests and implementation
*   **Status:** ✅ Verified
*   **Evidence:** `server/services/withings.py` lines 129–139; `tests/unit/test_withings.py` lines 178–191.
*   **Dynamic Check:** `test_store_measurements_upserts_correctly` PASSED.
*   **Notes:** Implementation is clean and correct. Upsert SQL matches plan.

### Step 2.M/2.N: `sync_weight` / `get_status` / `disconnect` — tests and implementation
*   **Status:** ⚠️ Partial
*   **Evidence:**
    - `sync_weight` (`server/services/withings.py` lines 142–150): returns `{"status": "success", "synced": count, "start_date": ..., "end_date": ...}`. Plan specified `{"status": "success", "measurements_stored": count, "days_fetched": days}`. The return keys differ: `synced` vs `measurements_stored`. This propagates to the frontend.
    - `get_status` (lines 153–168): returns `{connected, configured, last_measurement_date?, latest_weight_kg?}`. Plan specified `{configured, connected, user_id?, token_valid?}`. Fields differ entirely.
    - `disconnect` (lines 171–175): matches plan exactly.
*   **Dynamic Check:** `test_sync_weight_fails_when_not_connected` PASSED; `test_get_status_returns_correct_shape` PASSED (but note: the test does not mock `get_db`, which is called when connected=True — the DB call fails silently due to `except Exception: pass` at line 166–167, which is why the test passes without a DB mock).
*   **Notes:** The `get_status` unit test's passing is misleading — it only asserts `configured` and `connected` keys, but the DB query branch is exercised with an uncaught exception swallowed by `pass`. This is a test coverage gap, not a test failure.

### Step 3.A: Integration tests for GET /api/withings/status
*   **Status:** ❌ Failed
*   **Evidence:** `tests/integration/test_withings_integration.py` does NOT exist. Directory listing of `tests/integration/` confirms it is absent. The plan's Phase 3.A, 3.E, 4.A all require this file.
*   **Dynamic Check:** Cannot be run — file missing.
*   **Notes:** This means NO integration tests exist for: Withings status endpoint, sync endpoint, `body_measurements` table migration verification, upsert behavior, or PMC weight priority.

### Step 3.B/3.C/3.D/3.F/3.G: Router endpoints — implementation
*   **Status:** ✅ Verified
*   **Evidence:** `server/routers/withings.py` — all 5 required endpoints present:
    - `GET /status` (line 13) — `require_read`
    - `GET /auth-url` (line 18) — `require_write`
    - `GET /callback` (line 30) — no auth (correct per plan)
    - `POST /sync` (line 55) — `require_write`
    - `DELETE /disconnect` (line 79) — `require_write`
*   **Dynamic Check:** Unit tests pass. Integration tests unavailable (file missing).
*   **Notes:** The `/callback` endpoint uses `<meta http-equiv="refresh">` HTML redirect instead of the JavaScript `window.location` approach specified in the plan — both achieve the same browser redirect and the meta-refresh approach is simpler and more robust. The callback does NOT return `HTMLResponse` with `status_code=200` explicitly for the missing-code case — it raises `HTTPException(400)` instead of redirecting to `/settings?withings=error`. This is a minor deviation (plan says redirect on all error cases).

### Step 3.E: Integration tests for POST /api/withings/sync
*   **Status:** ❌ Failed
*   **Evidence:** `tests/integration/test_withings_integration.py` does not exist. See Step 3.A.
*   **Dynamic Check:** N/A.

### Step 3.H: Register withings router in `server/main.py`
*   **Status:** ✅ Verified
*   **Evidence:** `server/main.py` line 29 — `from server.routers import ... withings as withings_router`; line 218 — `app.include_router(withings_router.router)`.
*   **Dynamic Check:** Unit tests import and use the app successfully — router registration confirmed by 88/88 passing unit tests.

### Step 4.A: Integration test for PMC weight priority
*   **Status:** ❌ Failed
*   **Evidence:** No `tests/integration/test_withings_integration.py` file. PMC weight priority integration test is absent.
*   **Dynamic Check:** N/A.

### Step 4.B: Update `compute_daily_pmc()` with Withings priority
*   **Status:** ✅ Verified
*   **Evidence:** `server/ingest.py` lines 395–399 — prefetch from `body_measurements WHERE source='withings'` into dict `withings_weights`. Line 458: `weight = withings_weights.get(ds)` as first priority in the weight cascade. Implementation uses an inline dict lookup instead of the plan's `_lookup_withings_weight()` helper function — this is a cleaner approach achieving identical semantics.
*   **Dynamic Check:** Static verification only.
*   **Notes:** The engineer implemented an exact-match dict lookup (correct per plan's intent) rather than bisect-style range lookup.

### Step 5.A: `WithingsStatus` interface in `frontend/src/types/api.ts`
*   **Status:** ⚠️ Partial
*   **Evidence:** `frontend/src/types/api.ts` lines 284–289. Interface exists but has DIFFERENT fields than the plan specified.
    - **Plan specified:** `configured`, `connected`, `user_id?`, `token_valid?`
    - **Implemented:** `configured`, `connected`, `last_measurement_date?`, `latest_weight_kg?`
*   **Dynamic Check:** Frontend TypeScript types match the actual API response shape — so the frontend works correctly at runtime.
*   **Notes:** The engineer chose more useful fields (`last_measurement_date`, `latest_weight_kg`) over the plan's `user_id`/`token_valid`. This is a functional improvement but a plan deviation.

### Step 5.B: API helpers in `frontend/src/lib/api.ts`
*   **Status:** ⚠️ Partial
*   **Evidence:** `frontend/src/lib/api.ts` lines 185–193 — 4 helpers implemented: `fetchWithingsStatus`, `fetchWithingsAuthUrl`, `syncWithingsWeight`, `disconnectWithings`.
    - Plan section header said "5 API helpers" but plan code sample only showed 4. Only 4 are needed for the 5 endpoints (callback is not called by frontend). This is a plan inconsistency, not an implementation error.
    - The `syncWithingsWeight` return type at line 188 is `{ status: string; synced: number; start_date: string; end_date: string }` — matching the actual API response. Settings.tsx uses `result.synced` (line 328), consistent.
*   **Dynamic Check:** TypeScript types are consistent with backend response.
*   **Notes:** The return type is internally consistent even though it deviates from the plan's original `measurements_stored`/`days_fetched` shape.

### Step 5.C: `useWithingsStatus` hook in `frontend/src/hooks/useApi.ts`
*   **Status:** ✅ Verified
*   **Evidence:** `frontend/src/hooks/useApi.ts` lines 195–204 — hook present with `queryKey: ['withings-status']`, `enabled: isAuthenticated`, `refetchInterval: 30000`.
*   **Dynamic Check:** N/A.

### Step 5.D: Withings card in Settings System tab
*   **Status:** ✅ Verified
*   **Evidence:** `frontend/src/pages/Settings.tsx` — Withings card at line 710+, with `Scale` icon, connect/sync/disconnect handlers (lines 311–346), state variables (lines 107–109), proper `queryClient.invalidateQueries` for both `pmc` (line 329) and `withings-status` (lines 330, 342).
*   **Dynamic Check:** N/A (frontend static analysis).
*   **Notes:** Settings.tsx shows `latest_weight_kg` and `last_measurement_date` (line 726–729) which matches the implemented `WithingsStatus` interface, not the plan's `user_id`/`token_valid`.

### Step 6.A/6.B/6.C/6.D: Analysis page weight tab
*   **Status:** ✅ Verified
*   **Evidence:**
    - `frontend/src/pages/Analysis.tsx` line 56: `type Tab = 'power-curve' | 'efficiency' | 'zones' | 'ftp-history' | 'weight'`
    - Line 63: `{ key: 'weight', label: 'Weight', icon: Scale }` in TABS array
    - Lines 664–748: `WeightChart` component using `usePMC()` data with date range filtering, empty-state message, Withings connection prompt, and `last_measurement_date` display
    - Line 804: `{activeTab === 'weight' && <WeightChart dateRange={dateRange} />}`
*   **Dynamic Check:** N/A.
*   **Notes:** The `WeightChart` additionally uses `useWithingsStatus()` for the "last synced" badge and empty-state hint — a useful enhancement not in the plan. `Scale` icon from lucide-react is used (plan noted it as the correct icon).

### Step 7.A: Campaign 11 in Master Roadmap
*   **Status:** ✅ Verified
*   **Evidence:** `plans/00_MASTER_ROADMAP.md` line 49 — Campaign 11 entry present with correct description.
*   **Dynamic Check:** N/A.

---

## 🚨 Anti-Shortcut & Quality Scan

*   **Placeholders/TODOs in new/modified files:**
    - `server/services/withings.py` line 166–167: `except Exception: pass` — this is a silent-fail swallow in `get_status()` around the DB lookup for last measurement. It is intentional (optional enrichment, graceful degradation) but causes a unit test (`test_get_status_returns_correct_shape`) to pass without mocking `get_db`, masking incomplete test coverage.
    - No `TODO`, `FIXME`, `HACK`, or lazy string placeholders found in any new or modified file.
    - `datetime.utcfromtimestamp()` at `server/services/withings.py` line 118 — deprecated in Python 3.12, triggers DeprecationWarning in test output. Should use `datetime.fromtimestamp(ts, tz=timezone.utc)`.

*   **Test Integrity:**
    - **Unit tests:** 16 tests in `tests/unit/test_withings.py` — all real, none skipped or faked. 88/88 total unit tests PASS.
    - **Integration tests:** `tests/integration/test_withings_integration.py` is MISSING ENTIRELY. The plan required this file with at least 5 integration tests: DB table migration, upsert behavior, status endpoint, sync endpoint, PMC weight priority. None of these have runtime verification.
    - **Test gap — `_refresh_tokens` wrong action:** Unit test `test_get_valid_access_token_refreshes_expired_token` mocks `httpx.post` and validates the return value, but does NOT assert that the POST body contains `"action": "refreshaccesstoken"`. The wrong action string passes tests silently.
    - **Test gap — `fetch_weight_measurements` not-connected case:** The plan required a test that `fetch_weight_measurements()` raises when not connected. This test was not implemented. The implementation doesn't guard this case either.

---

## 🎯 Conclusion

**Overall Status: FAIL**

The feature is substantially implemented and the unit test suite passes completely (88/88). Frontend integration is consistent and functional. The Withings card in Settings, the weight tab in Analysis, and the PMC priority update are all correct. However, three issues require resolution before this feature can be considered production-ready:

**Critical (must fix):**

1.  **`_refresh_tokens()` uses wrong Withings API action** (`server/services/withings.py` line 70). `"action": "requesttoken"` must be `"action": "refreshaccesstoken"`. This will cause every token refresh to fail silently in production — any connection more than 3 hours old will break without error.

2.  **Integration test file is entirely missing** (`tests/integration/test_withings_integration.py`). The plan required it as a deliverable. Without it, there is zero runtime verification of: DB migration correctness, `body_measurements` upsert behavior, endpoint HTTP status codes, or PMC weight priority logic.

**Significant (should fix):**

3.  **`_get_valid_access_token()` does not guard for empty token** (`server/services/withings.py` lines 87–95). When no token exists, expiry defaults to 0, causing `time.time() >= 0 - 300` to always be True, which calls `_refresh_tokens()` (which will fail). This should check `if not get_setting("withings_access_token"): return None` (or raise) before the expiry check.

**Minor (quality):**

4.  `datetime.utcfromtimestamp()` deprecation warning at line 118 of `server/services/withings.py`. Fix: `datetime.fromtimestamp(grp["date"], tz=timezone.utc).strftime("%Y-%m-%d")`.

5.  `exchange_code()` does not check `resp.status_code` before calling `resp.json()`. A network failure or non-JSON 5xx response will raise an unhandled exception rather than returning a structured error.

6.  `/api/withings/callback` raises `HTTPException(400)` when code/state are missing, rather than redirecting to `/settings?withings=error` as the plan specified. The browser receives a 400 JSON error instead of being redirected.

**Actionable recommendations for the Engineer:**
- Fix line 70: `"action": "requesttoken"` → `"action": "refreshaccesstoken"`
- Add guard in `_get_valid_access_token()`: return None/raise if `withings_access_token` is empty before checking expiry
- Create `tests/integration/test_withings_integration.py` per the plan's Step 3.A/3.E/4.A specifications
- Fix `datetime.utcfromtimestamp()` → `datetime.fromtimestamp(ts, tz=timezone.utc)` and add `timezone` to the datetime import
