from __future__ import annotations

from core.executable_truth import classify_executable_truth
from core.symbol_execution_safety import (
    SYMBOL_EXECUTION_SAFETY_BLOCK_REASON,
    SYMBOL_FEED_UNSAFE_REASON,
    SYMBOL_FEED_DEPENDENCIES_MISSING_REASON,
    SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON,
    SYMBOL_FEED_DEPENDENCY_ID_MISSING_REASON,
    SYMBOL_MISSING_REASON,
    SYMBOL_OPTION_BLOCKED_REASON,
    SYMBOL_STALE_OPTION_REASON,
    SYMBOL_SUBSCRIPTION_FAILED_REASON,
    classify_symbol_execution_safety,
    resolve_candidate_symbol,
)


def _candidate(**overrides):
    candidate = {
        "symbol": "NIFTY",
        "candidate_class": "EXECUTABLE",
        "execution_entry_status": "executable",
        "strategy_family": "trend_pullback",
        "side": "BUY",
        "signal_score": 0.82,
        "setup_score": 0.80,
        "trigger_score": 0.81,
        "confluence_score": 0.83,
        "regime_fit": 0.84,
        "signal_valid": True,
        "signal_strength": 0.8,
        "fresh_quote_ok": True,
        "spread_ok": True,
        "liquidity_ok": True,
        "data_confidence": 0.95,
        "current_ltp": 100.0,
        "ltp": 100.0,
        "best_bid": 99.8,
        "best_ask": 100.2,
        "quote_source": "kite_ws",
        "option_ltp_source": "kite_ws",
        "quote_validation_status": "OK",
        "quote_age_sec": 0.5,
        "quote_ts_age_sec": 0.5,
        "quote_report_age_sec": 0.5,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
        "symbol_feed_ok_by_symbol": {"NIFTY": True},
        "feed_ok": True,
        "ws_connected": True,
        "effective_ws_connected": True,
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 1.0,
        "subscribed_option_tokens_count": 2,
    }
    candidate.update(overrides)
    return candidate


def test_resolve_candidate_symbol_uses_direct_symbol_first():
    assert resolve_candidate_symbol(_candidate(symbol="banknifty", underlying="NIFTY")) == "BANKNIFTY"


def test_symbol_execution_safety_allows_clean_symbol_feed():
    decision = classify_symbol_execution_safety(_candidate())

    assert decision.execution_allowed is True
    assert decision.reason_code == "ok"
    assert decision.reasons == ()
    assert decision.symbol == "NIFTY"
    assert decision.context["feed_health_truth"]["feed_ok"] is True
    assert decision.context["read_only"] is True
    assert decision.context["is_order_action"] is False
    assert decision.context["broker_api_called"] is False
    assert decision.context["allowed_for_live_execution"] is False


def test_symbol_execution_safety_blocks_missing_symbol():
    candidate = _candidate(symbol=None, underlying=None, underlying_symbol=None, index_symbol=None)

    decision = classify_symbol_execution_safety(candidate)

    assert decision.execution_allowed is False
    assert decision.reason_code == SYMBOL_EXECUTION_SAFETY_BLOCK_REASON
    assert decision.reasons == (SYMBOL_MISSING_REASON,)
    assert decision.context["read_only"] is True
    assert decision.context["is_order_action"] is False
    assert decision.context["broker_api_called"] is False
    assert decision.context["allowed_for_live_execution"] is False


def test_symbol_execution_safety_blocks_stale_symbol_option_ticks():
    decision = classify_symbol_execution_safety(
        _candidate(option_last_tick_age_by_symbol={"NIFTY": 12.0})
    )

    assert decision.execution_allowed is False
    assert SYMBOL_STALE_OPTION_REASON in decision.reasons
    assert decision.context["feed_health_truth"]["symbols"][0]["feed_ok"] is False


def test_symbol_execution_safety_ignores_aggregate_degradation_for_healthy_symbol():
    decision = classify_symbol_execution_safety(_candidate(
        feed_ok=False,
        feed_ok_scope="symbol_aggregate",
        global_feed_blocked=False,
        option_feed_block_reason_by_symbol={"NIFTY": "OK", "TCS": "STALE"},
        option_last_tick_age_by_symbol={"NIFTY": 0.5, "TCS": 900.0},
    ))

    assert decision.execution_allowed is True
    assert decision.reasons == ()
    assert decision.context["feed_health_truth"]["context"]["monitored_degraded_symbols"] == ["TCS"]


