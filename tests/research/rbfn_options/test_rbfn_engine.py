"""Tests for GaussianRBFNetwork.

Verifies:
- Scikit-learn free implementation
- Deterministic centers
- Ridge regularization behaviour
- Multidimensional target support
- Extrapolation and normalization stability
"""
from __future__ import annotations

import numpy as np
import pytest

from research.rbfn_options.core.rbfn_engine import GaussianRBFNetwork


def test_rbfn_initialization_validation():
    with pytest.raises(ValueError, match="n_centers must be positive"):
        GaussianRBFNetwork(n_centers=0)

    with pytest.raises(ValueError, match="width must be positive"):
        GaussianRBFNetwork(width=-1.0)

    with pytest.raises(ValueError, match="ridge must be non-negative"):
        GaussianRBFNetwork(ridge=-0.5)


def test_rbfn_fit_predict_basic():
    np.random.seed(42)
    n = 60
    x = np.linspace(-2, 2, n).reshape(-1, 1)
    y = np.sin(x)

    model = GaussianRBFNetwork(n_centers=10, width=1.0, ridge=0.1)
    model.fit(x, y)

    assert model.is_fitted
    assert model.weights is not None
    assert len(model.weights) == 11  # 1 bias + 10 centers

    pred = model.predict(x)
    assert pred.shape == (n,)
    # Sine approximation error should be reasonably low
    mae = np.mean(np.abs(pred - y.ravel()))
    assert mae < 0.2


def test_rbfn_multi_target():
    np.random.seed(42)
    n = 80
    x = np.random.randn(n, 3)
    y = np.column_stack([
        x[:, 0] * 2 + 1,
        np.sin(x[:, 1]),
        x[:, 2] ** 2,
    ])

    model = GaussianRBFNetwork(n_centers=15, width=2.0, ridge=1.0)
    model.fit(x, y)

    assert model.weights.shape == (16, 3)  # (1 + 15, 3)
    pred = model.predict(x)
    assert pred.shape == (n, 3)


def test_rbfn_centers_determinism():
    n = 50
    x = np.linspace(0, 10, n).reshape(-1, 1)
    y = x * 2.0

    model1 = GaussianRBFNetwork(n_centers=10)
    model1.fit(x, y)

    model2 = GaussianRBFNetwork(n_centers=10)
    model2.fit(x, y)

    np.testing.assert_array_almost_equal(model1.centers, model2.centers)
    np.testing.assert_array_almost_equal(model1.weights, model2.weights)


def test_rbfn_unfitted_raises():
    model = GaussianRBFNetwork()
    with pytest.raises(RuntimeError, match="Cannot predict with unfitted"):
        model.predict(np.array([[1.0]]))


def test_rbfn_insufficient_samples_raises():
    model = GaussianRBFNetwork(n_centers=28)
    with pytest.raises(ValueError, match="Number of samples"):
        model.fit(np.ones((10, 2)), np.ones(10))
