"""Write tools for the Nutritionist agent -- permission-gated at the agent level."""

from datetime import datetime, timezone
from server.database import get_db
from server.logging_config import get_logger

logger = get_logger(__name__)


def save_meal_analysis(
    meal_description: str,
    items: list[dict],
    total_calories: int,
    total_protein_g: float,
    total_carbs_g: float,
    total_fat_g: float,
    confidence: str,
    meal_type: str = "",
    photo_gcs_path: str = "",
    agent_notes: str = "",
) -> dict:
    """Save a meal analysis to the database after photo analysis.

    Call this tool after analyzing a meal photo. Provide the full itemized
    breakdown and macro totals.

    Args:
        meal_description: Brief natural language description (e.g., "Grilled chicken breast with brown rice and steamed broccoli").
        items: List of individual food items. Each dict must have:
            - name (str): Item name
            - serving_size (str): e.g., "6 oz", "1 cup", "200g"
            - calories (int)
            - protein_g (float)
            - carbs_g (float)
            - fat_g (float)
        total_calories: Sum of calories across all items.
        total_protein_g: Sum of protein across all items.
        total_carbs_g: Sum of carbs across all items.
        total_fat_g: Sum of fat across all items.
        confidence: "high", "medium", or "low".
        meal_type: Optional: "breakfast", "lunch", "dinner", "snack".
        photo_gcs_path: GCS path to the stored photo (set by the API layer).
        agent_notes: Optional nutritionist commentary about the meal.

    Returns:
        Saved meal record with id and timestamp.
    """
    # Validation
    if total_calories <= 0 or total_calories > 10000:
        return {"error": f"total_calories must be between 1 and 10000, got {total_calories}"}
    if total_protein_g < 0 or total_carbs_g < 0 or total_fat_g < 0:
        return {"error": "Macro values must be non-negative"}
    if confidence not in ("high", "medium", "low"):
        return {"error": f"confidence must be high/medium/low, got '{confidence}'"}
    if not items:
        return {"error": "items list must not be empty"}

    # Cross-check: macro calories vs total (log warning if >15% off, still save)
    macro_cal = round(total_protein_g * 4 + total_carbs_g * 4 + total_fat_g * 9)
    if total_calories > 0 and abs(macro_cal - total_calories) / total_calories > 0.15:
        logger.warning(
            "macro_calorie_mismatch",
            total_calories=total_calories,
            macro_derived_calories=macro_cal,
            difference_pct=round(abs(macro_cal - total_calories) / total_calories * 100, 1),
        )

    from server.utils.dates import user_today
    now = datetime.now(timezone.utc)
    date_str = user_today()
    logged_at = now.isoformat()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO meal_logs (user_id, date, logged_at, meal_type, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g, "
            "confidence, photo_gcs_path, agent_notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            ("athlete", date_str, logged_at, meal_type or None, meal_description,
             total_calories, total_protein_g, total_carbs_g, total_fat_g,
             confidence, photo_gcs_path or None, agent_notes or None),
        )
        row = conn.execute("SELECT lastval()").fetchone()
        meal_id = row["lastval"] if row else None

        # Insert individual items
        for item in items:
            conn.execute(
                "INSERT INTO meal_items (meal_id, name, serving_size, calories, "
                "protein_g, carbs_g, fat_g) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (meal_id, item.get("name", "Unknown"), item.get("serving_size"),
                 item.get("calories", 0), item.get("protein_g", 0),
                 item.get("carbs_g", 0), item.get("fat_g", 0)),
            )

    return {
        "status": "saved",
        "meal_id": meal_id,
        "date": date_str,
        "logged_at": logged_at,
        "description": meal_description,
        "total_calories": total_calories,
        "confidence": confidence,
        "items_count": len(items),
    }


