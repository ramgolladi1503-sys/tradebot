import numpy as np
from core.math.hmm_regime import GaussianHMM
from core.math.vpin import calculate_vpin
from core.math.fractional_differentiation import frac_diff_ffd, get_weights

def test_gaussian_hmm():
    np.random.seed(42)
    # Generate two distinct states
    state_0 = np.random.normal(loc=[10, 2], scale=[1, 0.1], size=(50, 2))
    state_1 = np.random.normal(loc=[30, 8], scale=[2, 0.5], size=(50, 2))
    X = np.vstack([state_0, state_1])
    
    hmm = GaussianHMM(n_components=2, n_iter=10)
    hmm.fit(X)
    
    assert hmm.is_fitted
    assert len(hmm.means_) == 2
    
    preds = hmm.predict(X)
    assert len(preds) == 100

def test_calculate_vpin():
    tick_volumes = np.array([100, 200, 150, 50, 300])
    tick_price_changes = np.array([1, 1, -1, 0, -1]) # Buy, Buy, Sell, Split, Sell
    bucket_volume = 200
    
    vpin = calculate_vpin(tick_volumes, tick_price_changes, bucket_volume)
    assert 0.0 <= vpin <= 1.0

def test_fractional_differentiation():
    # Linear series
    series = np.arange(10, dtype=float)
    
    weights = get_weights(0.5, 5)
    assert len(weights) == 5
    
    diff = frac_diff_ffd(series, d=0.5, thres=1e-3)
    # The output should have nans at the beginning based on window size
    assert len(diff) == 10
    assert np.isnan(diff[0][0])
