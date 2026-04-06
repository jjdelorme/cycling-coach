import pytest
from server.services.workout_generator import calculate_planned_tss

def test_calculate_planned_tss_steady_state():
    xml = """
<workout_file>
  <workout>
    <SteadyState Duration="3600" Power="1.0" />
  </workout>
</workout_file>
"""
    # TSS = (3600 * 1.0^2) / 3600 * 100 = 100
    assert calculate_planned_tss(xml) == 100.0

def test_calculate_planned_tss_defaults():
    xml = """
<workout_file>
  <workout>
    <SteadyState Duration="3600" />
  </workout>
</workout_file>
"""
    # SteadyState default Power is 0.65
    # TSS = (3600 * 0.65^2) / 3600 * 100 = 0.65^2 * 100 = 42.25
    # Python round(42.25, 1) is 42.2
    assert calculate_planned_tss(xml) == 42.2

def test_calculate_planned_tss_warmup_cooldown():
    xml = """
<workout_file>
  <workout>
    <Warmup Duration="600" PowerLow="0.4" PowerHigh="0.6" />
    <Cooldown Duration="600" PowerLow="0.6" PowerHigh="0.4" />
  </workout>
</workout_file>
"""
    # Avg power = 0.5
    # TSS = (600 * 0.5^2 + 600 * 0.5^2) / 3600 * 100
    # TSS = (150 + 150) / 3600 * 100 = 300 / 36 = 8.333...
    assert calculate_planned_tss(xml) == 8.3

def test_calculate_planned_tss_intervals_t():
    xml = """
<workout_file>
  <workout>
    <IntervalsT Repeat="5" OnDuration="60" OffDuration="60" OnPower="1.0" OffPower="0.5" />
  </workout>
</workout_file>
"""
    # TSS = 5 * (60 * 1.0^2 + 60 * 0.5^2) / 3600 * 100
    # TSS = 5 * (60 + 15) / 3600 * 100 = 5 * 75 / 36 = 375 / 36 = 10.4166...
    assert calculate_planned_tss(xml) == 10.4

def test_calculate_planned_tss_intervals_legacy():
    # This should fail currently as Intervals is not handled
    xml = """
<workout_file>
  <workout>
    <Intervals Repeat="5" OnDuration="60" OffDuration="60" OnPower="1.0" OffPower="0.5" />
  </workout>
</workout_file>
"""
    assert calculate_planned_tss(xml) == 10.4

def test_calculate_planned_tss_unknown_tag(caplog):
    xml = """
<workout_file>
  <workout>
    <UnknownTag Duration="3600" Power="1.0" />
    <SteadyState Duration="1800" Power="1.0" />
  </workout>
</workout_file>
"""
    # Should only count SteadyState: (1800 * 1.0^2) / 3600 * 100 = 50
    assert calculate_planned_tss(xml) == 50.0
    assert "Unknown workout tag: UnknownTag" in caplog.text

def test_calculate_planned_tss_empty_xml():
    assert calculate_planned_tss("") is None

def test_calculate_planned_tss_malformed_xml(caplog):
    assert calculate_planned_tss("<invalid") is None
    assert "Could not parse workout XML for TSS calculation" in caplog.text

def test_calculate_planned_tss_no_workout_tag():
    xml = "<workout_file></workout_file>"
    assert calculate_planned_tss(xml) is None

def test_calculate_planned_tss_zero_duration():
    xml = """
<workout_file>
  <workout>
    <SteadyState Duration="0" Power="1.0" />
  </workout>
</workout_file>
"""
    assert calculate_planned_tss(xml) is None
