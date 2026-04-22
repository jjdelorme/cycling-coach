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
