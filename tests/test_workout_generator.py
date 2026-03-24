"""Tests for workout generator."""

import xml.etree.ElementTree as ET

from server.services.workout_generator import generate_zwo, WORKOUT_TEMPLATES


def test_z2_endurance():
    xml_str, name = generate_zwo("z2_endurance", duration_minutes=90, ftp=250)
    assert name == "Z2 Endurance"
    root = ET.fromstring(xml_str)
    assert root.tag == "workout_file"
    assert root.find("name").text == "Z2 Endurance"
    workout = root.find("workout")
    assert len(list(workout)) >= 2


def test_threshold_2x20():
    xml_str, name = generate_zwo("threshold_2x20", ftp=261)
    root = ET.fromstring(xml_str)
    workout = root.find("workout")
    # Should have warmup, work, rest, work, cooldown
    elements = list(workout)
    assert len(elements) == 5
    # Work intervals should be at FTP (1.0)
    assert elements[1].get("Power") == "1.0"


def test_vo2max_intervals():
    xml_str, name = generate_zwo("vo2max_4x4", ftp=261)
    root = ET.fromstring(xml_str)
    workout = root.find("workout")
    intervals = workout.find("IntervalsT")
    assert intervals is not None
    assert intervals.get("Repeat") == "4"
    assert intervals.get("OnDuration") == "240"


def test_all_templates_generate_valid_xml():
    for workout_type in WORKOUT_TEMPLATES:
        xml_str, name = generate_zwo(workout_type, ftp=261)
        root = ET.fromstring(xml_str)
        assert root.tag == "workout_file"
        assert root.find("workout") is not None


def test_unknown_type():
    import pytest
    with pytest.raises(ValueError, match="Unknown workout type"):
        generate_zwo("nonexistent")


def test_duration_applied_to_endurance():
    xml_60, _ = generate_zwo("z2_endurance", duration_minutes=60, ftp=261)
    xml_120, _ = generate_zwo("z2_endurance", duration_minutes=120, ftp=261)

    root_60 = ET.fromstring(xml_60)
    root_120 = ET.fromstring(xml_120)

    # Get main interval duration
    w60 = list(root_60.find("workout"))
    w120 = list(root_120.find("workout"))
    dur_60 = int(w60[1].get("Duration"))
    dur_120 = int(w120[1].get("Duration"))

    assert dur_120 > dur_60
