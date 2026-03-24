"""Generate ZWO workout files based on current FTP."""

import xml.etree.ElementTree as ET
from xml.dom import minidom

WORKOUT_TEMPLATES = {
    "z2_endurance": {
        "name": "Z2 Endurance",
        "description": "Steady aerobic endurance ride. Keep power in Z2 (65-75% FTP).",
        "intervals": [
            {"type": "Warmup", "duration": 600, "power_low": 0.40, "power_high": 0.65},
            {"type": "SteadyState", "duration": None, "power": 0.65},  # duration set by caller
            {"type": "Cooldown", "duration": 300, "power_low": 0.65, "power_high": 0.40},
        ],
    },
    "threshold_2x20": {
        "name": "2x20 Threshold",
        "description": "Two 20-minute intervals at FTP. Key workout for building sustained power.",
        "intervals": [
            {"type": "Warmup", "duration": 600, "power_low": 0.40, "power_high": 0.75},
            {"type": "SteadyState", "duration": 1200, "power": 1.00},
            {"type": "SteadyState", "duration": 300, "power": 0.50},
            {"type": "SteadyState", "duration": 1200, "power": 1.00},
            {"type": "Cooldown", "duration": 600, "power_low": 0.65, "power_high": 0.40},
        ],
    },
    "sweetspot_3x15": {
        "name": "3x15 Sweet Spot",
        "description": "Three 15-minute intervals at 88-93% FTP. High training stress with manageable fatigue.",
        "intervals": [
            {"type": "Warmup", "duration": 600, "power_low": 0.40, "power_high": 0.75},
            {"type": "SteadyState", "duration": 900, "power": 0.90},
            {"type": "SteadyState", "duration": 300, "power": 0.50},
            {"type": "SteadyState", "duration": 900, "power": 0.90},
            {"type": "SteadyState", "duration": 300, "power": 0.50},
            {"type": "SteadyState", "duration": 900, "power": 0.90},
            {"type": "Cooldown", "duration": 600, "power_low": 0.65, "power_high": 0.40},
        ],
    },
    "vo2max_4x4": {
        "name": "4x4min VO2max",
        "description": "Four 4-minute intervals at 115-120% FTP. Builds aerobic ceiling.",
        "intervals": [
            {"type": "Warmup", "duration": 600, "power_low": 0.40, "power_high": 0.75},
            {"type": "IntervalsT", "repeat": 4, "on_duration": 240, "off_duration": 240, "on_power": 1.18, "off_power": 0.50},
            {"type": "Cooldown", "duration": 600, "power_low": 0.65, "power_high": 0.40},
        ],
    },
    "race_simulation": {
        "name": "Race Simulation",
        "description": "Variable-terrain simulation with surges. Mimics MTB race demands.",
        "intervals": [
            {"type": "Warmup", "duration": 600, "power_low": 0.40, "power_high": 0.65},
            {"type": "SteadyState", "duration": 600, "power": 0.75},
            {"type": "SteadyState", "duration": 180, "power": 1.10},
            {"type": "SteadyState", "duration": 300, "power": 0.65},
            {"type": "SteadyState", "duration": 240, "power": 1.15},
            {"type": "SteadyState", "duration": 600, "power": 0.70},
            {"type": "SteadyState", "duration": 300, "power": 1.05},
            {"type": "SteadyState", "duration": 300, "power": 0.55},
            {"type": "SteadyState", "duration": 180, "power": 1.20},
            {"type": "SteadyState", "duration": 600, "power": 0.65},
            {"type": "Cooldown", "duration": 300, "power_low": 0.65, "power_high": 0.40},
        ],
    },
    "recovery": {
        "name": "Recovery Spin",
        "description": "Easy recovery ride. Keep it in Z1, legs spinning, no effort.",
        "intervals": [
            {"type": "SteadyState", "duration": None, "power": 0.45},
        ],
    },
}


def generate_zwo(workout_type, duration_minutes=60, ftp=261):
    """Generate a ZWO XML string for the given workout type.

    Args:
        workout_type: Key from WORKOUT_TEMPLATES
        duration_minutes: Target duration for endurance/recovery workouts
        ftp: Current FTP (used in description, not in ZWO power which is FTP-relative)

    Returns:
        Tuple of (xml_string, workout_name)
    """
    template = WORKOUT_TEMPLATES.get(workout_type)
    if not template:
        raise ValueError(f"Unknown workout type: {workout_type}. Available: {list(WORKOUT_TEMPLATES.keys())}")

    root = ET.Element("workout_file")
    ET.SubElement(root, "author").text = "Cycling Coach"
    ET.SubElement(root, "name").text = template["name"]
    ET.SubElement(root, "description").text = template["description"] + f"\nFTP: {ftp}w"
    ET.SubElement(root, "sportType").text = "bike"

    workout = ET.SubElement(root, "workout")

    for interval in template["intervals"]:
        itype = interval["type"]

        if itype == "IntervalsT":
            el = ET.SubElement(workout, "IntervalsT")
            el.set("Repeat", str(interval["repeat"]))
            el.set("OnDuration", str(interval["on_duration"]))
            el.set("OffDuration", str(interval["off_duration"]))
            el.set("OnPower", str(interval["on_power"]))
            el.set("OffPower", str(interval["off_power"]))
        elif itype in ("Warmup", "Cooldown"):
            el = ET.SubElement(workout, itype)
            el.set("Duration", str(interval["duration"]))
            el.set("PowerLow", str(interval["power_low"]))
            el.set("PowerHigh", str(interval["power_high"]))
        else:  # SteadyState
            el = ET.SubElement(workout, "SteadyState")
            duration = interval["duration"] or (duration_minutes * 60 - 900)  # subtract warmup/cooldown
            if duration < 60:
                duration = 60
            el.set("Duration", str(duration))
            el.set("Power", str(interval["power"]))

    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    # Remove XML declaration
    lines = xml_str.split("\n")
    if lines[0].startswith("<?xml"):
        xml_str = "\n".join(lines[1:])

    return xml_str.strip(), template["name"]
