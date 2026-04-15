"""Weight resolver — single source of truth for athlete weight on a given date.

Priority chain (each level carries forward the most recent value on or before `date`):
  1. body_measurements (Withings scale) — highest accuracy
  2. rides.weight — device-recorded weight from ride file
  3. athlete_settings (key='weight_kg') — manual entry
  4. 75.0 kg — hard default (logged as warning)
"""
import logging

logger = logging.getLogger(__name__)

DEFAULT_WEIGHT_KG = 75.0


def get_weight_for_date(conn, date: str) -> float:
    """Resolve the athlete's weight for a given date using the priority chain.

    Args:
        conn: Active psycopg2-style DB connection (supports .execute().fetchone()).
        date: ISO date string (YYYY-MM-DD).

    Returns:
        Weight in kg as float.
    """
    # 1. Withings body_measurements — most recent measurement on or before date
    row = conn.execute(
        "SELECT weight_kg FROM body_measurements WHERE date <= %s AND weight_kg IS NOT NULL "
        "ORDER BY date DESC LIMIT 1",
        (date,),
    ).fetchone()
    if row and row["weight_kg"]:
        return float(row["weight_kg"])

    # 2. Ride-recorded weight -- most recent ride on or before date
    from server.utils.dates import get_request_tz
    tz_name = str(get_request_tz())
    row = conn.execute(
        "SELECT weight FROM rides "
        "WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE <= %s::DATE "
        "AND weight IS NOT NULL AND weight > 0 "
        "ORDER BY start_time DESC LIMIT 1",
        (tz_name, date),
    ).fetchone()
    if row and row["weight"]:
        return float(row["weight"])

    # 3. Athlete settings — most recent manual entry on or before date
    row = conn.execute(
        "SELECT value FROM athlete_settings WHERE key = 'weight_kg' AND date_set <= %s "
        "ORDER BY date_set DESC LIMIT 1",
        (date,),
    ).fetchone()
    if row and row["value"]:
        try:
            val = float(row["value"])
            if val > 0:
                return val
        except (ValueError, TypeError):
            pass

    # 4. Default fallback
    logger.warning(
        "weight_resolver_using_default date=%s default_kg=%.1f "
        "reason=no weight found in body_measurements, rides, or athlete_settings",
        date,
        DEFAULT_WEIGHT_KG,
    )
    return DEFAULT_WEIGHT_KG


def get_current_weight(conn) -> float:
    """Convenience wrapper: resolve weight for today following the full priority chain."""
    from server.utils.dates import user_today
    return get_weight_for_date(conn, user_today())
