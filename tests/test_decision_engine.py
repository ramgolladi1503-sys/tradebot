from core.decision_engine import evaluate_candidate_decision


def _base_candidate(**overrides):
    base = {
        "trade_id": "T-DECIDE-1",
        "symbol": "NIFTY",
        "candidate_status": "near_executable",
        "candidate_class": "real",
        "execution_status": "scored",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "display_entry": 150.0,
        "display_entry_status": "displayable",
        "entry": 150.0,
        "entry_price": 150.0,
        "stop_loss": 120.0,
        "target": 210.0,
        "execution_allowed": True,
        "execution_ok": True,
        "eligible_for_execution": True,
        "tradable": True,
        "hard_blockers": [],
        "blockers": [],
        "quote_ok": True,
        "quote_age_sec": 0.5,
        "best_bid": 149.8,
        "best_ask": 150.2,
        "ltp": 150.0,
        "quote_completeness": "FULL",
        "spread_source": "live_quote",
        "spread_pct": 0.003,
        "volume": 5000,
        "builder_confidence": 0.72,
        "gating_final_confidence": 0.74,
        "sizing_confluence_score": 0.70,
        "rank_score": 0.72,
        "confidence_final": 0.74,
        "regime": "TREND",
        "side": "BUY",
        "strategy_family": "ensemble_opt",
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_strong_candidate_executes():
    result = evaluate_candidate_decision(_base_candidate())
    assert result["decision_action"] == "EXECUTE"


def test_weak_signal_candidate_queues_not_executes():
    result = evaluate_candidate_decision(
        _base_candidate(
            candidate_class="softened",
            reject_reason="weak_signal",
            source_flags={"soft_reject_reason": "weak_signal"},
            builder_confidence=0.82,
            gating_final_confidence=0.85,
            rank_score=0.80,
        )
    )
    assert result["decision_action"] == "QUEUE"
    assert result["decision_reason"] == "weak_signal_queue_only"
    assert result["permission"] == "QUEUE_ONLY"
    assert result["final_action"] == "QUEUE_ONLY"


def test_no_signal_softened_candidate_never_executes():
    result = evaluate_candidate_decision(
        _base_candidate(
            candidate_class="softened",
            entry_block_code="no_signal",
            source_flags={"soft_reject_reason": "no_signal", "candidate_origin": "softened_builder_path"},
            builder_confidence=0.91,
            gating_final_confidence=0.92,
            rank_score=0.89,
        )
    )
    assert result["decision_action"] in {"QUEUE", "REJECT"}
    assert result["decision_action"] != "EXECUTE"
    assert result["decision_reason"] == "weak_signal_queue_only"


def test_synthetic_candidate_rejects():
    result = evaluate_candidate_decision(
        _base_candidate(
            candidate_class="synthetic",
            strategy_family="synthetic_advisory",
        )
    )
    assert result["decision_action"] == "REJECT"
    assert result["decision_reason"] == "non_real_candidate_class"


def test_invalid_geometry_rejects():
    result = evaluate_candidate_decision(
        _base_candidate(
            execution_entry=150.0,
            stop_loss=220.0,
            target=210.0,
        )
    )
    assert result["decision_action"] == "REJECT"
    assert "invalid_level_geometry" in result["readiness_reasons"]


def test_degraded_feed_blocks_execute():
    result = evaluate_candidate_decision(
        _base_candidate(
            quote_age_sec=10.0,
            spread_pct=0.05,
            volume=0,
        )
    )
    assert result["decision_action"] != "EXECUTE"
    assert result["feed"]["feed_state"] in {"degraded", "invalid"}


def test_feed_liquidity_quality_is_not_flat_for_quote_valid_rows():
    low = evaluate_candidate_decision(_base_candidate(volume=1_000))
    high = evaluate_candidate_decision(_base_candidate(volume=250_000))
    assert high["feed"]["liquidity_quality"] > low["feed"]["liquidity_quality"]