def test_symbol_execution_safety_does_not_infer_global_clear_from_symbol_maps():
    decision = classify_symbol_execution_safety(_candidate(
        feed_ok=False,
        option_feed_block_reason_by_symbol={"NIFTY": "OK", "TCS": "STALE"},
        option_last_tick_age_by_symbol={"NIFTY": 0.5, "TCS": 900.0},
    ))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_UNSAFE_REASON in decision.reasons
    assert decision.context["feed_health_truth"]["context"]["feed_ok_scope"] == "global_or_unknown"


def test_declared_index_dependencies_ignore_unrelated_stock_domain_degradation():
    decision = classify_symbol_execution_safety(_candidate(
        required_feed_domains=["INDEX_SPOT", "INDEX_FUTURES", "INDEX_OPTIONS"],
        feed_health={
            "domain_health_by_domain": {
                "INDEX_SPOT": {"state": "HEALTHY"},
                "INDEX_FUTURES": {"state": "HEALTHY"},
                "INDEX_OPTIONS": {"state": "HEALTHY"},
                "STOCK_SPOT": {"state": "DEGRADED"},
                "STOCK_OPTIONS": {"state": "DEGRADED"},
            }
        },
    ))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCY_ID_MISSING_REASON in decision.reasons
    truth = decision.context["feed_health_truth"]
    assert truth["context"]["required_domains"] == ["INDEX_SPOT", "INDEX_FUTURES", "INDEX_OPTIONS"]
    assert truth["overall_state"] == "OPERATIONAL_DEGRADED"
    assert decision.context["candidate_feed_dependency"]["registry_coverage"] is False
    assert truth["domains"]["stock_options"]["state"] == "DEGRADED"


def test_declared_missing_index_futures_domain_blocks_candidate():
    decision = classify_symbol_execution_safety(_candidate(
        required_feed_domains=["INDEX_SPOT", "INDEX_FUTURES", "INDEX_OPTIONS"],
        feed_health={
            "domain_health_by_domain": {
                "INDEX_SPOT": {"state": "HEALTHY"},
                "INDEX_OPTIONS": {"state": "HEALTHY"},
            }
        },
    ))

    assert decision.execution_allowed is False
    assert "required_domain_unknown:INDEX_FUTURES" in decision.context["feed_health_truth"]["reasons"]


def test_source_flag_feed_domain_declaration_is_consumed_and_invalid_declaration_blocks():
    declared = _candidate(source_flags={
        "candidate_id": "INTRADAY_OPENING_DRIVE_V1",
        "required_feed_domains": ["INDEX_SPOT"],
        "feed_health": {"domain_health_by_domain": {"INDEX_SPOT": {"state": "HEALTHY"}}},
    })
    decision = classify_symbol_execution_safety(declared)
    malformed = classify_symbol_execution_safety(_candidate(required_feed_domains=42))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON in decision.reasons
    assert decision.context["feed_health_truth"]["context"]["required_domains"] == ["INDEX_SPOT"]
    assert decision.context["candidate_feed_dependency"]["reason"] == "CANDIDATE_FEED_DEPENDENCY_DECLARATION_MISMATCH"
    assert malformed.execution_allowed is False
    assert "required_domain_unknown:__INVALID_REQUIRED_FEED_DOMAINS__" in malformed.context["feed_health_truth"]["reasons"]


def test_c1_c2_exact_candidate_ids_are_blocked_at_execution_safety_boundary():
    entries = (
        ("C1_INTRADAY_15M_IMPULSE", "INDEX_SPOT", "INDEX_FUTURES"),
        ("ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE", "INDEX_SPOT", "INDEX_FUTURES"),
        ("C2_OVERNIGHT_TREND", "INDEX_SPOT", "INDEX_FUTURES"),
        ("ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT", "INDEX_SPOT", "INDEX_FUTURES"),
    )
    for candidate_id, *domains in entries:
        decision = classify_symbol_execution_safety(_candidate(
            candidate_id=candidate_id,
            required_feed_domains=domains,
            feed_health={
                "domain_health_by_domain": {
                    "INDEX_SPOT": {"state": "HEALTHY"},
                    "INDEX_FUTURES": {"state": "HEALTHY"},
                    "STOCK_OPTIONS": {"state": "STALE"},
                }
            },
        ))
        assert decision.execution_allowed is False
        assert SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON in decision.reasons
        assert decision.context["candidate_feed_dependency"]["status"] == "PARTIAL_DECLARATION"
        assert decision.context["candidate_feed_dependency"]["execution_eligible"] is False
        assert decision.context["candidate_feed_dependency"]["required_domains"] == domains


