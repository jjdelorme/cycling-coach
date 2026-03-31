import math
import numpy as np
from scipy.signal import lfilter, medfilt
from scipy.ndimage import uniform_filter1d
from scipy.interpolate import interp1d
from itertools import groupby

POWER_BEST_DURATIONS = [5, 30, 60, 300, 1200, 3600]  # seconds

def _clean_hr_array(arr):
    if arr is None or len(arr) == 0:
        return arr
    
    # Convert to numpy float array, treating None as NaN
    arr = np.array([float(x) if x is not None else np.nan for x in arr], dtype=float)
    
    # 0. Median filter to handle single-point spikes
    if len(arr) >= 3:
        # Fill NaNs temporarily for filtering
        mask = ~np.isnan(arr)
        if np.any(mask):
            temp_arr = arr.copy()
            if np.any(~mask):
                x = np.arange(len(arr))
                f_fill = interp1d(x[mask], arr[mask], kind='nearest', bounds_error=False, fill_value="extrapolate")
                temp_arr[~mask] = f_fill(x[~mask])
            
            padded = np.pad(temp_arr, (1, 1), mode='edge')
            filtered = medfilt(padded, kernel_size=3)
            arr[mask] = filtered[1:-1][mask]

    # 1. Physiological Bounds check (Humans alive and exercising)
    arr[(arr < 30) | (arr > 240)] = np.nan
    
    # 2. Rate of change (RoC) filter (max 10 bpm per sec is physiologically impossible)
    if len(arr) > 1:
        diffs = np.abs(np.diff(arr))
        # diffs[i] is arr[i+1] - arr[i]. If diff > 10, mark arr[i+1] as nan
        roc_mask = np.concatenate(([False], diffs > 10.0))
        arr[roc_mask] = np.nan
    
    # 3. Interpolate the NaNs that were just created
    nans = np.isnan(arr)
    if np.any(nans) and np.any(~nans):
        x = np.arange(len(arr))
        mask = ~nans
        if np.sum(mask) >= 2:
            f = interp1d(x[mask], arr[mask], kind='linear', bounds_error=False, fill_value="extrapolate")
            # Only interpolate small gaps (<10s)
            for is_nan, group in groupby(enumerate(nans), key=lambda x: x[1]):
                group_list = list(group)
                if is_nan and len(group_list) < 10:
                    indices = [i for i, _ in group_list]
                    arr[indices] = f(indices)
                    
    return arr

