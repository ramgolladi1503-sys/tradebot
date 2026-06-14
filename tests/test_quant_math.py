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
    # The remaining 200 sell is left in an uncompleted bucket and ignored.
    # Total = (1.0 + 0.0 + 0.75) / 3 = 1.75 / 3 = 0.5833333333333334
    assert np.isclose(vpin, 0.5833333333333334)

def test_fractional_differentiation():
    # Linear series
    series = np.arange(10, dtype=float)
    
    weights = get_weights(0.5, 5)
    assert weights.shape[0] == 5
    
    diff = frac_diff_ffd(series, d=0.5, thres=1e-1)
    # The output should have nans at the beginning based on window size
    assert diff.shape[0] == 10
    assert np.isnan(diff[0][0])
    
    # Check actual differentiated values for thres=1e-1
    # w0 = 1.0, w1 = -0.5, w2 = -0.125
    # w is applied reversed: [-0.125, -0.5, 1.0] to [7.0, 8.0, 9.0]
    expected_val = 7.0 * -0.125 + 8.0 * -0.5 + 9.0 * 1.0
    assert np.isclose(diff[-1][0], expected_val)
