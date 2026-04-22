# Feature Implementation Plan: ADK Tool Serialization Safety

## 🔍 Analysis & Context
*   **Objective:** Fix an AI agent crash (`TypeError: Object of type date is not JSON serializable`) caused by native Python `date`/`datetime` (or `UUID`) objects in tool returns being passed to the Google ADK.
*   **Current Workarounds:**
    *   `server/nutrition/tools.py` uses a manual recursive `_serialize_dates` wrapper around every return.
    *   `server/coaching/tools.py` relies on explicit string casting in SQL (`::TEXT`) or manual `str(row['date'])`.
    *   Both approaches are fragile, leak serialization concerns into business logic, and require perfect developer memory.
*   **Proposed Architecture Evaluation:** The proposed "Registration-Layer Wrapper" using `pydantic.core.to_jsonable_python` is the **optimal solution**.
    *   *Why not Pydantic Models?* Too much boilerplate for simple SQL queries, bloats the LLM schema/responses, and adds strict validation where none is needed (it's internal trusted data).
    *   *Why not DB-level casting?* Leaks serialization formatting into the data access layer, leading to ugly queries and missed edge cases.
    *   *Why `to_jsonable_python`?* It's highly optimized (Rust), perfectly handles dates/UUIDs/nested structures, and cleanly decouples the API/LLM requirement (JSON string) from the domain logic (which should return native Python types).
*   **Refinement to Proposal:** Instead of putting the wrapper *only* in `server/nutrition/agent.py`, we should place it in a shared location (e.g., `server/utils/adk.py`) and apply it to BOTH agents (`nutrition` and `coaching`). This unifies the pattern and prevents the bug from ever surfacing in the coaching tools.

## 📋 Micro-Step Checklist
- [ ] Phase 1: Shared Serialization Infrastructure
  - [ ] Step 1.A: Create `_json_safe_tool` in `server/utils/adk.py`
  - [ ] Step 1.B: Apply wrapper in `server/nutrition/agent.py`
  - [ ] Step 1.C: Apply wrapper in `server/coaching/agent.py`
- [ ] Phase 2: Cleanup and Refactor
  - [ ] Step 2.A: Remove `_serialize_dates` from `server/nutrition/tools.py`
  - [ ] Step 2.B: Run Integration Tests

## 📝 Step-by-Step Implementation Details

### Prerequisites
`pydantic_core` is already installed as a dependency of `pydantic` (v2), which is listed in `requirements.txt`.

#### Phase 1: Shared Serialization Infrastructure

1.  **Step 1.A (The Shared Wrapper):** Implement the decorator.
    *   *Target File:* `server/utils/adk.py` (Create this file)
    *   *Exact Change:*
        ```python
        import functools
        from pydantic_core import to_jsonable_python

        def json_safe_tool(fn):
            """
            Wrap an ADK tool to ensure its return value is fully JSON serializable.
            Uses Pydantic's optimized core to convert dates, datetimes, UUIDs, and
            nested structures into native Python equivalents (strings/dicts/lists)
            that the ADK can safely pass to json.dumps().
            
            Uses @functools.wraps to perfectly preserve the original function's 
            signature, docstring, and type hints, which the Google ADK relies on 
            to generate the Gemini Tools schema.
            """
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                return to_jsonable_python(result)
            return wrapper
        ```

2.  **Step 1.B (Nutrition Agent Integration):** Apply dynamically to all nutrition tools.
    *   *Target File:* `server/nutrition/agent.py`
    *   *Exact Change:*
        1. Import the new decorator: `from server.utils.adk import json_safe_tool`.
        2. In `_get_agent()`, wrap every tool before appending to the `Agent`'s tools list:
        ```python
        def _get_agent():
            raw_tools = [
                get_meal_history,
                get_daily_macros,
                # ... all other read-only tools ...
            ]
            
            tools = [json_safe_tool(fn) for fn in raw_tools]

            for fn in _WRITE_TOOLS:
                # Wrap write tools with both permission gate and json serialization
                tools.append(json_safe_tool(_permission_gate(fn)))

            return Agent(
                # ...
                tools=tools,
            )
        ```

3.  **Step 1.C (Coaching Agent Integration):** Apply dynamically to all coaching tools.
    *   *Target File:* `server/coaching/agent.py`
    *   *Exact Change:* Apply the identical pattern from Step 1.B. Import `json_safe_tool`, list all read-only tools in `raw_tools`, wrap them in a list comprehension, and wrap the `_WRITE_TOOLS` before adding them to the final `tools` list.
    *   *Note:* Handle `AgentTool(agent=get_nutritionist_agent())` properly. It's an instance of a class, not a function, so it should *not* be wrapped by `json_safe_tool`. Only wrap the standalone function tools.

#### Phase 2: Cleanup and Refactor

1.  **Step 2.A (Remove Manual Workaround):** Strip out the fragile implementation.
    *   *Target File:* `server/nutrition/tools.py`
    *   *Exact Change:*
        1. Delete the `_serialize_dates` helper function at the top of the file.
        2. Remove all `_serialize_dates(...)` calls wrapping the `return` statements across all 9 tools in the file. They should now return pure Python types (e.g., `return {"date": date, "total_calories": total_cal, ...}`).

2.  **Step 2.B (Verification):** Validate no regressions.
    *   *Action:* Run unit/integration tests (`pytest tests/`) to ensure the agent instantiates correctly and queries return cleanly.
    *   *Success:* All tests pass. `json_safe_tool` correctly retains `__annotations__` so ADK doesn't fail on schema generation.

## 🎯 Success Criteria
*   The `_serialize_dates` hack is completely removed from `server/nutrition/tools.py`.
*   All function tools registered with *both* the Nutritionist and Coaching agents are dynamically wrapped with `json_safe_tool`.
*   No `TypeError: Object of type date is not JSON serializable` occurs during ADK execution for any data type (date, UUID, etc.).
*   The ADK correctly builds the function schema for Gemini because `functools.wraps` is utilized.