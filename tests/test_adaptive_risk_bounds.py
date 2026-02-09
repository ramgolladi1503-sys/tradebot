from core.adaptive_risk import compute_multiplier


def test_bounds():
    assert 0.1 <= compute_multiplier(1.0, -0.5, 10.0, 0.1, 1.0, 2.0) <= 1.0