def update_meal(
    meal_id: int,
    total_calories: int = 0,
    total_protein_g: float = 0.0,
    total_carbs_g: float = 0.0,
    total_fat_g: float = 0.0,
    meal_type: str = "",
) -> dict:
    """Update macro values on an existing meal (user corrections).

    Args:
        meal_id: The meal to update.
        total_calories: New calorie total (0 = no change).
        total_protein_g: New protein total (0 = no change).
        total_carbs_g: New carbs total (0 = no change).
        total_fat_g: New fat total (0 = no change).
        meal_type: New meal type (empty = no change).

    Returns:
        Status of the update.
    """
    updates = []
    params = []
    if total_calories > 0:
        updates.append("total_calories = %s")
        params.append(total_calories)
    if total_protein_g > 0:
        updates.append("total_protein_g = %s")
        params.append(total_protein_g)
    if total_carbs_g > 0:
        updates.append("total_carbs_g = %s")
        params.append(total_carbs_g)
    if total_fat_g > 0:
        updates.append("total_fat_g = %s")
        params.append(total_fat_g)
    if meal_type:
        updates.append("meal_type = %s")
        params.append(meal_type)

    if not updates:
        return {"error": "No values to update"}

    updates.append("edited_by_user = TRUE")
    params.append(meal_id)

    with get_db() as conn:
        conn.execute(
            f"UPDATE meal_logs SET {', '.join(updates)} WHERE id = %s",
            params,
        )

    return {"status": "updated", "meal_id": meal_id}


