from __future__ import annotations

from core.executable_truth import (
    FALLBACK_DRIVEN_REASON,
    PRICE_MISMATCH_REASON,
    STALE_OPTION_LTP_REASON,
    SUBSCRIPTION_FAILED_REASON,
    classify_executable_truth,
)
from core.execution_quality import evaluate_pretrade_execution_quality
from core.opportunity_engine import annotate_ranked_opportunities, select_top_opportunities


def _candidate(**updates):
    payload = {
        "trade_id": "EDGE41-CANDIDATE",
        "symbol": "NIFTY",
        "candidate_class": "EXECUTABLE",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "execution_entry": 121.5,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "display_entry": 121.5,
        "display_entry_status": "displayable",
        "display_entry_source": "ask",
        "entry_price": 121.5,
        "stop_loss": 115.0,
        "target": 135.0,
        "side": "BUY",
        "instrument": "OPT",
        "instrument_type": "OPT",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAY23850CE",
        "instrument_id": "NIFTY|2026-05-26|23850|CE",
        "option_type": "CE",
        "right": "CE",
        "confidence": 0.82,
        "builder_confidence": 0.82,
        "permission_confidence": 0.80,
        "gating_final_confidence": 0.79,
        "sizing_confluence_score": 0.84,
        "regime": "TREND",
        "volume": 25000,
        "current_volume": 25000,
        "oi": 15000,
        "best_bid": 121.0,
        "best_ask": 121.5,
        "current_ltp": 121.2,
        "quote_age_sec": 0.4,
        "ltp_age_sec": 0.4,
        "bid_age_sec": 0.4,
        "ask_age_sec": 0.4,
        "chain_snapshot_age_sec": 1.2,
        "fresh_quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "quote_ok": True,
        "quote_source": "live",
        "option_ltp_source": "live",
        "quote_validation_status": "OK",
        "data_state": "DATA_LIVE",
        "data_confidence": 0.95,
        "market_mode": "PAPER",
        "source_flags": {"runtime_mode": "PAPER"},
        "score_inputs_used": {"rr_source": "measured"},
    }
    payload.update(updates)
    return payload


def test_rest_fallback_quote_blocks_executable_truth() -> None:
    candidate = _candidate(
        quote_source="rest_fallback",
        option_ltp_source="rest_fallback",
        source_flags={
            "runtime_mode": "PAPER",
            "quote_truth": {
                "quote_source": "rest_fallback",
                "option_ltp_source": "rest_fallback",
                "quote_validation_status": "OK",
            },
        },
    )

    decision = classify_executable_truth(candidate)

    assert decision.execution_allowed is False
    assert decision.reason_code == FALLBACK_DRIVEN_REASON
    assert FALLBACK_DRIVEN_REASON in decision.reasons
    assert "rest_fallback" in decision.context["quote_sources"]


def test_fallback_estimated_rr_blocks_execution_quality() -> None:
    candidate = _candidate(
        score_inputs_used={"rr_source": "fallback_estimated"},
    )

    quality = evaluate_pretrade_execution_quality(candidate)

    assert quality.execution_ok is False
    assert quality.order_policy == "advisory"
    assert quality.reason_code == FALLBACK_DRIVEN_REASON
    assert FALLBACK_DRIVEN_REASON in quality.context["firebreak_reasons"]


def test_price_mismatch_blocks_even_when_entry_is_derivable() -> None:
    candidate = _candidate(
        quote_validation_status="PRICE_MISMATCH",
        source_flags={
            "runtime_mode": "PAPER",
            "quote_truth": {
                "quote_source": "tick_store",
                "option_ltp_source": "tick_store",
                "quote_validation_status": "PRICE_MISMATCH",
            },
        },
    )

    decision = classify_executable_truth(candidate)

    assert decision.execution_allowed is False
    assert decision.reason_code == PRICE_MISMATCH_REASON
    assert PRICE_MISMATCH_REASON in decision.reasons


def test_stale_or_subscription_failed_ltp_blocks_executable_truth() -> None:
    stale = classify_executable_truth(_candidate(quote_validation_status="STALE_OPTION_LTP"))
    failed = classify_executable_truth(
        _candidate(
            option_ltp_source="subscription_failed",
            source_flags={"runtime_mode": "PAPER", "option_ltp_source": "subscription_failed"},
        )
    )

    assert stale.execution_allowed is False
    assert stale.reason_code == STALE_OPTION_LTP_REASON
    assert failed.execution_allowed is False
    assert failed.reason_code == SUBSCRIPTION_FAILED_REASON


def test_fallback_candidate_cannot_be_selected_or_top_executable() -> None:
    candidate = _candidate(
        quote_source="rest_fallback",
        option_ltp_source="rest_fallback",
        score_inputs_used={"rr_source": "fallback_estimated"},
    )

    ranked = annotate_ranked_opportunities([candidate], scope="edge41", top_n=1)
    selected = ranked[0]
    top = select_top_opportunities(ranked, executable_top_n=1, advisory_top_n=5)

    assert selected["selected_for_execution"] is False
    assert selected["selection_reason"] == "execution_quality_reject"
    assert selected["execution_ok"] is False
    assert selected["order_policy"] == "advisory"
    assert selected["order_policy_reason"] == FALLBACK_DRIVEN_REASON
    assert top["top_executable_opportunities"] == []
    assert top["selector_outcome"] != "EXECUTE_TOP"
