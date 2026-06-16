import pytest
import numpy as np
from unittest.mock import MagicMock
from ml.meta_labeler import MetaLabeler

def test_meta_labeler_safe_fallback():
    # If model_path doesn't exist, it should fallback safely and approve all trades
    labeler = MetaLabeler(model_path="invalid/path/does/not/exist.pkl")
    assert not labeler.is_loaded
    
    trade = {"confidence": 80, "lot_size": 2}
    context = {"vix": 18.0}
    
    approved, prob = labeler.evaluate_trade(trade, context)
    assert approved is True
    assert prob == 1.0

def test_meta_labeler_feature_extraction():
    labeler = MetaLabeler(model_path=None)
    trade = {"confidence": 75, "lot_size": 3.0}
    context = {
        "vix": 12.5,
        "dealer_gamma_exposure": 1000.5,
        "cumulative_volume_delta": -500.0
    }
    
    features = labeler._extract_features(trade, context)
    assert features == [75.0, 12.5, 1000.5, -500.0, 3.0]

def test_meta_labeler_evaluation_mocked():
    labeler = MetaLabeler(model_path=None)
    
    # Mock a loaded model
    mock_model = MagicMock()
    # predict_proba returns a 2D array: [[prob_class_0, prob_class_1]]
    mock_model.predict_proba.return_value = np.array([[0.2, 0.8]])
    
    labeler.model = mock_model
    labeler.is_loaded = True
    
    trade = {"confidence": 80}
    # Required prob 0.9 -> should fail (0.8 < 0.9)
    approved, prob = labeler.evaluate_trade(trade, {}, required_prob=0.9)
    assert approved is False
    assert prob == 0.8
    
    # Required prob 0.6 -> should pass (0.8 >= 0.6)
    approved2, prob2 = labeler.evaluate_trade(trade, {}, required_prob=0.6)
    assert approved2 is True
    assert prob2 == 0.8
