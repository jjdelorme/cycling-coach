-- 0003_planned_meals.sql
-- Add planned_meals table for nutritionist-generated meal plans.
-- Also seeds default dietary preferences and nutritionist principles
-- into coach_settings.

CREATE TABLE IF NOT EXISTS planned_meals (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'athlete',
    date TEXT NOT NULL,
    meal_slot TEXT NOT NULL,  -- breakfast, lunch, dinner, snack_am, snack_pm, pre_workout, post_workout
    name TEXT NOT NULL,
    description TEXT,
    total_calories INTEGER NOT NULL,
    total_protein_g REAL NOT NULL,
    total_carbs_g REAL NOT NULL,
    total_fat_g REAL NOT NULL,
    items TEXT,               -- JSON array of food items
    agent_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_planned_meals_date ON planned_meals(date);
CREATE INDEX IF NOT EXISTS idx_planned_meals_user_date ON planned_meals(user_id, date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_planned_meals_slot ON planned_meals(user_id, date, meal_slot);

-- Seed default dietary preferences and nutritionist principles
INSERT INTO coach_settings (key, value) VALUES (
    'dietary_preferences',
    '- Diet type: [e.g., no restrictions, vegetarian, Mediterranean]
- Allergies: [e.g., none, tree nuts, shellfish]
- Intolerances: [e.g., lactose, gluten]
- Disliked foods: [e.g., liver, beets]
- Liked foods: [e.g., salmon, oatmeal, sweet potatoes]
- Eating schedule: [e.g., 3 meals + 2 snacks, intermittent fasting 16:8]
- Cooking ability: [e.g., enjoys cooking, prefers simple meals]
- Supplement use: [e.g., whey protein post-ride, electrolyte mix]'
) ON CONFLICT (key) DO NOTHING;

INSERT INTO coach_settings (key, value) VALUES (
    'nutritionist_principles',
    '- Periodize nutrition to match training load — more carbs on hard/long days, moderate on easy days
- Prioritize whole foods over supplements
- Pre-ride meals: easily digestible carbs 2-3h before, avoid high fat/fiber
- Post-ride: 3:1 carb:protein within 30 minutes of hard sessions
- On-bike fueling: 60-90g carbs/hour for rides > 90 minutes
- Rest day: maintain protein (1.6-2.0 g/kg), reduce total carbs
- Don''t over-restrict — chronic deficit impairs training adaptation'
) ON CONFLICT (key) DO NOTHING;
