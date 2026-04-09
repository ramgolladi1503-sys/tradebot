from core.candidate_scoring import score_candidate


def _base_candidate():
    return {
        "trade_id": "t1",
        "builder_confidence": 0.82,
        "confidence": 0.82,
        "global_confidence": 0.80,
        "trade_alignment": 0.78,
        "trade_score_detail": {"confluence_score": 0.76},
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target": 112.0,
        "volume": 120000,
        "oi": 250000,
        "spread_pct": 0.004,
        "quote_age_sec": 0.5,
        "regime": "TREND",
        "market_open": True,
        "quote_ok": True,
    }


def test_fallback_candidate_score_is_capped():
    candidate = _base_candidate()
    candidate["row_kind"] = "recovered_fallback"
    scored = score_candidate(candidate, {}, {})
    assert scored["candidate_class"] == "fallback"
    assert scored["rank_score"] <= 0.39
    assert scored["opportunity_score"] <= 0.39
    assert "class_fallback" in scored["penalty_reasons"]
