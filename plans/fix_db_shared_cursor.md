# Feature Implementation Plan: Fix Database Shared Cursor Anti-pattern

## 🔍 Analysis & Context
*   **Objective:** Refactor `_DbConnection` in `server/database.py` to create a new cursor for each `execute()` and `executemany()` call instead of using a single shared `self._cursor`.
*   **Reasoning:** Using a shared cursor is a known anti-pattern in `psycopg2` wrappers because it leads to result-set overwriting if multiple queries are active on the same connection (e.g., nested loops).
*   **Affected Files:** 
    *   `server/database.py`
*   **Key Dependencies:** `psycopg2`, `psycopg2.extras.RealDictCursor`
*   **Risks/Edge Cases:** 
    *   **Cursor Leakage:** Cursors should be closed. However, `psycopg2` closes all cursors when the connection is closed. Since `get_db()` ensures connection closure, the risk is minimal.
    *   **Performance:** Slight overhead of creating a new cursor object per query. Negligible for typical web application loads and standard DB operations.
    *   **Compatibility:** All existing code uses `.fetchall()` or `.fetchone()` or stores the returned cursor, so returning a new cursor is backward-compatible.

## 📋 Micro-Step Checklist
- [ ] Phase 1: Refactor `_DbConnection`
  - [ ] Step 1.A: Update `_DbConnection` implementation in `server/database.py`.
- [ ] Phase 2: Verification
  - [ ] Step 2.A: Run existing integration tests.
  - [ ] Step 2.B: Add a new integration test for nested queries to verify the fix.

## 📝 Step-by-Step Implementation Details

### Phase 1: Refactor `_DbConnection`

#### Step 1.A: Update `server/database.py`
*   **Target File:** `server/database.py`
*   **Change:**
    *   Remove `self._cursor` from `__init__`.
    *   Update `execute()` and `executemany()` to create a local cursor and return it.
    *   Update `close()` to remove `self._cursor.close()`.

```python
class _DbConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        adapted = self._adapt_sql(sql)
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        t0 = time.monotonic()
        cursor.execute(adapted, params)
        # ... logging logic ...
        return cursor

    def executemany(self, sql, params_list, page_size=1000):
        adapted = self._adapt_sql(sql)
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        t0 = time.monotonic()
        psycopg2.extras.execute_batch(cursor, adapted, params_list, page_size=page_size)
        # ... logging logic ...
        return cursor

    def close(self):
        self._conn.close()
```

### Phase 2: Verification

#### Step 2.A: Run Integration Tests
*   **Action:** Run `./scripts/run_integration_tests.sh`.
*   **Success:** All existing tests pass.

#### Step 2.B: Add Nested Query Test
*   **Target File:** `tests/integration/test_database.py`
*   **Test Case:**
```python
def test_nested_queries(db_conn):
    """Verify that nested queries do not overwrite each other (requires independent cursors)."""
    # Create some dummy data if needed, but we can just use system tables
    cursor1 = db_conn.execute("SELECT 1 as val UNION SELECT 2 as val ORDER BY val")
    results = []
    for row in cursor1:
        # With a shared cursor, this execute() would reset cursor1's state
        cursor2 = db_conn.execute("SELECT %s + 10 as val2", (row['val'],))
        results.append(cursor2.fetchone()['val2'])
    
    assert results == [11, 12], f"Expected [11, 12], got {results}. Shared cursor might be overwriting results."
```

## 🎯 Success Criteria
*   `_DbConnection` no longer holds a shared `self._cursor`.
*   Each `execute()` and `executemany()` call returns a fresh cursor.
*   Nested query loops work correctly without result set interference.
*   No regressions in existing database-dependent functionality.