def delete_meal(meal_id: int) -> dict:
    """Delete a meal and its items from the database.

    Args:
        meal_id: The meal to delete.

    Returns:
        Confirmation of deletion.
    """
    with get_db() as conn:
        row = conn.execute("SELECT id, description FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            return {"error": f"Meal {meal_id} not found"}
        # meal_items cascade-deletes via FK
        conn.execute("DELETE FROM meal_logs WHERE id = %s", (meal_id,))

    return {"status": "deleted", "meal_id": meal_id}


def set_macro_targets(
    calories: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> dict:
    """Update the athlete's daily macro targets.

    Args:
        calories: Daily calorie target (must be > 0 and < 10000).
        protein_g: Daily protein target in grams (must be >= 0).
        carbs_g: Daily carbs target in grams (must be >= 0).
        fat_g: Daily fat target in grams (must be >= 0).

    Returns:
        Updated targets.
    """
    if calories <= 0 or calories > 10000:
        return {"error": f"calories must be between 1 and 10000, got {calories}"}
    if protein_g < 0 or carbs_g < 0 or fat_g < 0:
        return {"error": "Macro targets must be non-negative"}

    with get_db() as conn:
        conn.execute(
            "INSERT INTO macro_targets (user_id, calories, protein_g, carbs_g, fat_g, updated_at) "
            "VALUES ('athlete', %s, %s, %s, %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "calories = EXCLUDED.calories, protein_g = EXCLUDED.protein_g, "
            "carbs_g = EXCLUDED.carbs_g, fat_g = EXCLUDED.fat_g, "
            "updated_at = EXCLUDED.updated_at",
            (calories, protein_g, carbs_g, fat_g),
        )

    return {
        "status": "updated",
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
    }


ALLOWED_MEAL_SLOTS = {
    "breakfast", "lunch", "dinner",
    "snack_am", "snack_pm",
    "pre_workout", "post_workout",
}


def generate_meal_plan(meals: list[dict]) -> dict:
    """Batch-create planned meals for one or more days.

    The agent decides WHAT to prescribe based on athlete data (dietary
    preferences, training load, macro targets, body composition goals).
    This function just persists those decisions in a single DB transaction.

    Use this when planning a full day or multi-day meal plan. For a single
    slot swap, use replace_planned_meal instead.

    Each meal dict must contain:
        - date (str, required): YYYY-MM-DD
        - meal_slot (str, required): One of breakfast, lunch, dinner,
          snack_am, snack_pm, pre_workout, post_workout
        - name (str, required): Meal name (e.g., "Overnight Oats with Berries")
        - total_calories (int, required): 1-5000
        - total_protein_g (float, required): >= 0
        - total_carbs_g (float, required): >= 0
        - total_fat_g (float, required): >= 0
        - description (str, optional): Preparation notes, ingredients summary
        - items (list[dict], optional): Itemized food breakdown. Each item:
            - name (str), serving_size (str), calories (int),
              protein_g (float), carbs_g (float), fat_g (float)
        - agent_notes (str, optional): Nutritionist reasoning/context

    Args:
        meals: List of meal dicts as described above.

    Returns:
        Dict with created meals, skipped rest slots, and any errors.
    """
    import json

    created = []
    errors = []

    with get_db() as conn:
        for spec in meals:
            date = spec.get("date")
            meal_slot = spec.get("meal_slot", "")
            name = spec.get("name", "")

            if not date:
                errors.append({"error": "Missing 'date' field", "spec": spec})
                continue
            if meal_slot not in ALLOWED_MEAL_SLOTS:
                errors.append({
                    "date": date,
                    "error": f"Invalid meal_slot '{meal_slot}'. Must be one of: {', '.join(sorted(ALLOWED_MEAL_SLOTS))}",
                })
                continue
            if not name:
                errors.append({"date": date, "meal_slot": meal_slot, "error": "Missing 'name' field"})
                continue

            total_calories = spec.get("total_calories", 0)
            total_protein_g = spec.get("total_protein_g", 0)
            total_carbs_g = spec.get("total_carbs_g", 0)
            total_fat_g = spec.get("total_fat_g", 0)

            if total_calories < 1 or total_calories > 5000:
                errors.append({"date": date, "meal_slot": meal_slot, "error": f"total_calories must be 1-5000, got {total_calories}"})
                continue
            if total_protein_g < 0 or total_carbs_g < 0 or total_fat_g < 0:
                errors.append({"date": date, "meal_slot": meal_slot, "error": "Macro values must be non-negative"})
                continue

            description = spec.get("description", "")
            items = spec.get("items", [])
            agent_notes = spec.get("agent_notes", "")

            items_json = json.dumps(items) if items else None

            # DELETE-then-INSERT for the specific (user_id, date, meal_slot)
            conn.execute(
                "DELETE FROM planned_meals WHERE user_id = %s AND date = %s AND meal_slot = %s",
                ("athlete", date, meal_slot),
            )
            conn.execute(
                "INSERT INTO planned_meals "
                "(user_id, date, meal_slot, name, description, total_calories, "
                "total_protein_g, total_carbs_g, total_fat_g, items, agent_notes) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                ("athlete", date, meal_slot, name, description or None,
                 total_calories, total_protein_g, total_carbs_g, total_fat_g,
                 items_json, agent_notes or None),
            )
            created.append({
                "date": date,
                "meal_slot": meal_slot,
                "name": name,
                "total_calories": total_calories,
            })

    return {
        "status": "success" if not errors else "partial",
        "created": created,
        "errors": errors,
        "total_meals": len(created),
        "message": f"Created {len(created)} planned meal(s)" + (f", {len(errors)} error(s)" if errors else ""),
    }


def replace_planned_meal(
    date: str,
    meal_slot: str,
    name: str,
    total_calories: int,
    total_protein_g: float,
    total_carbs_g: float,
    total_fat_g: float,
    description: str = "",
    items: list[dict] = [],
    agent_notes: str = "",
) -> dict:
    """Replace or create a single planned meal slot.

    Use this when swapping one meal without touching the rest of the day's
    plan. For batch planning, use generate_meal_plan instead.

    Args:
        date: Date (YYYY-MM-DD).
        meal_slot: One of breakfast, lunch, dinner, snack_am, snack_pm,
            pre_workout, post_workout.
        name: Meal name (e.g., "Grilled Salmon with Quinoa").
        total_calories: Calorie total (1-5000).
        total_protein_g: Protein in grams (>= 0).
        total_carbs_g: Carbs in grams (>= 0).
        total_fat_g: Fat in grams (>= 0).
        description: Preparation notes, ingredients summary.
        items: Itemized food breakdown. Each item:
            - name (str), serving_size (str), calories (int),
              protein_g (float), carbs_g (float), fat_g (float)
        agent_notes: Nutritionist reasoning/context.

    Returns:
        Details of the new planned meal, or error.
    """
    import json

    if meal_slot not in ALLOWED_MEAL_SLOTS:
        return {"status": "error", "message": f"Invalid meal_slot '{meal_slot}'. Must be one of: {', '.join(sorted(ALLOWED_MEAL_SLOTS))}"}
    if total_calories < 1 or total_calories > 5000:
        return {"status": "error", "message": f"total_calories must be 1-5000, got {total_calories}"}
    if total_protein_g < 0 or total_carbs_g < 0 or total_fat_g < 0:
        return {"status": "error", "message": "Macro values must be non-negative"}

    items_json = json.dumps(items) if items else None

    with get_db() as conn:
        previous = conn.execute(
            "SELECT name FROM planned_meals WHERE user_id = %s AND date = %s AND meal_slot = %s",
            ("athlete", date, meal_slot),
        ).fetchone()

        conn.execute(
            "DELETE FROM planned_meals WHERE user_id = %s AND date = %s AND meal_slot = %s",
            ("athlete", date, meal_slot),
        )
        conn.execute(
            "INSERT INTO planned_meals "
            "(user_id, date, meal_slot, name, description, total_calories, "
            "total_protein_g, total_carbs_g, total_fat_g, items, agent_notes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            ("athlete", date, meal_slot, name, description or None,
             total_calories, total_protein_g, total_carbs_g, total_fat_g,
             items_json, agent_notes or None),
        )

    return {
        "status": "success",
        "date": date,
        "meal_slot": meal_slot,
        "action": "replaced" if previous else "created",
        "previous_meal": previous["name"] if previous else None,
        "new_meal": name,
        "total_calories": total_calories,
    }


