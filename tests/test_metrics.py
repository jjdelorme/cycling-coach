import numpy as np
import pytest
from server.metrics import (
    calculate_np, calculate_tss, calculate_pmc, clean_ride_data, process_ride_samples
)

def test_clean_ride_data_interpolation():
    """Verify linear interpolation fills small gaps (<10s) in power data."""
    # Gap of 5 NaNs
    power = np.array([100.0, 100.0, np.nan, np.nan, np.nan, np.nan, np.nan, 200.0, 200.0])
    # x = 0, 1, 2, 3, 4, 5, 6, 7, 8
    # y = 100, 100, NaN, NaN, NaN, NaN, NaN, 200, 200
    # Values between index 1 (100) and index 7 (200).
    # Gap length = 7 - 1 = 6. 
    # Slope = (200 - 100) / 6 = 100 / 6 = 16.666...
    # y[2] = 100 + 1 * 16.66... = 116.66...
    # y[6] = 100 + 5 * 16.66... = 183.33...
    
    cleaned_p, _, _ = clean_ride_data(power)
    assert not np.isnan(cleaned_p).any()
    assert cleaned_p[2] == pytest.approx(116.666666)
    assert cleaned_p[6] == pytest.approx(183.333333)

    # Gap of 11 NaNs (should NOT be interpolated)
    power_large_gap = np.array([100.0] + [np.nan]*11 + [200.0])
    cleaned_p_large, _, _ = clean_ride_data(power_large_gap)
    assert np.isnan(cleaned_p_large).any()
    assert np.sum(np.isnan(cleaned_p_large)) == 11

def test_clean_ride_data_outliers():
    """Verify power outliers (>2500W) are removed."""
    # Need at least 5 elements for medfilt to be applied in clean_ride_data
    power = np.array([100.0, 100.0, 3000.0, 100.0, 100.0])
    cleaned_p, _, _ = clean_ride_data(power)
    # 3000 becomes 0, then medfilt([100, 100, 0, 100, 100], kernel_size=5)
    # For the middle element: sorted([100, 100, 0, 100, 100]) -> [0, 100, 100, 100, 100]. Median = 100.
    assert cleaned_p[2] == 100.0
    assert (cleaned_p <= 2500.0).all()

def test_clean_ride_data_smoothing():
    """Verify spikes are smoothed by the median filter."""
    # A single spike
    power = np.array([100.0, 100.0, 500.0, 100.0, 100.0])
    cleaned_p, _, _ = clean_ride_data(power)
    # medfilt([100, 100, 500, 100, 100], 3)
    # i=0: [?, 100, 100] -> 100 (scipy pad with 0 by default? Actually it handles edges)
    # i=2: [100, 500, 100] -> median is 100
    assert cleaned_p[2] == 100.0

def test_calculate_np_constant_power():
    """Given an array of exactly 300W for 1 hour, NP=300."""
    duration_s = 3600
    power_array = np.full(duration_s, 300.0)
    np_val = calculate_np(power_array)
    assert np_val == pytest.approx(300.0)

def test_calculate_np_alternating_blocks():
    """Given alternating 100W and 300W blocks, calculate correct NP."""
    # 30s at 100W, followed by 30s at 300W
    power_array = np.concatenate([np.full(30, 100.0), np.full(30, 300.0)])
    
    # NP calculation:
    # 1. 30s rolling average (window=30)
    # Mode 'valid' gives N - K + 1 values.
    # length = 60 - 30 + 1 = 31 values.
    # roll_avg[0] = mean of power_array[0:30] = 100.0
    # roll_avg[1] = mean of power_array[1:31] = (100*29 + 300)/30 = 106.666...
    # roll_avg[i] = (100*(30-i) + 300*i)/30
    # roll_avg[30] = mean of power_array[30:60] = 300.0
    
    roll_avgs = []
    for i in range(31):
        roll_avgs.append((100*(30-i) + 300*i)/30.0)
    
    roll_avgs = np.array(roll_avgs)
    expected_np = np.mean(roll_avgs ** 4) ** 0.25
    
    np_val = calculate_np(power_array)
    assert np_val == pytest.approx(expected_np)

