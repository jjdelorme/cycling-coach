"""Read-only ADK tools for the Nutritionist agent to query meal and training data."""

from datetime import datetime, timedelta
from server.database import get_db, get_all_athlete_settings
from server.queries import get_meals_for_date, get_meal_items, get_macro_targets, get_daily_meal_totals


def get_meal_history(days_back: int = 7) -> list[dict]:
    """Get recent meal history with macros and timestamps.

    Args:
        days_back: Number of days to look back. Default 7.

    Returns:
        List of meal records with date, description, macros, and confidence.
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, date, logged_at, meal_type, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g, "
            "confidence, edited_by_user "
            "FROM meal_logs WHERE date >= %s AND user_id = %s ORDER BY date DESC, logged_at DESC",
            (cutoff, "athlete"),
        ).fetchall()

    return [dict(r) for r in rows]


def get_daily_macros(date: str = "") -> dict:
    """Get the aggregate macronutrient totals for a specific day.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today if empty.

    Returns:
        Daily macro summary including totals, targets, remaining, and per-meal breakdown.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        meals = conn.execute(
            "SELECT id, logged_at, meal_type, description, "
            "total_calories, total_protein_g, total_carbs_g, total_fat_g, confidence "
            "FROM meal_logs WHERE date = %s AND user_id = %s ORDER BY logged_at",
            (date, "athlete"),
        ).fetchall()

        targets = get_macro_targets(conn)

    total_cal = sum(m["total_calories"] for m in meals)
    total_p = sum(m["total_protein_g"] for m in meals)
    total_c = sum(m["total_carbs_g"] for m in meals)
    total_f = sum(m["total_fat_g"] for m in meals)

    return {
        "date": date,
        "total_calories": total_cal,
        "total_protein_g": round(total_p, 1),
        "total_carbs_g": round(total_c, 1),
        "total_fat_g": round(total_f, 1),
        "target_calories": targets["calories"],
        "target_protein_g": targets["protein_g"],
        "target_carbs_g": targets["carbs_g"],
        "target_fat_g": targets["fat_g"],
        "remaining_calories": targets["calories"] - total_cal,
        "remaining_protein_g": round(targets["protein_g"] - total_p, 1),
        "meals": [dict(m) for m in meals],
        "meal_count": len(meals),
    }


def get_weekly_summary(date: str = "") -> dict:
    """Get a 7-day nutrition summary with daily breakdown and weekly averages.

    Args:
        date: Any date in the target week (YYYY-MM-DD). Defaults to today. Week is Mon-Sun.

    Returns:
        Weekly averages and per-day totals.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    dt = datetime.fromisoformat(date)
    start = dt - timedelta(days=dt.weekday())
    end = start + timedelta(days=6)

    days = []
    with get_db() as conn:
        for i in range(7):
            day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            totals = get_daily_meal_totals(conn, day)
            # Get ride calories for this day
            ride_row = conn.execute(
                "SELECT COALESCE(SUM(total_calories), 0) AS ride_cal "
                "FROM rides WHERE date = %s",
                (day,),
            ).fetchone()
            totals["date"] = day
            totals["calories_out_rides"] = int(ride_row["ride_cal"]) if ride_row else 0
            days.append(totals)

    days_with_meals = [d for d in days if d["meal_count"] > 0]
    n = len(days_with_meals) or 1

    return {
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": end.strftime("%Y-%m-%d"),
        "avg_daily_calories": round(sum(d["calories"] for d in days_with_meals) / n),
        "avg_daily_protein_g": round(sum(d["protein_g"] for d in days_with_meals) / n, 1),
        "avg_daily_carbs_g": round(sum(d["carbs_g"] for d in days_with_meals) / n, 1),
        "avg_daily_fat_g": round(sum(d["fat_g"] for d in days_with_meals) / n, 1),
        "days": days,
    }


def get_caloric_balance(date: str = "") -> dict:
    """Get caloric intake vs estimated expenditure for a day.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.

    Returns:
        Intake, ride expenditure, estimated BMR, total expenditure, and net balance.
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    from server.services.weight import get_weight_for_date
    with get_db() as conn:
        totals = get_daily_meal_totals(conn, date)
        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s",
            (date,),
        ).fetchone()
        ride_cal = int(ride_row["total"]) if ride_row else 0
        weight_kg = get_weight_for_date(conn, date)

    bmr = _estimate_daily_bmr(weight_kg)
    total_out = ride_cal + bmr

    return {
        "date": date,
        "intake": int(totals["calories"]),
        "rides": ride_cal,
        "estimated_bmr": bmr,
        "total_expenditure": total_out,
        "net_balance": int(totals["calories"]) - total_out,
    }


def get_macro_targets_tool() -> dict:
    """Get the athlete's current daily macro targets.

    Returns:
        Daily targets for calories, protein, carbs, and fat.
    """
    with get_db() as conn:
        return get_macro_targets(conn)


