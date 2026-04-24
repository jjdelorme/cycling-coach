import functools
import inspect
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

    Only wraps plain functions. Tool *objects* (instances of ADK BaseTool
    subclasses such as AgentTool, PreloadMemoryTool, GoogleSearchTool)
    must be passed directly to the Agent's tools list — wrapping them with
    @functools.wraps would set __wrapped__ to a non-callable instance and
    crash inspect.signature() during ADK schema generation. Raise loudly
    at registration time so the misuse is caught immediately rather than
    surfacing as a 500 on the first chat() call.
    """
    if hasattr(fn, "_get_declaration"):
        raise TypeError(
            f"json_safe_tool was given an ADK tool object ({type(fn).__name__}); "
            "tool objects must be appended to the agent's tools list directly, "
            "not wrapped. See server/coaching/agent.py for the AgentTool / "
            "preload_memory_tool pattern."
        )
    if not inspect.isfunction(fn) and not inspect.ismethod(fn):
        raise TypeError(
            f"json_safe_tool expected a function, got {type(fn).__name__}: {fn!r}"
        )

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        return to_jsonable_python(result)
    return wrapper
