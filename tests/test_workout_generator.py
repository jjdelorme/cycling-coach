"""Tests for workout generator, FIT export, and TCX export."""

import xml.etree.ElementTree as ET

from server.services.workout_generator import generate_zwo, WORKOUT_TEMPLATES
from server.services.fit_export import zwo_to_fit
from server.services.tcx_export import zwo_to_tcx


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


# FIT export tests

def test_fit_export_endurance():
    xml_str, name = generate_zwo("z2_endurance", duration_minutes=90, ftp=261)
    fit_bytes = zwo_to_fit(xml_str, ftp=261, workout_name=name)
    assert len(fit_bytes) > 50
    # Verify it's a valid FIT file (starts with header size byte + ".FIT" signature)
    assert fit_bytes[8:12] == b'.FIT'


def test_fit_export_intervals():
    xml_str, name = generate_zwo("vo2max_4x4", ftp=261)
    fit_bytes = zwo_to_fit(xml_str, ftp=261, workout_name=name)
    assert len(fit_bytes) > 50
    assert fit_bytes[8:12] == b'.FIT'


def test_fit_export_all_templates():
    for workout_type in WORKOUT_TEMPLATES:
        xml_str, name = generate_zwo(workout_type, ftp=261)
        fit_bytes = zwo_to_fit(xml_str, ftp=261, workout_name=name)
        assert len(fit_bytes) > 50, f"FIT export failed for {workout_type}"
        assert fit_bytes[8:12] == b'.FIT', f"Invalid FIT header for {workout_type}"


def test_fit_export_roundtrip():
    """Verify FIT file can be read back by the FIT SDK."""
    from fit_tool.fit_file import FitFile
    xml_str, name = generate_zwo("sweetspot_3x15", ftp=261)
    fit_bytes = zwo_to_fit(xml_str, ftp=261, workout_name=name)
    fit_file = FitFile.from_bytes(fit_bytes)
    assert len(fit_file.records) > 0


# TCX export tests

def test_tcx_export_basic():
    xml_str, name = generate_zwo("z2_endurance", duration_minutes=90, ftp=261)
    tcx = zwo_to_tcx(xml_str, ftp=261, workout_name=name)
    root = ET.fromstring(tcx)
    ns = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
    workout = root.find(".//tcx:Workout", ns)
    assert workout is not None
    assert workout.get("Sport") == "Biking"
    steps = workout.findall("tcx:Step", ns)
    assert len(steps) >= 2


def test_tcx_export_intervals_use_repeat():
    xml_str, name = generate_zwo("vo2max_4x4", ftp=261)
    tcx = zwo_to_tcx(xml_str, ftp=261, workout_name=name)
    # Should contain Repeat_t for intervals
    assert 'xsi:type="Repeat_t"' in tcx
    assert "<Repetitions>4</Repetitions>" in tcx


def test_tcx_export_step_names_include_watts():
    xml_str, name = generate_zwo("sweetspot_3x15", ftp=261)
    tcx = zwo_to_tcx(xml_str, ftp=261, workout_name=name)
    # Sweet spot at 90% of 261 = 235w
    assert "235w" in tcx
    assert "90%" in tcx


def test_tcx_export_includes_scheduled_date():
    xml_str, name = generate_zwo("z2_endurance", ftp=261)
    tcx = zwo_to_tcx(xml_str, ftp=261, scheduled_date="2026-03-26")
    assert "Scheduled: 2026-03-26" in tcx


def test_tcx_export_all_templates():
    for workout_type in WORKOUT_TEMPLATES:
        xml_str, name = generate_zwo(workout_type, ftp=261)
        tcx = zwo_to_tcx(xml_str, ftp=261, workout_name=name)
        root = ET.fromstring(tcx)
        ns = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
        workout = root.find(".//tcx:Workout", ns)
        assert workout is not None, f"TCX export failed for {workout_type}"