def clean_ride_data(power_array, hr_array=None, cadence_array=None):
    """
    Clean ride data:
    - Missing values (gaps < 10s): Linear interpolation.
    - Outlier detection: Power uses rolling Z-score and hard cutoff.
    - Heart rate: Biological bounds, RoC filtering, and median filter.
    """
    def _clean_single_array(arr, is_power=False):
        if arr is None or len(arr) == 0:
            return arr
            
        # Convert to numpy float array, treating None as NaN
        arr = np.array([float(x) if x is not None else np.nan for x in arr], dtype=float)
        
        # Power specific cleaning: Outlier detection
        if is_power:
            # Set power > 2500W to NaN for interpolation instead of 0
            arr[arr > 2500] = np.nan
        
        # Linear interpolation for gaps (NaNs) < 10s
        nans = np.isnan(arr)
        if np.any(nans) and np.any(~nans):
            x = np.arange(len(arr))
            # Find groups of NaNs
            for is_nan, group in groupby(enumerate(nans), key=lambda x: x[1]):
                group_list = list(group)
                if is_nan and len(group_list) < 10:
                    # Small gap: interpolate
                    indices = [i for i, _ in group_list]
                    mask = ~nans
                    if np.sum(mask) >= 2:
                        f = interp1d(x[mask], arr[mask], kind='linear', bounds_error=False, fill_value="extrapolate")
                        arr[indices] = f(indices)
        
        # Rolling Z-Score Outlier Detection for Power
        if is_power and len(arr) >= 30:
            # Use 30-second rolling window to ensure single-point spikes have Z > 4
            window = 30 
            
            # Temporarily fill NaNs for rolling calculations to prevent NaN propagation
            temp_arr = arr.copy()
            nans_temp = np.isnan(temp_arr)
            if np.any(nans_temp) and np.any(~nans_temp):
                x = np.arange(len(temp_arr))
                mask = ~nans_temp
                f_fill = interp1d(x[mask], temp_arr[mask], kind='nearest', bounds_error=False, fill_value="extrapolate")
                temp_arr[nans_temp] = f_fill(x[nans_temp])
            elif np.all(nans_temp):
                temp_arr[:] = 0.0
                
            rolling_mean = uniform_filter1d(temp_arr, size=window)
            rolling_sq_mean = uniform_filter1d(temp_arr**2, size=window)
            
            # Calculate standard deviation safely to avoid negative variances due to float precision
            variance = np.maximum(rolling_sq_mean - rolling_mean**2, 0)
            rolling_std = np.sqrt(variance)
            
            # Avoid division by zero when signal is perfectly steady
            rolling_std[rolling_std < 1.0] = 1.0
            
            # Compute Z-score contextual to the current window
            z_scores = np.abs((temp_arr - rolling_mean) / rolling_std)
            
            # Flag anomalies (Z > 4.0 captures sensor glitches but ignores organic sprint onset)
            anomalies = z_scores > 4.0
            
            # Replace anomalies with the contextual rolling mean
            if np.any(anomalies):
                arr[anomalies] = rolling_mean[anomalies]
        
        # Statistical outlier removal (spike suppression) using median filter
        # Apply to all signals (including power for short arrays or single points)
        if len(arr) >= 5:
            # Fill NaNs temporarily for filtering to avoid propagating NaNs
            mask = ~np.isnan(arr)
            if np.any(mask):
                temp_arr = arr.copy()
                if np.any(~mask):
                    x = np.arange(len(arr))
                    f_fill = interp1d(x[mask], arr[mask], kind='nearest', bounds_error=False, fill_value="extrapolate")
                    temp_arr[~mask] = f_fill(x[~mask])
                
                # Use 5s window for power, 3s for others
                k_size = 5 if is_power else 3
                # Pad to avoid edge effects
                padded = np.pad(temp_arr, (k_size//2, k_size//2), mode='edge')
                filtered = medfilt(padded, kernel_size=k_size)
                # Recover filtered signal
                arr_filtered = filtered[k_size//2 : -(k_size//2) if k_size//2 > 0 else None]
                
                # Only apply filter where we have data (don't fill large gaps with filtered noise)
                arr[mask] = arr_filtered[mask]
        
        return arr

    cleaned_power = _clean_single_array(power_array, is_power=True)
    cleaned_hr = _clean_hr_array(hr_array) if hr_array is not None else None
    cleaned_cadence = _clean_single_array(cadence_array) if cadence_array is not None else None
    
    return cleaned_power, cleaned_hr, cleaned_cadence

def calculate_np(power_array):
    """
    Calculate Normalized Power (NP) from a power array.
    
    NP is a 30-second rolling average, raised to the 4th power, 
    averaged, and then the 4th root is taken.
    """
    if len(power_array) < 30:
        return float(np.mean(power_array)) if len(power_array) > 0 else 0.0
    
    # Convert to float64 for precision and handle NaNs by treating as 0
    p = np.nan_to_num(power_array, nan=0.0).astype(float)
    
    # 30-second rolling average
    window = np.ones(30) / 30
    roll_avg = np.convolve(p, window, mode='valid')
    
    # 4th power, mean, and 4th root
    np_val = np.mean(roll_avg ** 4) ** 0.25
    return float(np_val)

def calculate_tss(np_val, duration_s, ftp):
    """
    Calculate Training Stress Score (TSS).
    TSS = (duration_s * NP * IF) / (FTP * 3600) * 100
    IF = NP / FTP
    """
    if ftp <= 0:
        return 0.0
    tss = (duration_s * (np_val ** 2)) / (ftp ** 2 * 36)
    return float(tss)

def compute_rolling_best(powers, window_s, hrs=None, cadences=None):
    if len(powers) < window_s:
        return None
    
    # Use numpy for performance if possible, but keep the logic consistent with original
    # Convert to numpy array and handle NaNs
    p = np.nan_to_num(powers, nan=0.0).astype(float)
    
    # Vectorized sliding window sum
    window = np.ones(window_s)
    sums = np.convolve(p, window, mode='valid')
    best_idx = int(np.argmax(sums))
    best_sum = sums[best_idx]
            
    avg_power = round(best_sum / window_s)
    
    res = {
        "power": avg_power,
        "start_offset_s": best_idx,
        "avg_hr": None,
        "avg_cadence": None
    }
    
    if hrs is not None:
        window_hrs = [h for h in hrs[best_idx : best_idx + window_s] if h is not None and not np.isnan(h)]
        res["avg_hr"] = round(sum(window_hrs) / len(window_hrs)) if window_hrs else None
        
    if cadences is not None:
        window_cadences = [c for c in cadences[best_idx : best_idx + window_s] if c is not None and not np.isnan(c)]
        res["avg_cadence"] = round(sum(window_cadences) / len(window_cadences)) if window_cadences else None
        
    return res

def compute_hr_tss(avg_hr: float, duration_s: float, lthr: float, max_hr: float, resting_hr: float) -> float:
    """Compute heart-rate-based TSS (hrTSS) using the exponential TRIMP model.

    This is the standard formula used by TrainingPeaks when power data is unavailable.
    hrTSS approximates the training stress using heart rate relative to lactate threshold.

    Args:
        avg_hr: Average heart rate for the activity (bpm).
        duration_s: Duration of the activity (seconds).
        lthr: Lactate threshold heart rate (bpm).
        max_hr: Maximum heart rate (bpm).
        resting_hr: Resting heart rate (bpm).

    Returns:
        Estimated TSS value, or 0 if inputs are invalid.
    """
    hr_range = max_hr - resting_hr
    if hr_range <= 0 or lthr <= resting_hr or duration_s <= 0 or avg_hr <= resting_hr:
        return 0.0

    duration_h = duration_s / 3600.0

    # Heart rate reserve ratio for the activity
    hr_ratio = (avg_hr - resting_hr) / hr_range

    # Heart rate reserve ratio at LTHR (the reference point = 100 TSS/hr)
    lthr_ratio = (lthr - resting_hr) / hr_range

    # Exponential TRIMP factor
    trimp_activity = hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
    trimp_lthr = lthr_ratio * 0.64 * math.exp(1.92 * lthr_ratio)

    if trimp_lthr <= 0:
        return 0.0

    hr_tss = (duration_h * trimp_activity / trimp_lthr) * 100.0
    return round(hr_tss, 1)

def calculate_pmc(tss_list, initial_ctl=0.0, initial_atl=0.0):
    """
    Calculate CTL and ATL from a sequence of daily TSS values using a vectorized EWMA.
    CTL = 42-day EWMA, ATL = 7-day EWMA.
    Returns lists of (ctl, atl) for each day.
    """
    if not tss_list:
        return [], []
        
    x = np.array(tss_list, dtype=float)
    
    def ewma(data, tau, initial):
        # Formula: y[n] = (1/tau)*x[n] + (1 - 1/tau)*y[n-1]
        # In lfilter form: a[0]*y[n] + a[1]*y[n-1] = b[0]*x[n]
        # a = [1.0, -(1.0 - 1.0/tau)], b = [1.0/tau]
        b = [1.0 / tau]
        a = [1.0, -(1.0 - 1.0 / tau)]
        # Initial condition for lfilter to start with y[-1] = initial
        # zi = (1.0 - 1.0/tau) * initial
        zi = np.array([(1.0 - 1.0 / tau) * initial])
        y, _ = lfilter(b, a, data, zi=zi)
        return y

    ctl_values = ewma(x, 42, initial_ctl)
    atl_values = ewma(x, 7, initial_atl)
    
    return ctl_values.tolist(), atl_values.tolist()

def process_ride_samples(raw_powers, raw_hrs, raw_cadences, ftp, duration_s, lthr=0, max_hr=0, resting_hr=0):
    """
    Pure logic pipeline to process raw ride streams into structured metrics.
    Stateless and decoupled from I/O.
    """
    # 1. Clean using SciPy pipeline
    cleaned_p, cleaned_hr, cleaned_cadence = clean_ride_data(raw_powers, raw_hrs, raw_cadences)
    
    # Identify if we have power data and update status
    has_power_data = any(p is not None and not np.isnan(p) and p > 0 for p in (cleaned_p if cleaned_p is not None else []))
    data_status = "cleaned" if has_power_data else "raw"

    # Convert vectors back to list of native types for further use, NaNs become None
    # (used for power bests and averaging)
    powers_list = [float(p) if not np.isnan(p) else None for p in cleaned_p] if cleaned_p is not None else []
    hrs_list = [int(h) if not np.isnan(h) else None for h in cleaned_hr] if cleaned_hr is not None else []
    cadences_list = [int(c) if not np.isnan(c) else None for c in cleaned_cadence] if cleaned_cadence is not None else []

    # 2. Recalculate NP and TSS using vectorized math if we have power data
    powers_vec = np.nan_to_num(cleaned_p, nan=0.0) if cleaned_p is not None else np.array([])
    
    np_power = 0.0
    tss = 0.0
    avg_power = 0.0
    intensity_factor = 0.0
    vi = 0.0
    power_bests = []

    if has_power_data:
        np_power = calculate_np(powers_vec)
        tss = calculate_tss(np_power, duration_s, ftp)
        avg_power = round(np.mean(powers_vec))
        intensity_factor = round(np_power / ftp, 3) if ftp > 0 else 0
        if avg_power > 0:
            vi = round(np_power / avg_power, 3)

        # Power bests at standard durations
        for dur in POWER_BEST_DURATIONS:
            res = compute_rolling_best(powers_vec, dur, hrs=hrs_list, cadences=cadences_list)
            if res and res["power"] > 0:
                power_bests.append({
                    "duration_s": dur,
                    "power": res["power"],
                    "avg_hr": res["avg_hr"],
                    "avg_cadence": res["avg_cadence"],
                    "start_offset_s": res["start_offset_s"]
                })
    
    # If no power-based TSS but we have HR data, compute hrTSS
    elif raw_hrs and any(h is not None for h in raw_hrs):
        # Use average HR from cleaned data if available, else raw
        if hrs_list:
            valid_hrs = [h for h in hrs_list if h is not None]
            avg_hr = sum(valid_hrs) / len(valid_hrs) if valid_hrs else 0
        else:
            valid_raw_hrs = [h for h in raw_hrs if h is not None]
            avg_hr = sum(valid_raw_hrs) / len(valid_raw_hrs) if valid_raw_hrs else 0
            
        if avg_hr > 0 and lthr > 0:
            tss = compute_hr_tss(avg_hr, duration_s, lthr, max_hr, resting_hr)

    # Calculate average HR and cadence from cleaned data even without power
    final_avg_hr = 0
    if hrs_list:
        valid_hrs = [h for h in hrs_list if h is not None]
        final_avg_hr = round(sum(valid_hrs) / len(valid_hrs)) if valid_hrs else 0
        
    final_avg_cadence = 0
    if cadences_list:
        valid_cadences = [c for c in cadences_list if c is not None]
        final_avg_cadence = round(sum(valid_cadences) / len(valid_cadences)) if valid_cadences else 0

    return {
        "np_power": np_power,
        "tss": tss,
        "avg_power": avg_power,
        "intensity_factor": intensity_factor,
        "variability_index": vi,
        "has_power_data": has_power_data,
        "data_status": data_status,
        "power_bests": power_bests,
        "avg_hr": final_avg_hr,
        "avg_cadence": final_avg_cadence,
        "powers": powers_list,
        "hrs": hrs_list,
        "cadences": cadences_list
    }
