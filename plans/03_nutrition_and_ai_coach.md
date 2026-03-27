# Plan 03: Nutrition & Multimodal AI Coach

This campaign integrates meal tracking and nutritional analysis directly into the ADK Agent (AI Coach), allowing the athlete to manage their whole life through the coaching interface.

## 🥅 Objective
*   Implement a **Nutrition Database** (Backend schema + REST API).
*   Implement the **Macro Dashboard** (Frontend UI).
*   Extend the **AI Coach** with Multimodal support (Gemini Vision) and Nutrition Tools.

## 🧱 Key Features

### Meal Analysis via Photo
*   **Coach Chat:** Upload a photo of a meal.
*   **Gemini Vision:** Analyze the photo for macronutrients.
*   **Auto-Logging:** The agent uses a tool to log the analysis directly into the DB.

### Holistic Coaching Loop (Energy Balance)
*   **Intake vs. Expenditure:** The AI Coach compares calories consumed (Nutrition) with calories burned (Rides).
*   **Advice:** Provides recommendations on fueling and recovery based on actual data.

---

## 📋 Micro-Step Checklist

### 1. Nutrition Backend Foundation
- [ ] **Step 1.1:** Database schema for `nutrition_logs`.
  - Table: `id, user_id, timestamp, name, image_url, calories, protein, carbs, fat, source (manual/ai)`.
- [ ] **Step 1.2:** Backend Router: `server/routers/nutrition.py`.
  - `POST /meals`: Log a meal.
  - `GET /nutrition/summary/{date}`: Daily totals.
- [ ] **Step 1.3:** Integration with existing `Rides` domain to calculate "Net Energy Balance".

### 2. Macro Dashboard (UI)
- [ ] **Step 2.1:** Scaffold `src/features/nutrition/`.
- [ ] **Step 2.2:** Build the `<MacroDashboard />`.
  - Use `react-chartjs-2` to visualize daily macros against goals.
- [ ] **Step 2.3:** Add "Nutrition" tab to `Layout.tsx` and wire routing.

### 3. Multimodal AI Coach (Multimodal Port)
- [ ] **Step 3.1:** Implement `server/coaching/nutrition_tools.py`.
  - `analyze_meal_photo(image_bytes)`: Uses Gemini 1.5/2.0 to extract macros.
  - `log_macros(calories, protein, carbs, fat, name)`.
  - `get_energy_balance(date)`.
- [ ] **Step 3.2:** Upgrade `CoachPanel.tsx`.
  - Add image upload button.
  - Update chat API to handle `multipart/form-data`.
- [ ] **Step 3.3:** Update `server/routers/coaching.py`.
  - Handle image file uploads and pass to the `chat` service.

### 4. Holistic Tooling
- [ ] **Step 4.1:** Register all nutrition tools in `server/coaching/agent.py`.
- [ ] **Step 4.2:** Update Agent System Instruction to include Nutrition expertise.

---

## 🎯 Verification Criteria
*   The athlete can successfully **upload a photo** in the coach chat.
*   The **AI Coach** correctly identifies the food and estimated macros.
*   The logged macros appear immediately in the **Macro Dashboard**.
*   The AI Coach can answer questions about **Energy Balance** (e.g., "Did I eat enough for today's ride?").
