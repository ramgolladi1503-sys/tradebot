import numpy as np

def get_weights(d, size):
    """
    Returns weights for the fractional differentiation.
    w_k = -w_{k-1} * (d - k + 1) / k
    """
    w = [1.0]
    for k in range(1, size):
        w.append(-w[-1] * (d - k + 1) / k)
    return np.array(w).reshape(-1, 1)

def frac_diff_ffd(series, d, thres=1e-5):
    """
    Fixed-Width Window Fractional Differentiation (FFD).
    
    Args:
        series (np.array): A 1D or 2D array of prices.
        d (float): The differencing factor (e.g., 0.4).
        thres (float): The weight threshold to truncate the window.
        
    Returns:
        np.array: The fractionally differentiated series.
    """
    # Compute weights until the threshold is met
    w = [1.0]
    k = 1
    while True:
        weight = -w[-1] * (d - k + 1) / k
        if abs(weight) < thres:
            break
        w.append(weight)
        k += 1
        
    w = np.array(w[::-1]).reshape(-1, 1) # Reverse to align with chronological data
    window_size = len(w)
    
    if series.ndim == 1:
        series = series.reshape(-1, 1)
        
    n_samples, n_features = series.shape
    out = np.zeros((n_samples, n_features))
    out[:] = np.nan
    
    # Apply weights
    for i in range(window_size - 1, n_samples):
        window = series[i - window_size + 1 : i + 1]
        out[i] = np.sum(w * window, axis=0)
        
    return out
