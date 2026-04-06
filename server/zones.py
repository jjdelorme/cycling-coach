"""Canonical zone definitions for power and heart rate analysis.

Single source of truth — import from here, never redefine zones elsewhere.
Zone boundaries follow the Coggan 6-zone power model and Friel 5-zone HR model.
"""

# Power zones: (zone_id, label, range_str, lower_fraction, upper_fraction)
# Fractions are of FTP. upper_fraction=inf means no upper bound.
POWER_ZONES = [
    ("Z1", "Active Recovery", "<55%",    0.00,  0.55),
    ("Z2", "Endurance",       "55-75%",  0.55,  0.75),
    ("Z3", "Tempo",           "75-90%",  0.75,  0.90),
    ("Z4", "Threshold",       "90-105%", 0.90,  1.05),
    ("Z5", "VO2max",          "105-120%",1.05,  1.20),
    ("Z6", "Anaerobic",       ">120%",   1.20,  float("inf")),
]

# HR zones: (zone_id, label, range_str, lower_fraction, upper_fraction)
# Fractions are of LTHR.
HR_ZONES = [
    ("Z1", "Recovery",  "<81%",   0.00, 0.81),
    ("Z2", "Aerobic",   "81-89%", 0.81, 0.89),
    ("Z3", "Tempo",     "89-93%", 0.89, 0.93),
    ("Z4", "Threshold", "93-99%", 0.93, 0.99),
    ("Z5", "VO2max",    ">99%",   0.99, float("inf")),
]


def power_zone_label(ftp_fraction: float) -> str:
    """Return a human-readable zone label for a given fraction of FTP.

    Args:
        ftp_fraction: Power as a fraction of FTP (e.g., 0.85 = 85% FTP).

    Returns:
        Zone label string like "Z3 Tempo" or "Z6 Anaerobic".
    """
    for zone_id, label, _, lo, hi in POWER_ZONES:
        if lo <= ftp_fraction < hi:
            return f"{zone_id} {label}"
    return "Z6 Anaerobic"


def compute_power_zones(powers: list, ftp: int) -> dict:
    """Compute power zone distribution from per-second power data.

    Args:
        powers: List of per-second power values (watts). None or 0 = coasting.
        ftp: Athlete's FTP in watts.

    Returns:
        Dict with ftp_used, zones list, and coasting_seconds.
    """
    counts = {z[0]: 0 for z in POWER_ZONES}
    coasting = 0
    total = 0
    for p in powers:
        if p is None or p == 0:
            coasting += 1
            continue
        total += 1
        for zone_id, _, _, lo, hi in POWER_ZONES:
            if ftp * lo <= p < ftp * hi:
                counts[zone_id] += 1
                break

    zones = []
    for zone_id, label, rng, _, _ in POWER_ZONES:
        secs = counts[zone_id]
        pct = round(100 * secs / total, 1) if total > 0 else 0
        zones.append({"zone": zone_id, "label": label, "range": rng, "seconds": secs, "pct": pct})

    return {"ftp_used": ftp, "zones": zones, "coasting_seconds": coasting}


def compute_hr_zones(heart_rates: list, lthr: int) -> dict | None:
    """Compute HR zone distribution from per-second heart rate data.

    Args:
        heart_rates: List of per-second HR values (bpm). None or 0 = invalid.
        lthr: Athlete's lactate threshold heart rate in bpm.

    Returns:
        Dict with lthr_used and zones list, or None if lthr is 0 or no valid data.
    """
    if not lthr or lthr <= 0:
        return None

    counts = {z[0]: 0 for z in HR_ZONES}
    total = 0
    for hr in heart_rates:
        if hr is None or hr == 0:
            continue
        total += 1
        for zone_id, _, _, lo, hi in HR_ZONES:
            if lthr * lo <= hr < lthr * hi:
                counts[zone_id] += 1
                break

    if total == 0:
        return None

    zones = []
    for zone_id, label, rng, _, _ in HR_ZONES:
        secs = counts[zone_id]
        pct = round(100 * secs / total, 1) if total > 0 else 0
        zones.append({"zone": zone_id, "label": label, "range": rng, "seconds": secs, "pct": pct})

    return {"lthr_used": lthr, "zones": zones}
