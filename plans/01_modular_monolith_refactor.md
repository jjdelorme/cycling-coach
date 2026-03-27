# Plan 01: Modular Monolith Refactor

This campaign transforms the current "Type-Based" frontend structure into a "Feature-Driven" architecture. This is a foundational refactor to enable long-term scale and isolation of concerns.

## 🥅 Objective
*   Refactor `frontend/src` into `core/` and `features/`.
*   Establish strict boundaries with `index.ts` public APIs.
*   Characterize existing logic with a Vitest harness before moving code.

## 🧱 Architectural Boundaries

### `src/core/` (The Shared Kernel)
*   **API Client:** `src/core/api/` (Handles tokens and axios/fetch setup).
*   **Authentication:** `src/core/auth/` (Login logic and user context).
*   **Theme:** `src/core/theme/` (Tailwind v4 themes and global CSS).
*   **Components:** `src/core/components/` (Base Layout, Buttons, Modals).

### `src/features/` (The Domains)
*   `rides/`: List, Summary, Detail views.
*   `coaching/`: The AI Coach panel and history.
*   `athlete/`: Settings, Profile, User Management.
*   `sync/`: Intervals.icu sync status and controls.

---

## 📋 Micro-Step Checklist

### 1. Preparation & Characterization
- [ ] **Step 1.1:** Initialize the **Vitest Harness**.
  - Add `vitest`, `@testing-library/react`, `jsdom` to `package.json`.
  - Create `vitest.setup.ts`.
- [ ] **Step 1.2:** Characterize the **API Client**.
  - Write a test ensuring `lib/api.ts` correctly appends auth headers.
- [ ] **Step 1.3:** Characterize the **Auth Flow**.
  - Write a test ensuring `lib/auth.tsx` provides the expected user state.

### 2. Core Migration
- [ ] **Step 2.1:** Move `lib/api.ts` to `core/api/index.ts`.
  - Fix all imports using global find/replace.
- [ ] **Step 2.2:** Move `lib/auth.tsx` to `core/auth/index.tsx`.
- [ ] **Step 2.3:** Move `lib/theme.tsx` and `lib/units.tsx` to `core/theme/`.

### 3. Feature Scaffolding
- [ ] **Step 3.1:** Scaffold **Rides Feature**.
  - Create `features/rides/`.
  - Move `pages/Rides.tsx`, `pages/Dashboard.tsx`, and `pages/Calendar.tsx`.
  - Export them from `features/rides/index.ts`.
- [ ] **Step 3.2:** Scaffold **Coaching Feature**.
  - Move `components/CoachPanel.tsx` to `features/coaching/`.
- [ ] **Step 3.3:** Scaffold **Athlete Feature**.
  - Move `pages/Settings.tsx`, `components/UserAvatar.tsx`, and `components/UserManagement.tsx`.

### 4. Integration & Routing
- [ ] **Step 4.1:** Update `App.tsx`.
  - Import all pages directly from their respective `features/` folders.
- [ ] **Step 4.2:** Final Audit.
  - Run `npm run lint` and `npm run build`.
  - Confirm all tests pass.

---

## 🎯 Verification Criteria
*   The `src/pages/` and `src/components/` folders are **deleted**.
*   `npm run build` succeeds with **zero** typescript errors.
*   The application UI is functionally identical to the pre-refactor state.