def test_calculate_tss():
    """Test with known NP, duration, and FTP values."""
    # Example: 1 hour at FTP should give 100 TSS.
    # TSS = (s * NP^2) / (FTP^2 * 36)
    # TSS = (3600 * FTP^2) / (FTP^2 * 36) = 100
    np_val = 200.0
    duration_s = 3600
    ftp = 200.0
    tss = calculate_tss(np_val, duration_s, ftp)
    assert tss == pytest.approx(100.0)
    
    # Another example: 2 hours at 0.70 IF
    # IF = NP / FTP = 0.70
    # TSS = 2 * 0.70^2 * 100 = 2 * 0.49 * 100 = 98
    np_val = 140.0
    duration_s = 7200
    ftp = 200.0
    tss = calculate_tss(np_val, duration_s, ftp)
    assert tss == pytest.approx(98.0)

def test_calculate_pmc():
    """
    CTL/ATL: Provide a predefined TSS sequence and assert EWMA values match.
    CTL = 42-day EWMA, ATL = 7-day EWMA.
    Formula: CTL_today = CTL_yesterday + (TSS_today - CTL_yesterday) / 42
    """
    # Test for 10 days of 100 TSS
    tss_sequence = [100.0] * 10
    ctl_vals, atl_vals = calculate_pmc(tss_sequence)
    
    # First day:
    # CTL = 0 + (100 - 0) / 42 = 100/42 = 2.38
    # ATL = 0 + (100 - 0) / 7 = 100/7 = 14.28
    assert ctl_vals[0] == pytest.approx(100.0 / 42)
    assert atl_vals[0] == pytest.approx(100.0 / 7)
    
    # Second day:
    # CTL = 100/42 + (100 - 100/42) / 42
    expected_ctl_2 = (100/42) + (100 - 100/42) / 42
    expected_atl_2 = (100/7) + (100 - 100/7) / 7
    assert ctl_vals[1] == pytest.approx(expected_ctl_2)
    assert atl_vals[1] == pytest.approx(expected_atl_2)

    # Long term convergence: if TSS is constant 100, CTL and ATL should approach 100.
    tss_sequence_long = [100.0] * 500
    ctl_vals_long, atl_vals_long = calculate_pmc(tss_sequence_long)
    assert ctl_vals_long[-1] == pytest.approx(100.0, rel=0.01)
    assert atl_vals_long[-1] == pytest.approx(100.0, rel=0.01)

def test_calculate_pmc_with_initial_values():
    """Test PMC with non-zero initial values."""
    tss_sequence = [100.0]
    ctl_vals, atl_vals = calculate_pmc(tss_sequence, initial_ctl=50.0, initial_atl=60.0)
    
    expected_ctl = 50.0 + (100.0 - 50.0) / 42
    expected_atl = 60.0 + (100.0 - 60.0) / 7
    
    assert ctl_vals[0] == pytest.approx(expected_ctl)
    assert atl_vals[0] == pytest.approx(expected_atl)

def test_process_ride_samples_structure():
    """Verify process_ride_samples returns the correct dictionary structure and handles empty data."""
    # Test with empty data
    result = process_ride_samples([], [], [], ftp=250, duration_s=0)
    
    assert isinstance(result, dict)
    expected_keys = {
        "np_power", "tss", "avg_power", "intensity_factor", 
        "variability_index", "has_power_data", "data_status", "power_bests"
    }
    assert expected_keys.issubset(result.keys())
    assert result["has_power_data"] is False
    assert isinstance(result["power_bests"], list)

