# Fix Implementation Plan: Ride Details Date Navigation Bug

## 🔍 Analysis & Context
*   **Objective:** Fix a bug where clicking the "back" or "next" arrows on the date widget within the ride details page incorrectly routes to the planned workout view instead of the completed ride view for that date.
*   **Affected Files:** `frontend/src/components/DayDetailShell.tsx`
*   **Key Dependencies:** `frontend/src/lib/api.ts` (API client for authenticated and timezone-aware requests)
*   **Root Cause:**
    *   The `DayDetailShell` component is currently making a raw, unauthenticated `fetch()` call directly to `/api/rides?start_date=${date}&end_date=${date}` to determine if a completed ride exists on the target date.
    *   This raw `fetch()` call is missing two critical headers injected by the centralized `api.ts` client:
        1.  `Authorization: Bearer <token>` (causing a 401 error).
        2.  `X-Client-Timezone` (causing potential date mismatching on the backend since it assumes UTC without it).
    *   When the raw `fetch` call fails, the `catch` block silently swallows the error (`console.warn`) and blindly falls back to navigating to `/rides/by-date/${date}`.
    *   The `/rides/by-date/:date` route in `Rides.tsx` is explicitly designed to show *only* planned workouts for a given date, resulting in completed rides being skipped.

## 📋 Micro-Step Checklist
- [ ] Phase 1: Fix API call in `DayDetailShell`
  - [ ] Step 1.A: Import `fetchRides`
  - [ ] Step 1.B: Replace raw `fetch` with `fetchRides`
  - [ ] Step 1.C: Implement loading state to prevent rapid clicks

## 📝 Step-by-Step Implementation Details

### Prerequisites
None

#### Phase 1: Fix API call in `DayDetailShell`
1.  **Step 1.A (Import `fetchRides`):** Import the authenticated API client into the component.
    *   *Target File:* `frontend/src/components/DayDetailShell.tsx`
    *   *Exact Change:* Add `import { fetchRides } from '../lib/api'` to the top of the file, alongside other imports.
2.  **Step 1.B (Replace raw `fetch` with `fetchRides`):** Update the `navigateToDate` function to use the correct API client to query for rides on the target date.
    *   *Target File:* `frontend/src/components/DayDetailShell.tsx`
    *   *Exact Change:* Inside `async function navigateToDate(date: string)`, replace the `try/catch` block fetching logic:
        ```javascript
        // OLD:
        const response = await fetch(`/api/rides?start_date=${date}&end_date=${date}`)
        if (response.ok) {
          const ridesOnDate = await response.json()
          if (ridesOnDate && ridesOnDate.length > 0) {
            navigate(`/rides/${ridesOnDate[0].id}`)
            return
          }
        }

        // NEW:
        const ridesOnDate = await fetchRides({ start_date: date, end_date: date, limit: 1 })
        if (ridesOnDate && ridesOnDate.length > 0) {
          navigate(`/rides/${ridesOnDate[0].id}`)
          return
        }
        ```
3.  **Step 1.C (Implement loading state):** Add a boolean state to disable the navigation buttons while the API call resolves to prevent race conditions from rapid clicking.
    *   *Target File:* `frontend/src/components/DayDetailShell.tsx`
    *   *Exact Change:*
        *   Update the React import to: `import { useMemo, useState } from 'react'`
        *   Add state: `const [isLoading, setIsLoading] = useState(false)` inside the component.
        *   Wrap the body of `navigateToDate` with `setIsLoading(true)` and `setIsLoading(false)` inside a `finally` block:
        ```javascript
        async function navigateToDate(date: string) {
          setIsLoading(true)
          try {
            const ridesOnDate = await fetchRides({ start_date: date, end_date: date, limit: 1 })
            if (ridesOnDate && ridesOnDate.length > 0) {
              navigate(`/rides/${ridesOnDate[0].id}`)
              return
            }
          } catch (err) {
            console.warn('Failed to fetch ride for date:', err)
          } finally {
            setIsLoading(false)
          }
          navigate(`/rides/by-date/${date}`)
        }
        ```
        *   Add `disabled={!prevDate || isLoading}` and `disabled={!nextDate || isLoading}` to the "back" and "next" `<button>` elements respectively. Add `opacity-50` to the button className when `isLoading` is true (e.g. `` className={`p-2 rounded-md transition-all text-text-muted hover:text-text hover:bg-surface-low disabled:opacity-20 ${isLoading ? 'opacity-50 cursor-wait' : ''}`} ``).

### 🧪 Global Testing Strategy
*   **Manual Verification:** Launch the local dev server. Create a planned workout on Day A and a completed ride on Day B. Click the date widget "next" and "back" arrows to ensure the app routes to the actual `/rides/:id` page for the completed ride and does not mistakenly show the planned workout view for Day B.
*   **Network Tab:** Confirm the `GET /api/rides?start_date=X&end_date=X&limit=1` request in the browser network tab contains the `Authorization` Bearer token and the `X-Client-Timezone` header.

## 🎯 Success Criteria
*   When a user clicks "next" or "back" in the `DayDetailShell` widget, the app reliably routes to `/rides/:id` if a completed ride exists for the target date.
*   The backend logs show successful `GET /api/rides` queries containing the correct headers, without 401 Unauthorized errors during date navigation.
*   Rapid clicking on the date navigation buttons is debounced/prevented by the disabled loading state.