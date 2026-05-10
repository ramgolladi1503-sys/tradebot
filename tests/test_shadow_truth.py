from __future__ import annotations

from core.shadow_truth import shadow_evaluate_candidate, shadow_evaluate_candidates


def _candidate(**overrides):
    row = {
        "trade_id": "T-SHADOW",
        "symbol": "NIFTY",
        "opt_ltp": 120.0,
        "current_ltp": 120.0,
        "best_bid": 119.8,
        "best_ask": 120.2,
        "spread_pct": 0.003,
        "liquidity_score": 0.82,
        "quote_age_sec": 0.3,
        "max_quote_age_sec": 2.0,
        "quote_source": "live_broker",
        "spread_source": "live_book",
        "liquidity_source": "live_book",
        "contract_exact_match": True,
        "execution_entry": 120.2,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "selected_for_execution": True,
    }
    row.update(overrides)
    return row


def test_shadow_truth_reports_no_behavior_change_for_clean_candidate():
    decision = shadow_evaluate_candidate(_candidate(), index=0)

    assert decision.shadow_execution_truth_allowed is True
    assert decision.drift_type == "NO_DRIFT"
    assert decision.drift_severity == "INFO"


def test_shadow_truth_flags_current_selected_dirty_candidate_as_critical():
    decision = shadow_evaluate_candidate(
        _candidate(
            trade_id="T-DIRTY",
            phase2_spread_fallback_used=True,
            spread_source="fallback_default",
        ),
        index=0,
    )

    assert decision.shadow_execution_truth_allowed is False
    assert decision.drift_type == "CURRENT_ALLOWS_SHADOW_BLOCKS"
    assert decision.drift_severity == "CRITICAL"
    assert decision.recommended_action == "investigate_before_execution"
    assert "fallback_spread" in decision.shadow_blockers


def test_shadow_truth_flags_execution_allowed_shadow_block_as_high_when_not_selected():
    decision = shadow_evaluate_candidate(
        _candidate(
            selected_for_execution=False,
            eligible_for_execution=False,
            execution_status="blocked",
            quote_source="unknown",
            execution_allowed=True,
        ),
        index=0,
    )

    assert decision.shadow_execution_truth_allowed is False
    assert decision.drift_severity == "HIGH"
    assert decision.drift_type == "EXECUTION_ALLOWED_SHADOW_BLOCKS"


def test_shadow_truth_batch_payload_is_shadow_only():
    payload = shadow_evaluate_candidates(
        [
            _candidate(trade_id="T-CLEAN"),
            _candidate(
                trade_id="T-DIRTY",
                phase2_liquidity_fallback_used=True,
                liquidity_source="fallback_default",
            ),
        ]
    )

    assert payload["mode"] == "SHADOW_ONLY"
    assert payload["behavior_changed"] is False
    assert payload["total_candidates"] == 2
    assert payload["severity_counts"]["CRITICAL"] == 1
    assert payload["critical_drifts"][0]["ref"] == "T-DIRTY"
