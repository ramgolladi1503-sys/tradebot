import numpy as np

def calculate_ou_half_life(spread_series):
    """
    Calculates the Ornstein-Uhlenbeck mean-reversion half-life of a spread.
    
    dz = theta * (mu - z) * dt + sigma * dW
    We run an OLS regression: z(t) - z(t-1) = a + b * z(t-1) + epsilon
    where b = -theta * dt.
    Half-life = -ln(2) / b
    
    Args:
        spread_series (list or np.array): Time series of the spread.
        
    Returns:
        float: The half-life in periods. Returns infinity if the series is not mean-reverting (b >= 0).
    """
    if spread_series is None or len(spread_series) < 3:
        return float('inf')
        
    # Convert to numpy array
    z = np.array(spread_series, dtype=float)
    
    # Calculate differences (dz) and lagged values
    dz = np.diff(z)
    z_lag = z[:-1]
    
    # OLS Regression: dz = a + b * z_lag
    # We add a constant column to z_lag for the intercept 'a'
    A = np.vstack([z_lag, np.ones(len(z_lag))]).T
    
    try:
        # Solve A * x = dz
        # np.linalg.lstsq returns a tuple; the first element contains the coefficients [b, a]
        coefs = np.linalg.lstsq(A, dz, rcond=None)[0]
        b = coefs[0]
        a = coefs[1]
    except Exception:
        return float('inf')
        
    # If b is extremely close to 0 or positive, it is a random walk or diverging
    if b >= -1e-4:
        return float('inf')
        
    # Half-life calculation
    half_life = -np.log(2) / b
    return half_life
