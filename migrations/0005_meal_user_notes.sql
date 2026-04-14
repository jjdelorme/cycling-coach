-- 0005_meal_user_notes.sql
-- Add user_notes column to meal_logs so users can save personal notes on meals.

ALTER TABLE meal_logs ADD COLUMN IF NOT EXISTS user_notes TEXT;