def clear_meal_plan(date: str, meal_slot: str = "") -> dict:
    """Remove planned meals for a date, or a specific slot on that date.

    Args:
        date: Date (YYYY-MM-DD).
        meal_slot: Optional. If provided, only clears that slot.
            If empty, clears all planned meals for the date.

    Returns:
        Confirmation with count of removed meals.
    """
    if meal_slot and meal_slot not in ALLOWED_MEAL_SLOTS:
        return {"status": "error", "message": f"Invalid meal_slot '{meal_slot}'. Must be one of: {', '.join(sorted(ALLOWED_MEAL_SLOTS))}"}

    with get_db() as conn:
        if meal_slot:
            result = conn.execute(
                "DELETE FROM planned_meals WHERE user_id = %s AND date = %s AND meal_slot = %s",
                ("athlete", date, meal_slot),
            )
        else:
            result = conn.execute(
                "DELETE FROM planned_meals WHERE user_id = %s AND date = %s",
                ("athlete", date),
            )
        removed = result.rowcount

    return {
        "status": "success",
        "date": date,
        "meal_slot": meal_slot or "all",
        "removed": removed,
        "message": f"Removed {removed} planned meal(s) from {date}" + (f" ({meal_slot})" if meal_slot else ""),
    }


def update_dietary_preferences(section: str, new_value: str) -> dict:
    """Update the athlete's dietary preferences or nutritionist principles.

    Use this when the athlete reports changes to their diet, allergies,
    food preferences, or when adjusting nutritionist guiding principles.

    Args:
        section: Which setting to update. One of: 'dietary_preferences',
            'nutritionist_principles'.
        new_value: The full new value for that section. Use bullet points
            starting with '- '.

    Returns:
        Status of the update.
    """
    from server.database import set_setting

    valid_sections = {"dietary_preferences", "nutritionist_principles"}
    if section not in valid_sections:
        return {"status": "error", "message": f"Invalid section '{section}'. Must be one of: {', '.join(sorted(valid_sections))}"}

    set_setting(section, new_value)

    return {
        "status": "success",
        "section": section,
        "message": f"Updated {section.replace('_', ' ')}. Changes will be reflected in future meal planning.",
    }


def ask_clarification(question: str, context: str = "") -> dict:
    """Request clarification from the user about an ambiguous meal photo.

    Call this when confidence is low and you need more information before saving.
    The question will be displayed to the user as a follow-up prompt.

    Args:
        question: Specific question to ask (e.g., "Is that grilled chicken or tofu?").
        context: What you're uncertain about.

    Returns:
        The question echoed back for display to the user.
    """
    return {
        "status": "clarification_needed",
        "question": question,
        "context": context,
    }
