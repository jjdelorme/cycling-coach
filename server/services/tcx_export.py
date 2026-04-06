"""Convert ZWO workout XML to Garmin TCX workout files."""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Optional

from server.zones import power_zone_label

NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOC = f"{NS} http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"


def zwo_to_tcx(
    xml_str: str,
    ftp: int = 0,
    workout_name: str = "Workout",
    scheduled_date: Optional[str] = None,
) -> str:
    """Convert a ZWO workout XML string to a Garmin TCX workout file.

    Args:
        xml_str: ZWO XML content.
        ftp: Athlete's FTP for computing absolute power targets.
        workout_name: Name for the workout.
        scheduled_date: Optional date (YYYY-MM-DD) to include in notes.

    Returns:
        TCX XML string.
    """
    zwo_root = ET.fromstring(xml_str)
    workout_el = zwo_root.find("workout")
    if workout_el is None:
        raise ValueError("No <workout> element found in ZWO")

    name_el = zwo_root.find("name")
    if name_el is not None and name_el.text:
        workout_name = name_el.text

    desc_el = zwo_root.find("description")
    description = desc_el.text if desc_el is not None and desc_el.text else ""

    # Build TCX
    root = ET.Element("TrainingCenterDatabase")
    root.set("xmlns", NS)
    root.set("xmlns:xsi", XSI)
    root.set("xsi:schemaLocation", SCHEMA_LOC)

    workouts = ET.SubElement(root, "Workouts")
    workout = ET.SubElement(workouts, "Workout")
    workout.set("Sport", "Biking")
    ET.SubElement(workout, "Name").text = workout_name

    # Add notes with description, FTP, and scheduled date
    notes_parts = []
    if description:
        # Strip any existing FTP line from description to avoid duplication
        desc_lines = [l for l in description.split("\n") if not l.strip().startswith("FTP:")]
        if desc_lines:
            notes_parts.append("\n".join(desc_lines).strip())
    notes_parts.append(f"FTP: {ftp}w")
    if scheduled_date:
        notes_parts.append(f"Scheduled: {scheduled_date}")
    ET.SubElement(workout, "Notes").text = "\n".join(notes_parts)

    step_id = [1]  # mutable counter for nested steps

    for el in workout_el:
        _convert_zwo_element(el, workout, ftp, step_id)

    # Pretty-print
    xml_out = minidom.parseString(
        ET.tostring(root, encoding="unicode")
    ).toprettyxml(indent="  ")

    # Remove extra XML declaration
    lines = xml_out.split("\n")
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'

    return "\n".join(lines)


def _convert_zwo_element(el, parent, ftp: int, step_id: list[int]):
    """Convert a single ZWO element to TCX Step(s)."""
    tag = el.tag

    if tag == "IntervalsT":
        repeat = int(el.get("Repeat", "1"))
        on_dur = int(float(el.get("OnDuration", "0")))
        off_dur = int(float(el.get("OffDuration", "0")))
        on_pct = float(el.get("OnPower", "1.0"))
        off_pct = float(el.get("OffPower", "0.5"))
        on_watts = round(on_pct * ftp)
        off_watts = round(off_pct * ftp)

        # Create Repeat_t step
        repeat_step = ET.SubElement(parent, "Step")
        repeat_step.set("xsi:type", "Repeat_t")
        ET.SubElement(repeat_step, "StepId").text = str(step_id[0])
        step_id[0] += 1
        ET.SubElement(repeat_step, "Repetitions").text = str(repeat)

        # On child
        child_on = ET.SubElement(repeat_step, "Child")
        child_on.set("xsi:type", "Step_t")
        ET.SubElement(child_on, "StepId").text = str(step_id[0])
        step_id[0] += 1
        ET.SubElement(child_on, "Name").text = f"{power_zone_label(on_pct)} {on_watts}w ({round(on_pct*100)}%)"
        dur = ET.SubElement(child_on, "Duration")
        dur.set("xsi:type", "Time_t")
        ET.SubElement(dur, "Seconds").text = str(on_dur)
        ET.SubElement(child_on, "Intensity").text = "Active"
        target = ET.SubElement(child_on, "Target")
        target.set("xsi:type", "None_t")

        # Off child
        child_off = ET.SubElement(repeat_step, "Child")
        child_off.set("xsi:type", "Step_t")
        ET.SubElement(child_off, "StepId").text = str(step_id[0])
        step_id[0] += 1
        ET.SubElement(child_off, "Name").text = f"Recovery {off_watts}w ({round(off_pct*100)}%)"
        dur_off = ET.SubElement(child_off, "Duration")
        dur_off.set("xsi:type", "Time_t")
        ET.SubElement(dur_off, "Seconds").text = str(off_dur)
        ET.SubElement(child_off, "Intensity").text = "Rest"
        target_off = ET.SubElement(child_off, "Target")
        target_off.set("xsi:type", "None_t")

    elif tag == "Warmup":
        dur_s = int(float(el.get("Duration", "0")))
        low_pct = float(el.get("PowerLow", "0.4"))
        high_pct = float(el.get("PowerHigh", "0.65"))
        low_w = round(low_pct * ftp)
        high_w = round(high_pct * ftp)

        step = ET.SubElement(parent, "Step")
        step.set("xsi:type", "Step_t")
        ET.SubElement(step, "StepId").text = str(step_id[0])
        step_id[0] += 1
        ET.SubElement(step, "Name").text = f"Warmup {low_w}-{high_w}w"
        dur = ET.SubElement(step, "Duration")
        dur.set("xsi:type", "Time_t")
        ET.SubElement(dur, "Seconds").text = str(dur_s)
        ET.SubElement(step, "Intensity").text = "Warmup"
        target = ET.SubElement(step, "Target")
        target.set("xsi:type", "None_t")

    elif tag == "Cooldown":
        dur_s = int(float(el.get("Duration", "0")))
        low_pct = float(el.get("PowerLow", "0.4"))
        high_pct = float(el.get("PowerHigh", "0.65"))
        low_w = round(low_pct * ftp)
        high_w = round(high_pct * ftp)

        step = ET.SubElement(parent, "Step")
        step.set("xsi:type", "Step_t")
        ET.SubElement(step, "StepId").text = str(step_id[0])
        step_id[0] += 1
        ET.SubElement(step, "Name").text = f"Cooldown {high_w}-{low_w}w"
        dur = ET.SubElement(step, "Duration")
        dur.set("xsi:type", "Time_t")
        ET.SubElement(dur, "Seconds").text = str(dur_s)
        ET.SubElement(step, "Intensity").text = "Cooldown"
        target = ET.SubElement(step, "Target")
        target.set("xsi:type", "None_t")

    elif tag == "SteadyState":
        dur_s = int(float(el.get("Duration", "0")))
        pct = float(el.get("Power", "0.65"))
        watts = round(pct * ftp)

        step = ET.SubElement(parent, "Step")
        step.set("xsi:type", "Step_t")
        ET.SubElement(step, "StepId").text = str(step_id[0])
        step_id[0] += 1
        ET.SubElement(step, "Name").text = f"{power_zone_label(pct)} {watts}w ({round(pct*100)}%)"
        dur = ET.SubElement(step, "Duration")
        dur.set("xsi:type", "Time_t")
        ET.SubElement(dur, "Seconds").text = str(dur_s)

        # Map to appropriate intensity
        if pct < 0.56:
            intensity = "Rest"
        elif pct >= 1.05:
            intensity = "Active"
        else:
            intensity = "Active"
        ET.SubElement(step, "Intensity").text = intensity
        target = ET.SubElement(step, "Target")
        target.set("xsi:type", "None_t")