def get_upcoming_training_load(days_ahead: int = 3) -> dict:
    """Get upcoming planned workouts and training load for fueling guidance.

    Args:
        days_ahead: Number of days to look ahead. Default 3.

    Returns:
        Planned workouts with date, name, TSS, duration, and estimated calories.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, name, total_duration_s, planned_tss, coach_notes "
            "FROM planned_workouts WHERE date >= %s AND date <= %s ORDER BY date",
            (today, end),
        ).fetchall()

    days = []
    for r in rows:
        tss = float(r["planned_tss"] or 0)
        duration_h = (r["total_duration_s"] or 0) / 3600
        # Rough calorie estimate from duration (500-700 kcal/hr for cycling)
        est_cal = round(duration_h * 600) if duration_h > 0 else 0
        days.append({
            "date": r["date"],
            "name": r["name"],
            "planned_tss": round(tss),
            "duration_h": round(duration_h, 1),
            "estimated_calories": est_cal,
            "coach_notes": r["coach_notes"],
        })

    return {
        "days": days,
        "total_planned_tss": sum(d["planned_tss"] for d in days),
        "total_estimated_calories": sum(d["estimated_calories"] for d in days),
    }


def get_recent_workouts(days_back: int = 3) -> list[dict]:
    """Get recent completed ride summaries for nutritional context.

    Args:
        days_back: Number of days to look back. Default 3.

    Returns:
        List of ride summaries with TSS, duration, and calories burned.
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, sub_sport, duration_s, tss, total_calories, "
            "avg_power, normalized_power "
            "FROM rides WHERE date >= %s ORDER BY date DESC",
            (cutoff,),
        ).fetchall()

    return [
        {
            "date": r["date"],
            "sport": r["sub_sport"],
            "duration_h": round((r["duration_s"] or 0) / 3600, 1),
            "tss": r["tss"],
            "calories_burned": r["total_calories"] or 0,
            "avg_power": r["avg_power"],
            "normalized_power": r["normalized_power"],
        }
        for r in rows
    ]


def get_planned_meals(date: str = "", days_ahead: int = 7) -> dict:
    """Get planned meals for a date range, organized by day and slot.

    Args:
        date: Start date (YYYY-MM-DD). Defaults to today.
        days_ahead: Number of days to include. Default 7.

    Returns:
        Dictionary with planned meals organized by date, each date containing
        its meal slots with name, macros, description, and items.
    """
    import json

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    start = datetime.fromisoformat(date)
    end = start + timedelta(days=days_ahead - 1)
    end_str = end.strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, meal_slot, name, description, total_calories, "
            "total_protein_g, total_carbs_g, total_fat_g, items, agent_notes "
            "FROM planned_meals WHERE user_id = %s AND date >= %s AND date <= %s "
            "ORDER BY date, meal_slot",
            ("athlete", date, end_str),
        ).fetchall()

    # Organize by date
    days = {}
    for r in rows:
        d = r["date"]
        if d not in days:
            days[d] = {"date": d, "meals": [], "day_calories": 0, "day_protein_g": 0, "day_carbs_g": 0, "day_fat_g": 0}
        items_parsed = []
        if r["items"]:
            try:
                items_parsed = json.loads(r["items"])
            except (json.JSONDecodeError, TypeError):
                pass
        days[d]["meals"].append({
            "meal_slot": r["meal_slot"],
            "name": r["name"],
            "description": r["description"],
            "total_calories": r["total_calories"],
            "total_protein_g": round(r["total_protein_g"], 1),
            "total_carbs_g": round(r["total_carbs_g"], 1),
            "total_fat_g": round(r["total_fat_g"], 1),
            "items": items_parsed,
            "agent_notes": r["agent_notes"],
        })
        days[d]["day_calories"] += r["total_calories"]
        days[d]["day_protein_g"] += r["total_protein_g"]
        days[d]["day_carbs_g"] += r["total_carbs_g"]
        days[d]["day_fat_g"] += r["total_fat_g"]

    # Round daily totals
    for d in days.values():
        d["day_protein_g"] = round(d["day_protein_g"], 1)
        d["day_carbs_g"] = round(d["day_carbs_g"], 1)
        d["day_fat_g"] = round(d["day_fat_g"], 1)

    return {
        "start_date": date,
        "end_date": end_str,
        "days": list(days.values()),
        "total_days_with_plans": len(days),
    }


def get_dietary_preferences() -> dict:
    """Get the athlete's dietary preferences and nutritionist principles.

    Returns:
        Dictionary with dietary_preferences and nutritionist_principles text.
    """
    from server.database import get_setting

    return {
        "dietary_preferences": get_setting("dietary_preferences"),
        "nutritionist_principles": get_setting("nutritionist_principles"),
    }


def _estimate_daily_bmr(weight_kg: float = 0) -> int:
    """Estimate BMR from athlete settings using Mifflin-St Jeor equation.

    Args:
        weight_kg: Weight in kg. If 0 or not provided, falls back to athlete_settings.
    """
    settings = get_all_athlete_settings()
    try:
        if weight_kg <= 0:
            weight_kg = float(settings.get("weight_kg", 0))
        age = int(settings.get("age", 0))
        gender = settings.get("gender", "").lower()
    except (ValueError, TypeError):
        return 1750

    if weight_kg <= 0 or age <= 0:
        return 1750

    if gender == "male":
        bmr = 10 * weight_kg + 6.25 * 175 - 5 * age + 5
    elif gender == "female":
        bmr = 10 * weight_kg + 6.25 * 165 - 5 * age - 161
    else:
        bmr = 10 * weight_kg + 6.25 * 170 - 5 * age - 78

    return round(bmr * 1.2)  # Sedentary multiplier; exercise added separately
