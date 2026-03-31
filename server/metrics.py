import numpy as np
from scipy.signal import lfilter, medfilt
from scipy.interpolate import interp1d
from itertools import groupby

def clean_ride_data(power_array, hr_array=None, cadence_array=None):
    """
    Clean ride data:
    - Missing values (gaps < 10s): Linear interpolation.
    - Outlier detection: Zero out power > 2500W and smooth spikes using median filter (3-5s).
    """
    def _clean_single_array(arr, is_power=False):
        if arr is None or len(arr) == 0:
            return arr
            
        # Convert to numpy float array, treating None as NaN
        arr = np.array([float(x) if x is not None else np.nan for x in arr], dtype=float)
        
        # Power specific cleaning: Outlier detection
        if is_power:
            # Zero out power > 2500W (impossible for human)
            arr[arr > 2500] = 0.0
        
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
                    # We need at least one non-NaN before and after for good interpolation, 
                    # but interp1d with 'linear' handles edge cases with 'extrapolate'.
                    # However, we only want to fill the small gaps.
                    mask = ~nans
                    if np.sum(mask) >= 2:
                        f = interp1d(x[mask], arr[mask], kind='linear', bounds_error=False, fill_value="extrapolate")
                        arr[indices] = f(indices)
        
        # Statistical outlier removal (spike suppression) using median filter
        # Apply to all signals (power, HR, cadence) to handle stochastic anomalies
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
    cleaned_hr = _clean_single_array(hr_array) if hr_array is not None else None
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
