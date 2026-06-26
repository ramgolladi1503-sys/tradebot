import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch
from scripts.analyze_entropy_truth_soak import analyze_candidate, analyze

def test_analyze_empty_runtime(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("scripts.analyze_entropy_truth_soak.Path", lambda x: tmp_path / x)
    (tmp_path / "runtime").mkdir(exist_ok=True)
    
    with pytest.raises(SystemExit) as exc:
        analyze()
    assert exc.value.code == 0
    out, err = capsys.readouterr()
    assert "OFFHOURS_READY_ONLY" in out

def test_fallback_top_opportunity_exits_nonzero():
    data = {
        "data_quality_state": "FALLBACK",
        "display_bucket": "TOP_OPPORTUNITY",
        "market_entropy_raw": 0.5,
        "score_eligible": True
    }
    res = analyze_candidate(data)
    assert "bad_feed_in_top_opportunities" in res["violations"]

def test_stale_quote_eligible_exits_nonzero():
    data = {
        "quote_age_sec": 3.5,
        "score_eligible": True,
        "market_entropy_raw": 0.5,
        "data_quality_state": "OK"
    }
    res = analyze_candidate(data)
    assert "stale_quote_eligible" in res["violations"]

def test_valid_clean_candidate():
    data = {
        "quote_age_sec": 1.0,
        "score_eligible": True,
        "market_entropy_raw": 0.5,
        "data_quality_state": "OK",
        "regime_probabilities": {"A": 0.5, "B": 0.5}
    }
    res = analyze_candidate(data)
    assert not res["violations"]

def test_invalid_prob_vector_uncertain_false():
    data = {
        "quote_age_sec": 1.0,
        "score_eligible": True,
        "market_entropy_raw": 0.5,
        "data_quality_state": "OK",
        "regime_probabilities": {"A": 0.5, "B": 0.4},
        "market_regime_uncertain": False
    }
    res = analyze_candidate(data)
    assert "invalid_prob_uncertain_false" in res["violations"]

def test_invalid_prob_vector_uncertain_true():
    data = {
        "quote_age_sec": 1.0,
        "score_eligible": True,
        "market_entropy_raw": 0.5,
        "data_quality_state": "OK",
        "regime_probabilities": {"A": 0.5, "B": 0.4},
        "market_regime_uncertain": True
    }
    res = analyze_candidate(data)
    assert "invalid_prob_uncertain_false" not in res["violations"]
