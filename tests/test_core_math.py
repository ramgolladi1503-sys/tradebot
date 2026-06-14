import numpy as np
from core.math.kalman_filter import KalmanFilter
from core.math.mean_reversion import calculate_ou_half_life

def test_kalman_filter_initialization():
    kf = KalmanFilter()
    assert not kf.is_initialized
    hr, intercept, error = kf.update(100.0, 50.0)
    assert kf.is_initialized
    assert hr == 2.0
    assert intercept == 0.0
    assert error == 0.0

def test_kalman_filter_convergence():
    kf = KalmanFilter(delta=1e-5, wt=1e-3)
    # Simulate y = 5.0 + 2.0 * x + noise
    np.random.seed(42)
    x = np.linspace(10, 100, 100)
    y = 5.0 + 2.0 * x + np.random.normal(0, 0.5, 100)
    
    hr, intercept = 0.0, 0.0
    for price_y, price_x in zip(y, x):
        hr, intercept, _ = kf.update(price_y, price_x)
        
    # Check if the filter converges close to true parameters
    assert np.isclose(hr, 2.0, atol=0.2)
    assert np.isclose(intercept, 5.0, atol=2.0)

def test_ou_half_life_mean_reverting():
    # Simulate mean-reverting process
    np.random.seed(42)
    z = [0.0]
    for i in range(1000):
        # dz = -0.1 * z * dt + noise
        dz = -0.1 * z[-1] + np.random.normal(0, 1.0)
        z.append(z[-1] + dz)
        
    hl = calculate_ou_half_life(z)
    # Half-life should be around -ln(2) / -0.1 = 6.93
    assert 5.0 < hl < 9.0

def test_ou_half_life_random_walk():
    # Simulate random walk
    np.random.seed(42)
    z = np.cumsum(np.random.normal(0, 1.0, 1000))
    hl = calculate_ou_half_life(z)
    # Random walk is not mean-reverting (or has extremely long half-life)
    assert hl == float('inf') or hl > 200.0

def test_ou_half_life_short_series():
    assert calculate_ou_half_life([1.0, 2.0]) == float('inf')
    assert calculate_ou_half_life(None) == float('inf')
