import numpy as np
from scipy.signal import lfilter, medfilt
from scipy.interpolate import interp1d
from itertools import groupby

def clean_ride_data(power_array, hr_array=None, cadence_array=None):
    """
    Clean ride data:
    - Missing values (gaps < 10s): Linear interpolation.
    - Outlier detection: Zero out power > 2500W and smooth spikes using median filter.
    """
    def _clean_single_array(arr, is_power=False):
        if arr is None or len(arr) == 0:
            return arr
            
        arr = np.array(arr, dtype=float)
        
        # Power specific cleaning: Outlier detection
        if is_power:
            # Zero out power > 2500W
            arr[arr > 2500] = 0.0
        
        # Linear interpolation for gaps (NaNs)
        nans = np.isnan(arr)
        if np.any(nans) and np.any(~nans):
            x = np.arange(len(arr))
            if np.sum(~nans) >= 2:
                f = interp1d(x[~nans], arr[~nans], kind='linear', bounds_error=False, fill_value="extrapolate")
                
                new_arr = arr.copy()
                interpolated_values = f(x)
                
                for is_nan, group in groupby(enumerate(nans), key=lambda x: x[1]):
                    group_list = list(group)
                    if is_nan and len(group_list) < 10:
                        for i, _ in group_list:
                            new_arr[i] = interpolated_values[i]
                arr = new_arr
        
        # Power specific cleaning: Smooth spikes using median filter
        if is_power:
            if len(arr) >= 3:
                nans = np.isnan(arr)
                temp_arr = arr.copy()
                if np.any(nans):
                    mask = ~nans
                    if np.any(mask):
                        x = np.arange(len(arr))
                        # Use nearest-neighbor interpolation to fill NaNs for filtering
                        f_fill = interp1d(x[mask], arr[mask], kind='nearest', bounds_error=False, fill_value="extrapolate")
                        temp_arr[nans] = f_fill(x[nans])
                
                # Pad to avoid zero-padding issues at the edges
                padded = np.pad(temp_arr, (1, 1), mode='edge')
                filtered = medfilt(padded, kernel_size=3)
                arr = filtered[1:-1]
                
                # Restore original NaNs for large gaps
                if np.any(nans):
                    arr[nans] = np.nan
        
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
        return np.mean(power_array) if len(power_array) > 0 else 0.0
    
    # 30-second rolling average
    window = np.ones(30) / 30
    roll_avg = np.convolve(power_array, window, mode='valid')
    
    # 4th power, mean, and 4th root
    np_val = np.mean(roll_avg ** 4) ** 0.25
    return float(np_val)

def calculate_tss(np_val, duration_s, ftp):
    """
    Calculate Training Stress Score (TSS).
    TSS = (duration_s * NP * IF) / (FTP * 3600) * 100
    Since IF = NP / FTP:
    TSS = (duration_s * NP * (NP / FTP)) / (FTP * 36)
    TSS = (duration_s * NP^2) / (FTP^2 * 36)
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
        # y[0] = b[0]*x[0] + zi[0]
        # We want y[0] = (1/tau)*x[0] + (1 - 1/tau)*initial
        # So zi[0] = (1 - 1/tau)*initial
        zi = np.array([(1.0 - 1.0 / tau) * initial])
        y, _ = lfilter(b, a, data, zi=zi)
        return y

    ctl_values = ewma(x, 42, initial_ctl)
    atl_values = ewma(x, 7, initial_atl)
    
    return ctl_values.tolist(), atl_values.tolist()
