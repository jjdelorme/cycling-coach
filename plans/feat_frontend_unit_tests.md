# Feature Implementation Plan: Frontend Unit Testing Suite

## 🔍 Analysis & Context
*   **Objective:** Establish a comprehensive unit and integration testing suite for the React UI frontend to prevent regressions and improve maintainability.
*   **Affected Files:** `frontend/package.json`, `frontend/vitest.config.ts`, `frontend/src/setupTests.ts`, `frontend/src/lib/*`, `frontend/src/components/*`, `frontend/src/hooks/*`, `frontend/src/pages/*`
*   **Key Dependencies:** `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `msw` (for API mocking).
*   **Risks/Edge Cases:** Currently, the frontend only has pure-function tests (e.g., `fmtSport` in `format.test.ts`) because a DOM testing environment is not configured. Testing components heavily reliant on `Chart.js` (like `RideTimelineChart.tsx`) or `@tanstack/react-query` requires proper mocking and provider wrapping. Testing `useApi.ts` mutations requires ensuring query invalidations run properly.

## 📋 Micro-Step Checklist
- [ ] Phase 1: Test Environment Configuration
  - [ ] Step 1.A: Install Testing Libraries
  - [ ] Step 1.B: Configure Vitest and jsdom
- [ ] Phase 2: Core Logic & Utilities Coverage (Pure Functions)
  - [ ] Step 2.A: Expand Formatting Tests
  - [ ] Step 2.B: API Wrapper Tests
  - [ ] Step 2.C: Auth & Unit Context Tests
- [ ] Phase 3: Custom Hooks
  - [ ] Step 3.A: React Query Mutations (useApi)
  - [ ] Step 3.B: Complex State Hooks (useSyncSingleRide)
- [ ] Phase 4: Shared Components
  - [ ] Step 4.A: Pure Visual Components (SportIcon, UserAvatar)
  - [ ] Step 4.B: Interactive Components (CoachPanel)
  - [ ] Step 4.C: Chart Components (RideTimelineChart)
- [ ] Phase 5: Key Page Integration Tests
  - [ ] Step 5.A: Dashboard Page Integration
  - [ ] Step 5.B: Rides List Integration

## 📝 Step-by-Step Implementation Details

### Prerequisites
Node.js 18+ and `npm` installed. Running development server is not required for Vitest.

#### Phase 1: Test Environment Configuration
1.  **Step 1.A (Install Testing Libraries):** Add required packages for DOM testing and mocking.
    *   *Target File:* `frontend/package.json`
    *   *Exact Change:* Run `npm install -D jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event msw` inside the `frontend/` directory.
2.  **Step 1.B (Configure Vitest and jsdom):** Setup the DOM environment for React components.
    *   *Target File:* `frontend/vitest.config.ts` and `frontend/src/setupTests.ts`
    *   *Exact Change:* 
        *   Create `frontend/src/setupTests.ts` containing: `import '@testing-library/jest-dom'`
        *   Update `vitest.config.ts` to include:
            ```typescript
            export default defineConfig({
              test: {
                globals: true,
                environment: 'jsdom',
                setupFiles: ['./src/setupTests.ts'],
              },
            })
            ```
    *   *Verification:* Run `npm test` and ensure existing tests pass without errors.

#### Phase 2: Core Logic & Utilities Coverage
1.  **Step 2.A (Expand Formatting Tests):** Cover missing utilities.
    *   *Target File:* `frontend/src/lib/format.test.ts`
    *   *Test Cases to Write:* Assert `fmtDuration` formats seconds correctly (e.g., `3600 -> 1h 0m`, `null -> --`). Assert `fmtDistance` handles metric vs imperial conversions correctly. Assert `fmtElevation` handles feet vs meters.
2.  **Step 2.B (API Wrapper Tests):** Test global fetch wrapper.
    *   *Target File:* `frontend/src/lib/api.test.ts` (new)
    *   *Test Cases to Write:* Mock `global.fetch`. Assert that `request()` injects `Authorization` header when a token exists. Assert that `request()` throws `'Unauthorized — please sign in again'` when response status is 401.

#### Phase 3: Custom Hooks
1.  **Step 3.A (React Query Mutations):** Test query invalidation logic.
    *   *Target File:* `frontend/src/hooks/useApi.test.tsx` (new)
    *   *Test Cases to Write:* Wrap with `QueryClientProvider`. Mock `api.deleteRide`. Call `useDeleteRide()`. Assert `mutate` invalidates `['rides']`, `['pmc']`, and other specified keys.
2.  **Step 3.B (Complex State Hooks):** Test single ride sync flow.
    *   *Target File:* `frontend/src/hooks/useSyncSingleRide.test.tsx` (new)
    *   *Test Cases to Write:* Mock API response states (syncing, completed). Assert hook transitions from `isSyncing = true` to `false` and triggers the `onSuccess` callback.

#### Phase 4: Shared Components
1.  **Step 4.A (Pure Visual Components):** Test isolated rendering.
    *   *Target File:* `frontend/src/components/SportIcon.test.tsx` (new) and `UserAvatar.test.tsx` (new)
    *   *Test Cases to Write:* 
        *   `SportIcon`: Render with `sport="Ride"`. Assert `<svg>` contains the correct cycling path. Assert `sport="Unknown"` renders the fallback icon.
        *   `UserAvatar`: Render with missing `picture_url`. Assert fallback initial (e.g., "J" for John) is rendered in the avatar circle.
2.  **Step 4.B (Interactive Components):** Test `CoachPanel` logic.
    *   *Target File:* `frontend/src/components/CoachPanel.test.tsx` (new)
    *   *Test Cases to Write:* Mock `useSessions` and `useSendChat`. Render `CoachPanel`. Assert typing into the input updates state. Assert clicking "Send" calls the mock `sendChat` function with the correct session ID and clears the input.
3.  **Step 4.C (Chart Components):** Test chart rendering boundaries.
    *   *Target File:* `frontend/src/components/RideTimelineChart.test.tsx` (new)
    *   *Test Cases to Write:* Mock `react-chartjs-2` to prevent canvas errors. Pass dummy `streams` data. Assert the component renders the wrapper `div` and passes the correctly formatted `data` prop to the mocked `Chart` component.

#### Phase 5: Key Page Integration Tests
1.  **Step 5.A (Dashboard Page Integration):** Test page data loading.
    *   *Target File:* `frontend/src/pages/Dashboard.test.tsx` (new)
    *   *Test Cases to Write:* Wrap page in `QueryClientProvider` and `BrowserRouter`. Mock `usePMC`, `useWeeklyOverview`, `useActivityDates`. Assert that loading spinners appear initially, followed by the rendering of the `WeeklyOverview` component and PMC chart area once data is mocked as "loaded".
2.  **Step 5.B (Rides List Integration):** Test list rendering and interactions.
    *   *Target File:* `frontend/src/pages/Rides.test.tsx` (new)
    *   *Test Cases to Write:* Mock `useRides` to return an array of 2 rides. Assert that two ride cards are rendered in the DOM with their respective titles. Assert that clicking the delete button on a ride card opens the confirmation modal (if applicable) or calls `deleteRide`.

### 🧪 Global Testing Strategy
*   **Unit Tests:** Utilities (`lib/`) and custom hooks (`hooks/`) should have complete edge-case coverage as they form the backbone of UI logic. Pure visual components should be tested for exact render output states (prop permutations).
*   **Integration Tests:** Pages should be tested for data-fetching lifecycle (loading -> error -> success states) and child component assembly. Use MSW (Mock Service Worker) for API mocking in complex components to avoid brittle fetch mocks, or heavily rely on `@tanstack/react-query` hook mocking.

## 🎯 Success Criteria
*   Running `npm test` executes the full suite in the `jsdom` environment without canvas or missing DOM API errors.
*   The overall frontend test coverage for lines, functions, and branches reaches > 80% (verifiable via `npm run test -- --coverage`).
*   All identified edge cases in pure functions (like unit conversion missing values) are handled and explicitly asserted.
