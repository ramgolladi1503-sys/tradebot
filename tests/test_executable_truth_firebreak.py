from core.executable_truth import classify_executable_truth
from core.execution_quality import evaluate_pretrade_execution_quality


def _clean_candidate(**overrides):
    candidate = {
        "trade_id": "T1",
        "symbol": "NIFTY",
        "candidate_class": "EXECUTABLE",
        "execution_allowed": True,
        "tradable": True,
        "selected_for_execution": True,
        "execution_entry": 101.0,
        "execution_entry_status": "executable",
        "data_state": "DATA_OK",
        "fresh_quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "data_confidence": 0.90,
        "best_bid": 100.9,
        "best_ask": 101.1,
        "spread_pct": 0.002,
        "volume": 50000,
        "current_volume": 50000,
        "oi": 100000,
        "quote_ok": True,
        "source_flags": {},
    }
    candidate.update(overrides)
    return candidate


def test_clean_fresh_candidate_is_allowed_by_truth_classifier():
    decision = classify_executable_truth(_clean_candidate())
    assert decision.execution_allowed is True
    assert decision.reason_code == "ok"


def test_fallback_candidate_is_blocked_even_with_entry():
    candidate = _clean_candidate(fallback_candidate=True, source_flags={"fallback_candidate": True})
    decision = classify_executable_truth(candidate)
    quality = evaluate_pretrade_execution_quality(candidate)
    assert decision.execution_allowed is False
    assert decision.reason_code == "fallback_driven_data"
    assert quality.execution_ok is False
    assert quality.order_policy == "advisory"
    assert quality.reason_code == "fallback_driven_data"


def test_recovered_fallback_source_is_blocked():
    candidate = _clean_candidate(source_flags={"recovered_fallback": True, "chain_source": "recovered_fallback"})
    decision = classify_executable_truth(candidate)
    quality = evaluate_pretrade_execution_quality(candidate)
    assert decision.execution_allowed is False
    assert decision.reason_code == "fallback_driven_data"
    assert quality.execution_ok is False


def test_degraded_advisory_data_is_blocked_in_paper_too():
    candidate = _clean_candidate(source_flags={"execution_block_type": "advisory", "runtime_mode": "PAPER"})
    quality = evaluate_pretrade_execution_quality(candidate)
    assert quality.execution_ok is False
    assert quality.order_policy == "advisory"
    assert quality.reason_code == "degraded_data"


def test_stale_quote_is_blocked():
    candidate = _clean_candidate(data_state="DATA_STALE", fresh_quote_ok=False)
    decision = classify_executable_truth(candidate)
    quality = evaluate_pretrade_execution_quality(candidate)
    assert decision.execution_allowed is False
    assert "stale_quote" in decision.reasons
    assert quality.execution_ok is False
    assert quality.reason_code == "stale_quote"


def test_unverified_spread_is_blocked():
    candidate = _clean_candidate(spread_ok=False, best_bid=None, best_ask=None)
    decision = classify_executable_truth(candidate)
    quality = evaluate_pretrade_execution_quality(candidate)
    assert decision.execution_allowed is False
    assert decision.reason_code == "unverified_spread"
    assert quality.execution_ok is False


def test_low_data_confidence_is_blocked():
    candidate = _clean_candidate(data_confidence=0.01)
    decision = classify_executable_truth(candidate)
    quality = evaluate_pretrade_execution_quality(candidate)
    assert decision.execution_allowed is False
    assert decision.reason_code == "low_data_confidence"
    assert quality.execution_ok is False
