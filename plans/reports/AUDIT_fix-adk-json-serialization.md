# Plan Validation Report: Campaign 22 — ADK Serialization

## Summary
* **Overall Status:** READY-WITH-CAVEATS (minor cleanup recommended; not a hard block)
* **Completion Rate:** 4/5 plan steps verified; 1 step skipped because its premise was already obsolete.

## What Changed (vs `main`)
* New shared wrapper `server/utils/adk.py::json_safe_tool` using `pydantic_core.to_jsonable_python` and `functools.wraps` to preserve ADK schema introspection.
* `server/coaching/agent.py` and `server/nutrition/agent.py` dynamically wrap every function tool (and write tools post-permission-gate). `AgentTool(...)` instance left unwrapped per plan.
* `server/routers/nutrition.py` casts `r["date"]` to `str(...)` in three meal-plan response paths (independent of the wrapper — needed because `routers/nutrition.py` returns to FastAPI/JSON, not ADK).
* Three integration test files updated to use `start_time` instead of the now-removed `rides.date` column (rebased onto recent timezone migration `0006_timezone_schema.sql`).
* Plan + roadmap docs added.

## Detailed Audit
### Step 1.A — Shared wrapper
* Status: Verified. `server/utils/adk.py` lines 1-19 implements the spec exactly.
### Step 1.B — Nutrition agent wiring
* Status: Verified. `server/nutrition/agent.py` lines 240-258 wrap raw tools and gated write tools.
### Step 1.C — Coaching agent wiring
* Status: Verified. `server/coaching/agent.py` lines 249-277. `AgentTool(agent=get_nutritionist_agent())` is correctly appended unwrapped.
### Step 2.A — Remove `_serialize_dates` from `server/nutrition/tools.py`
* Status: N/A — `_serialize_dates` does not exist on `main` (verified via `git show main:server/nutrition/tools.py`). The plan's premise was stale. No action required, but the plan checklist should be marked accordingly.
### Step 2.B — Tests
* Status: Pass. `pytest` (unit suite) → **390 passed, 0 failed, 2 warnings** in 5.17s.

## Anti-Shortcut & Quality Scan
* Placeholders/TODOs: None found in modified files.
* Test integrity: No tests skipped or commented out. Integration test edits are legitimate schema-migration alignment, not gutting.
* **Gap (non-blocking):** No dedicated unit test for `json_safe_tool` itself. Recommend a small `tests/unit/test_adk_utils.py` covering: (a) `date`/`datetime`/`UUID`/nested dict round-trip, (b) `__name__`/`__doc__`/`__annotations__` preserved through `functools.wraps`. The wrapper is exercised transitively in `test_agent_tool_wiring.py` and `test_nutrition_agent.py`, but direct coverage is the right hygiene per AGENTS.md.

## Issues Found
1. **Import-before-docstring in `server/coaching/agent.py` line 1.** `from server.utils.adk import json_safe_tool` was inserted **above** the module docstring `"""ADK-based coaching agent setup."""`. Result: the docstring is now a dead string literal, and `server.coaching.agent.__doc__` is `None`. Cosmetic but trivial to fix — move the import below the docstring (matches the clean placement done in `nutrition/agent.py` line 8).
2. **Plan step 2.A is misleading** — `_serialize_dates` was never present, so the plan's "remove the hack" success criterion was a no-op. Recommend updating the plan markdown to reflect this so the next reviewer doesn't think work was skipped.

## Conclusion
Implementation is correct, minimal, and matches AGENTS.md principles. Unit tests are green. Two minor items (cosmetic import order + a missing focused unit test for the wrapper) should be addressed before push, but neither is a functional blocker.

**Recommended actions before push to test:**
1. Move the `from server.utils.adk import json_safe_tool` import below the module docstring in `server/coaching/agent.py`.
2. Add `tests/unit/test_adk_utils.py` with ~3 small assertions (date/UUID/nested + `functools.wraps` preservation).
3. Run `./scripts/run_integration_tests.sh` once before push since the integration suite was edited to follow the recent `rides.date` removal — quick sanity check, ~1 min.

Verdict: **READY-WITH-CAVEATS** — safe to push to a test environment after the two trivial cleanups above; no functional risk identified.