def test_unknown_candidate_family_with_structured_domain_health_blocks_at_execution_boundary():
    decision = classify_symbol_execution_safety(_candidate(
        candidate_family="UNREGISTERED_FAMILY",
        required_feed_domains=["INDEX_SPOT"],
        feed_health={"domain_health_by_domain": {"INDEX_SPOT": {"state": "HEALTHY"}}},
    ))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON in decision.reasons
    assert decision.context["candidate_feed_dependency"]["status"] == "UNKNOWN_BLOCKED"


def test_opaque_lineage_id_without_registered_family_cannot_fall_through_legacy_pass():
    decision = classify_symbol_execution_safety(_candidate(candidate_id="signal-opaque-001"))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON in decision.reasons
    assert decision.context["candidate_feed_dependency"]["status"] == "UNKNOWN_BLOCKED"


def test_opaque_lineage_id_uses_exact_registered_strategy_id_and_remains_partial():
    decision = classify_symbol_execution_safety(_candidate(
        candidate_id="signal-c1-opaque-001",
        strategy_id="C1_INTRADAY_15M_IMPULSE",
    ))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON in decision.reasons
    assert decision.context["candidate_feed_dependency"]["candidate_id"] == "C1_INTRADAY_15M_IMPULSE"
    assert decision.context["candidate_feed_dependency"]["status"] == "PARTIAL_DECLARATION"


def test_identity_health_without_registered_dependency_identity_blocks():
    decision = classify_symbol_execution_safety(_candidate(feed_health={
        "feed_health_by_identity": {
            "NIFTY 50": {"domain": "INDEX_SPOT", "state": "HEALTHY"}
        }
    }))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCY_ID_MISSING_REASON in decision.reasons
    assert decision.context["candidate_feed_dependency"]["status"] == "UNKNOWN_BLOCKED"


def test_structured_domain_evidence_requires_nonempty_explicit_candidate_dependencies():
    domain_health = {"INDEX_SPOT": {"state": "HEALTHY"}}
    undeclared = classify_symbol_execution_safety(_candidate(feed_health={
        "domain_health_by_domain": domain_health,
    }))
    empty = classify_symbol_execution_safety(_candidate(
        required_feed_domains=[],
        feed_health={"domain_health_by_domain": domain_health},
    ))

    assert undeclared.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCIES_MISSING_REASON in undeclared.reasons
    assert SYMBOL_FEED_DEPENDENCY_ID_MISSING_REASON in undeclared.reasons
    assert empty.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCIES_MISSING_REASON in empty.reasons


def test_symbol_only_legacy_feed_payload_without_domain_evidence_remains_supported():
    decision = classify_symbol_execution_safety(_candidate())

    assert decision.execution_allowed is True


def test_opaque_candidate_id_without_family_is_unknown_blocked():
    decision = classify_symbol_execution_safety(_candidate(candidate_id="signal-20260930-001"))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_DEPENDENCY_AUTHORITY_BLOCK_REASON in decision.reasons
    assert decision.context["candidate_feed_dependency"]["status"] == "UNKNOWN_BLOCKED"
    assert decision.context["candidate_feed_dependency"]["registry_coverage"] is False
    assert decision.context["feed_health_truth"]["context"]["required_domains"] == []


def test_symbol_execution_safety_still_blocks_global_transport_failure():
    decision = classify_symbol_execution_safety(_candidate(ws_connected=False, effective_ws_connected=False))

    assert decision.execution_allowed is False
    assert SYMBOL_FEED_UNSAFE_REASON in decision.reasons


def test_symbol_execution_safety_preserves_subscription_failure_reason():
    decision = classify_symbol_execution_safety(
        _candidate(option_feed_block_reason_by_symbol={"NIFTY": "subscription_failed"})
    )

    assert decision.execution_allowed is False
    assert SYMBOL_OPTION_BLOCKED_REASON in decision.reasons
    assert SYMBOL_SUBSCRIPTION_FAILED_REASON in decision.reasons


def test_executable_truth_blocks_when_symbol_feed_is_stale():
    decision = classify_executable_truth(
        _candidate(option_last_tick_age_by_symbol={"NIFTY": 10.0})
    )

    assert decision.execution_allowed is False
    assert SYMBOL_EXECUTION_SAFETY_BLOCK_REASON in decision.reasons
    assert SYMBOL_STALE_OPTION_REASON in decision.reasons
    assert decision.context["symbol_execution_safety"]["symbol"] == "NIFTY"


def test_executable_truth_allows_clean_symbol_safety_when_other_truths_are_clean():
    decision = classify_executable_truth(_candidate())

    assert decision.execution_allowed is True
    assert decision.reason_code == "ok"
    assert decision.context["symbol_execution_safety"]["execution_allowed"] is True