def test_process_ride_samples_logic():
    """Verify process_ride_samples logic with dummy data."""
    # This test will likely fail until Phase 2 is implemented, 
    # but we define our expectations here.
    raw_powers = [200.0] * 3600 # 1 hour at 200W
    raw_hrs = [150.0] * 3600
    raw_cadences = [90.0] * 3600
    ftp = 200.0
    duration_s = 3600.0
    
    result = process_ride_samples(raw_powers, raw_hrs, raw_cadences, ftp, duration_s)

    # We expect NP=200, TSS=100, IF=1.0, VI=1.0 for constant 200W at 200W FTP
    assert result["np_power"] == pytest.approx(200.0)
    assert result["tss"] == pytest.approx(100.0)
    assert result["avg_power"] == pytest.approx(200.0)
    assert result["intensity_factor"] == pytest.approx(1.0)
    assert result["variability_index"] == pytest.approx(1.0)
    assert result["has_power_data"] is True

    # Check power bests structure
    # Expected: list of dicts like {"duration_s": 60, "power": 200.0}
    assert len(result["power_bests"]) > 0
    best_1min = next(b for b in result["power_bests"] if b["duration_s"] == 60)
    assert best_1min["power"] == pytest.approx(200.0)

def test_clean_ride_data_hr_bounds():
    """Verify HR values < 30 or > 240 are filtered and interpolated."""
    hr = np.array([120, 125, 255, 125, 120], dtype=float)
    # 255 is out of bounds, should be removed and interpolated
    _, cleaned_hr, _ = clean_ride_data(None, hr_array=hr)
    assert cleaned_hr[2] == pytest.approx(125.0)
    assert np.all(cleaned_hr >= 30)
    assert np.all(cleaned_hr <= 240)

def test_clean_ride_data_hr_roc():
    """Verify impossible sudden jumps in HR (>10 bpm/s) are filtered."""
    hr = np.array([120, 121, 145, 121, 120], dtype=float)
    # 145 is a +24 jump from 121, should be filtered
    _, cleaned_hr, _ = clean_ride_data(None, hr_array=hr)
    assert cleaned_hr[2] == pytest.approx(121.0)

def test_clean_ride_data_power_zscore():
    """Verify power spikes are caught by rolling Z-score but sprints are kept."""
    # 1. Brief massive spike
    power_spike = np.full(60, 200.0)
    power_spike[30] = 1000.0 # Massive spike in the middle
    # Add some tiny noise to avoid zero variance issues in the test itself
    power_spike += np.random.normal(0, 1, 60)

    cleaned_p, _, _ = clean_ride_data(power_spike)
    assert cleaned_p[30] < 500.0 # Should be significantly reduced (replaced by rolling mean)

    # 2. Sustained sprint (should NOT be filtered)
    power_sprint = np.full(60, 200.0)
    power_sprint[30:45] = 800.0 # 15-second sprint

    cleaned_p_sprint, _, _ = clean_ride_data(power_sprint)
    assert np.all(cleaned_p_sprint[30:45] >= 700.0) # Should be largely preserved

from server.metrics import compute_rolling_best

def test_compute_rolling_best():
    powers = np.array([100, 200, 300, 400, 500], dtype=float)
    
    # 3s window
    # windows: [100,200,300] -> sum 600, avg 200
    #          [200,300,400] -> sum 900, avg 300
    #          [300,400,500] -> sum 1200, avg 400 (best)
    
    res = compute_rolling_best(powers, 3)
    assert res["power"] == 400
    assert res["start_offset_s"] == 2

    # 1s window
    res = compute_rolling_best(powers, 1)
    assert res["power"] == 500
    assert res["start_offset_s"] == 4

    # 5s window
    res = compute_rolling_best(powers, 5)
    assert res["power"] == 300
    assert res["start_offset_s"] == 0

    # Window longer than powers
    res = compute_rolling_best(powers, 10)
    assert res is None

if __name__ == "__main__":
    # If run as script, we can still run some basic tests
    test_compute_rolling_best()
    print("All basic tests passed!")
