import pytest
import math
from core.entropy_contract import shannon_entropy, max_entropy, normalized_entropy, entropy_diagnostics

def test_entropy_one_hot():
    probs = {"A": 1.0, "B": 0.0, "C": 0.0}
    assert math.isclose(shannon_entropy(probs), 0.0, abs_tol=1e-6)
    assert math.isclose(normalized_entropy(probs), 0.0, abs_tol=1e-6)

def test_entropy_uniform_5_regimes():
    probs = {"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2}
    ent = shannon_entropy(probs)
    assert math.isclose(ent, math.log(5), abs_tol=1e-6)
    assert math.isclose(normalized_entropy(probs), 1.0, abs_tol=1e-6)

def test_entropy_invalid_sum():
    probs = {"A": 0.5, "B": 0.6}
    with pytest.raises(ValueError):
        shannon_entropy(probs)

def test_entropy_negative_prob():
    probs = {"A": -0.1, "B": 1.1}
    with pytest.raises(ValueError):
        shannon_entropy(probs)

def test_entropy_nan_prob():
    probs = {"A": float('nan'), "B": float('nan')}
    with pytest.raises(ValueError):
        shannon_entropy(probs)

def test_max_entropy():
    assert math.isclose(max_entropy(5), math.log(5), abs_tol=1e-6)
    
def test_entropy_diagnostics():
    probs = {"A": 0.2, "B": 0.8}
    diag = entropy_diagnostics(probs)
    assert "entropy" in diag
    assert "normalized_entropy" in diag
    assert "max_entropy" in diag
    assert diag["num_states"] == 2
