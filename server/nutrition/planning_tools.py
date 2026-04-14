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

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
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
