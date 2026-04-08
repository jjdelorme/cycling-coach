"""Generate ZWO workout files from database templates or custom step definitions."""

import json
import xml.etree.ElementTree as ET
from xml.dom import minidom

from server.logging_config import get_logger

logger = get_logger(__name__)


def get_template(key):
    """Look up a workout template by key from the database.

    Returns dict with: key, name, description, category, steps (parsed from JSON), source.
    Returns None if not found.
    """
    from server.database import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM workout_templates WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    t = dict(row)
    t["steps"] = json.loads(t["steps"])
    return t


def list_templates():
    """List all workout templates from the database.

    Returns list of dicts with: id, key, name, description, category, source, created_at.
    Steps are parsed from JSON.
    """
    from server.database import get_db
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM workout_templates ORDER BY category, name"
        ).fetchall()
    results = []
    for row in rows:
        t = dict(row)
        t["steps"] = json.loads(t["steps"])
        results.append(t)
    return results


def _build_zwo_xml(name, description, steps, ftp, duration_minutes=None):
    """Build ZWO XML from a list of step dicts.

    Steps use the unified format:
    - Warmup/Cooldown: duration_seconds, power_low, power_high
    - SteadyState: duration_seconds (None = fill remaining time), power
    - Intervals: repeat, on_duration_seconds, off_duration_seconds, on_power, off_power
    """
    root = ET.Element("workout_file")
    ET.SubElement(root, "author").text = "Cycling Coach"
    ET.SubElement(root, "name").text = name
    ET.SubElement(root, "description").text = (description or "") + f"\nFTP: {ftp}w"
    ET.SubElement(root, "sportType").text = "bike"

    workout = ET.SubElement(root, "workout")

    for step in steps:
        stype = step["type"].lower()

        if stype in ("intervals", "intervalst", "interval"):
            el = ET.SubElement(workout, "IntervalsT")
            el.set("Repeat", str(step.get("repeat", step.get("Repeat", 1))))
            el.set("OnDuration", str(step.get("on_duration_seconds", step.get("on_duration", 0))))
            el.set("OffDuration", str(step.get("off_duration_seconds", step.get("off_duration", 0))))
            el.set("OnPower", str(step.get("on_power", 1.0)))
            el.set("OffPower", str(step.get("off_power", 0.5)))
        elif stype in ("warmup", "cooldown"):
            # Zwift requires capitalized tag names for these
            tag = "Warmup" if stype == "warmup" else "Cooldown"
            el = ET.SubElement(workout, tag)
            el.set("Duration", str(step.get("duration_seconds", step.get("duration", 0))))
            el.set("PowerLow", str(step.get("power_low", 0.4)))
            el.set("PowerHigh", str(step.get("power_high", 0.65)))
        elif stype in ("steadystate", "recovery", "rest", "tempo", "threshold", "endurance", "z2", "z3", "z4", "z5"):
            el = ET.SubElement(workout, "SteadyState")
            dur = step.get("duration_seconds", step.get("duration"))
            if dur is None and duration_minutes:
                # Fill remaining time (subtract warmup/cooldown)
                dur = duration_minutes * 60 - 900
                if dur < 60:
                    dur = 60
            elif dur is None:
                dur = 1800  # default 30min
            el.set("Duration", str(dur))
            el.set("Power", str(step.get("power", 0.65)))
        else:
            logger.warning("unknown_step_type", step_type=stype)

    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    lines = xml_str.split("\n")
    if lines[0].startswith("<?xml"):
        xml_str = "\n".join(lines[1:])

    return xml_str.strip()


def generate_zwo(template_key, duration_minutes=60, ftp=0):
    """Generate a ZWO XML string from a database template.

    Args:
        template_key: Key from workout_templates table.
        duration_minutes: Target duration for endurance/recovery workouts.
        ftp: Current FTP.

    Returns:
        Tuple of (xml_string, workout_name)
    """
    tmpl = get_template(template_key)
    if not tmpl:
        raise ValueError(f"Unknown workout template: {template_key}")

    xml_str = _build_zwo_xml(tmpl["name"], tmpl["description"], tmpl["steps"], ftp, duration_minutes)
    return xml_str, tmpl["name"]


def generate_custom_zwo(name, description, steps, ftp=0):
    """Generate a ZWO XML string from custom step definitions.

    Args:
        name: Workout name.
        description: Coaching notes.
        steps: List of step dicts (see _build_zwo_xml for format).
        ftp: Current FTP.

    Returns:
        Tuple of (xml_string, workout_name)
    """
    xml_str = _build_zwo_xml(name, description, steps, ftp)
    return xml_str, name


def calculate_planned_tss(workout_xml: str) -> float | None:
    """Calculate planned TSS from ZWO workout XML.

    TSS = sum(step_duration_s * power_pct^2) / 3600 * 100

    For each step type:
    - SteadyState: duration * power^2
    - Warmup/Cooldown: duration * avg(power_low, power_high)^2
    - IntervalsT: repeat * (on_dur * on_power^2 + off_dur * off_power^2)
    """
    if not workout_xml:
        return None

    try:
        root = ET.fromstring(workout_xml)
    except ET.ParseError:
        logger.warning("workout_xml_parse_failed")
        return None

    workout_el = root.find("workout")
    if workout_el is None:
        return None

    weighted_seconds = 0.0  # sum of duration_s * power_pct^2

    for step in workout_el:
        tag = step.tag

        if tag == "SteadyState":
            dur = float(step.get("Duration", 0))
            power = float(step.get("Power", 0.65))
            weighted_seconds += dur * power * power

        elif tag in ("Warmup", "Cooldown"):
            dur = float(step.get("Duration", 0))
            p_low = float(step.get("PowerLow", 0.4))
            p_high = float(step.get("PowerHigh", 0.65))
            avg_power = (p_low + p_high) / 2
            weighted_seconds += dur * avg_power * avg_power

        elif tag == "IntervalsT" or tag == "Intervals":
            repeats = int(step.get("Repeat", 1))
            on_dur = float(step.get("OnDuration", 0))
            off_dur = float(step.get("OffDuration", 0))
            on_power = float(step.get("OnPower", 1.0))
            off_power = float(step.get("OffPower", 0.5))
            weighted_seconds += repeats * (
                on_dur * on_power * on_power + off_dur * off_power * off_power
            )
        else:
            logger.warning("unknown_workout_tag", tag=tag)

    if weighted_seconds <= 0:
        return None

    tss = weighted_seconds / 3600 * 100
    return round(tss, 1)
