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
    assert hmm.means_.shape[0] == 2
    
    preds = hmm.predict(X)
    assert preds.shape[0] == 100
    # True behavioral proof: HMM should separate the two distinct clusters
    cluster_0_preds = preds[:50]
    cluster_1_preds = preds[50:]
    # Either all 0s and all 1s, or vice versa
    assert np.unique(cluster_0_preds).shape[0] == 1
    assert np.unique(cluster_1_preds).shape[0] == 1
    assert cluster_0_preds[0] != cluster_1_preds[0]

def test_calculate_vpin():
    tick_volumes = np.array([100, 200, 150, 50, 300])
    tick_price_changes = np.array([1, 1, -1, 0, -1]) # Buy, Buy, Sell, Split, Sell
    bucket_volume = 200
    
    vpin = calculate_vpin(tick_volumes, tick_price_changes, bucket_volume)
    # Proof: 
    # B1: 200 buy -> 1.0
    # B2: 100 buy, 100 sell -> 0.0
    # B3: 25 buy, 175 sell -> 0.75
    # B4: 200 sell -> 1.0
    # Total = 2.75 / 4 = 0.6875
    assert np.isclose(vpin, 0.6875)

def test_fractional_differentiation():
    # Linear series
    series = np.arange(10, dtype=float)
    
    weights = get_weights(0.5, 5)
    assert weights.shape[0] == 5
    
    diff = frac_diff_ffd(series, d=0.5, thres=1e-3)
    # The output should have nans at the beginning based on window size
    assert diff.shape[0] == 10
    assert np.isnan(diff[0][0])
    
    # Check actual differentiated values
    # w0 = 1.0, w1 = -0.5, w2 = -0.125, w3 = -0.0625, w4 = -0.0390625
    expected_val = 9.0 * 1.0 + 8.0 * -0.5 + 7.0 * -0.125 + 6.0 * -0.0625 + 5.0 * -0.0390625
    assert np.isclose(diff[-1][0], expected_val)
