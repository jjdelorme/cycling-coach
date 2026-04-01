# Feature Implementation Plan: Delete Ride

## 🔍 Analysis & Context
*   **Objective:** Implement a full-stack feature to hard-delete a ride and its associated data, then recalculate the Performance Management Chart (PMC) to maintain metric integrity.
*   **Affected Files:**
    *   `server/routers/rides.py`
    *   `frontend/src/lib/api.ts`
    *   `frontend/src/hooks/useApi.ts`
    *   `frontend/src/components/WorkoutViewer.tsx`
    *   `tests/test_api.py`
*   **Key Dependencies:** `server.ingest.compute_daily_pmc` for PMC recalculation, React Query for frontend state invalidation.
*   **Risks/Edge Cases:** Ensuring cascading deletes for `ride_records`, `ride_laps`, and `power_bests` work correctly without orphaned rows. Recalculating PMC from the date of the deleted ride is required. We must explicitly *not* delete the raw JSON files from disk.

## 📋 Micro-Step Checklist
- [x] Phase 1: The Backend Endpoint & PMC Recalculation
  - [x] Step 1.A: Write Backend Tests for Ride Deletion (✅ Completed: tests/test_delete_ride.py)
  - [x] Step 1.B: Implement `DELETE /api/rides/{ride_id}` (✅ Completed: server/routers/rides.py)
- [x] Phase 2: Frontend API & State Management
  - [x] Step 2.A: Add API call and React Query Mutation (✅ Completed: frontend/src/lib/api.ts, frontend/src/hooks/useApi.ts)
- [x] Phase 3: UI Implementation
  - [x] Step 3.A: Add Delete Button and Confirmation Dialog to Ride Detail View (✅ Completed: frontend/src/pages/Rides.tsx)

## 📝 Step-by-Step Implementation Details

### Phase 1: The Backend Endpoint & PMC Recalculation
1.  **Step 1.A (The Unit Test Harness):** Define the verification requirement.
    *   *Target File:* `tests/test_api.py`
    *   *Test Cases to Write:*
        *   Assert `DELETE /api/rides/{ride_id}` returns 200 OK.
        *   Assert querying the deleted ride returns 404.
        *   Assert associated `ride_records`, `ride_laps`, and `power_bests` are removed from the DB.
        *   Assert `compute_daily_pmc` was called.
2.  **Step 1.B (The Implementation):** Execute the core change.
    *   *Target File:* `server/routers/rides.py`
    *   *Exact Change:* Add a `DELETE` endpoint.
        ```python
        from server.ingest import compute_daily_pmc

        @router.delete("/{ride_id}")
        def delete_ride(ride_id: int, user: CurrentUser = Depends(require_write)):
            with get_db() as conn:
                # 1. Get ride date for PMC recalculation
                ride = conn.execute("SELECT date FROM rides WHERE id = ?", (ride_id,)).fetchone()
                if not ride:
                    raise HTTPException(status_code=404, detail="Ride not found")
                
                ride_date = ride["date"]
                
                # 2. Delete dependencies
                conn.execute("DELETE FROM ride_records WHERE ride_id = ?", (ride_id,))
                conn.execute("DELETE FROM ride_laps WHERE ride_id = ?", (ride_id,))
                conn.execute("DELETE FROM power_bests WHERE ride_id = ?", (ride_id,))
                
                # 3. Delete ride
                conn.execute("DELETE FROM rides WHERE id = ?", (ride_id,))
                
                # 4. Recalculate PMC
                compute_daily_pmc(conn, since_date=ride_date)
                
            return {"status": "ok"}
        ```

### Phase 2: Frontend API & State Management
1.  **Step 2.A (The API Setup):** Add API wrappers.
    *   *Target File:* `frontend/src/lib/api.ts`
    *   *Exact Change:* Add `export const deleteRide = (id: number) => request<{status: string}>('/api/rides/' + id, { method: 'DELETE' })`
    *   *Target File:* `frontend/src/hooks/useApi.ts`
    *   *Exact Change:* Add `useDeleteRide` mutation that invalidates `['rides']`, `['pmc']`, `['weekly-summary']`, and `['ride', id]`.

### Phase 3: UI Implementation
1.  **Step 3.A (The UI Update):** Add delete functionality to the UI.
    *   *Target File:* `frontend/src/components/WorkoutViewer.tsx`
    *   *Exact Change:* Add a "Delete Ride" button styled with a danger color. When clicked, display a standard `window.confirm` dialog stating: `"Are you sure you want to delete this ride? This will permanently remove its data and recalculate your Fitness/Fatigue metrics from this date forward."`. If confirmed, call the `useDeleteRide` mutation, and on success, trigger `onClose()` to dismiss the viewer.

### 🧪 Global Testing Strategy
*   **Unit Tests:** Verify the endpoint deletes records without affecting other rides.
*   **Integration Tests:** Run `pytest tests/test_api.py` to ensure the endpoint correctly cascades deletes and triggers PMC updates without file I/O operations touching the underlying JSON.

## 🎯 Success Criteria
*   Backend endpoint successfully deletes a ride and all related records.
*   PMC is dynamically recalculated starting from the date of the deleted ride.
*   Local JSON files are ignored and left intact on disk.
*   Frontend provides a clear warning and gracefully updates the UI and invalidates caches upon deletion.