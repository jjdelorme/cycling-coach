"""Convert ZWO workout XML to Garmin FIT workout files."""

import xml.etree.ElementTree as ET

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import (
    FileType, Sport, Intensity,
    WorkoutStepDuration, WorkoutStepTarget,
)


def zwo_to_fit(xml_str: str, ftp: int = 261, workout_name: str = "Workout") -> bytes:
    """Convert a ZWO workout XML string to a Garmin FIT workout file.

    Args:
        xml_str: ZWO XML content.
        ftp: Athlete's FTP for computing absolute power targets.
        workout_name: Name for the workout.

    Returns:
        FIT file bytes.
    """
    root = ET.fromstring(xml_str)
    workout_el = root.find("workout")
    if workout_el is None:
        raise ValueError("No <workout> element found in ZWO")

    name_el = root.find("name")
    if name_el is not None and name_el.text:
        workout_name = name_el.text

    # Parse all steps from ZWO
    steps = _parse_zwo_to_steps(workout_el, ftp)
    if not steps:
        raise ValueError("No workout steps found in ZWO")

    # Build FIT file
    builder = FitFileBuilder(auto_define=True)

    # File ID
    file_id = FileIdMessage()
    file_id.type = FileType.WORKOUT
    file_id.manufacturer = 1  # Garmin
    file_id.product = 0
    file_id.serial_number = 12345
    builder.add(file_id)

    # Workout message
    wkt = WorkoutMessage()
    wkt.sport = Sport.CYCLING
    wkt.num_valid_steps = len(steps)
    wkt.wkt_name = workout_name[:40]  # FIT name limit
    builder.add(wkt)

    # Workout steps
    for i, step in enumerate(steps):
        msg = WorkoutStepMessage()
        msg.message_index = i
        msg.wkt_step_name = step["name"][:16]  # FIT step name limit
        msg.duration_type = WorkoutStepDuration.TIME
        msg.duration_value = step["duration_ms"]
        msg.target_type = WorkoutStepTarget.POWER
        msg.custom_target_value_low = step["power_low"]
        msg.custom_target_value_high = step["power_high"]
        msg.intensity = step["intensity"]
        builder.add(msg)

    fit_file = builder.build()
    return fit_file.to_bytes()


def _parse_zwo_to_steps(workout_el, ftp: int) -> list[dict]:
    """Parse ZWO workout element into FIT-compatible step definitions."""
    steps = []

    for el in workout_el:
        tag = el.tag

        if tag == "IntervalsT":
            repeat = int(el.get("Repeat", "1"))
            on_dur = int(float(el.get("OnDuration", "0")))
            off_dur = int(float(el.get("OffDuration", "0")))
            on_pct = float(el.get("OnPower", "1.0"))
            off_pct = float(el.get("OffPower", "0.5"))

            on_watts = round(on_pct * ftp)
            off_watts = round(off_pct * ftp)
            # Give a +/- 5% range for power targets
            on_margin = max(5, round(on_watts * 0.03))
            off_margin = max(5, round(off_watts * 0.05))

            for i in range(repeat):
                steps.append({
                    "name": f"Int {i+1}/{repeat}",
                    "duration_ms": on_dur * 1000,
                    "power_low": on_watts - on_margin,
                    "power_high": on_watts + on_margin,
                    "intensity": Intensity.ACTIVE,
                })
                steps.append({
                    "name": "Recovery",
                    "duration_ms": off_dur * 1000,
                    "power_low": off_watts - off_margin,
                    "power_high": off_watts + off_margin,
                    "intensity": Intensity.RECOVERY,
                })

        elif tag == "Warmup":
            dur = int(float(el.get("Duration", "0")))
            low_pct = float(el.get("PowerLow", "0.4"))
            high_pct = float(el.get("PowerHigh", "0.65"))
            steps.append({
                "name": "Warmup",
                "duration_ms": dur * 1000,
                "power_low": round(low_pct * ftp),
                "power_high": round(high_pct * ftp),
                "intensity": Intensity.WARMUP,
            })

        elif tag == "Cooldown":
            dur = int(float(el.get("Duration", "0")))
            low_pct = float(el.get("PowerLow", "0.4"))
            high_pct = float(el.get("PowerHigh", "0.65"))
            steps.append({
                "name": "Cooldown",
                "duration_ms": dur * 1000,
                "power_low": round(low_pct * ftp),
                "power_high": round(high_pct * ftp),
                "intensity": Intensity.COOLDOWN,
            })

        elif tag == "SteadyState":
            dur = int(float(el.get("Duration", "0")))
            pct = float(el.get("Power", "0.65"))
            watts = round(pct * ftp)
            margin = max(5, round(watts * 0.03))
            steps.append({
                "name": _zone_name(pct),
                "duration_ms": dur * 1000,
                "power_low": watts - margin,
                "power_high": watts + margin,
                "intensity": Intensity.ACTIVE,
            })

    return steps


def _zone_name(pct: float) -> str:
    """Short zone name for FIT step labels."""
    if pct < 0.56:
        return "Z1 Easy"
    elif pct < 0.76:
        return "Z2 Endurance"
    elif pct < 0.91:
        return "Z3 Tempo"
    elif pct < 1.06:
        return "Z4 Threshold"
    elif pct < 1.21:
        return "Z5 VO2max"
    else:
        return "Z6 Anaerobic"
