"""Safety regression tests for EDGE-35 strategy signal quality.

These tests are read-only: broker_api_called=False, is_order_action=False,
live_order_action=False. Strategy signal validation must not cross execution
boundaries.
"""

from core.executable_truth import classify_executable_truth
from core.strategy_signal_quality import classify_strategy_signal_quality


def _candidate(**overrides):
    base = {
        "trade_id": "EDGE35-T1",
        "candidate_class": "EXECUTABLE",
        "execution_entry_status": "executable",
        "selected_for_execution": True,
        "market_mode": "LIVE",
        "strategy_family": "trend_pullback",
        "side": "BUY",
        "signal_score": 0.72,
        "setup_score": 0.74,
        "trigger_score": 0.70,
        "confluence_score": 0.72,
        "regime_fit": 0.76,
        "instrument_token": 123456,
        "last_option_tick_epoch": 1_700_000_000.0,
        "option_feed_block_reason": "OK",
        "ltp_age_sec": 0.5,
        "bid_age_sec": 0.6,
        "ask_age_sec": 0.7,
        "quote_age_sec": 0.7,
        "chain_snapshot_age_sec": 2.0,
        "data_state": "DATA_OK",
        "fresh_quote_ok": True,
        "liquidity_ok": True,
        "spread_ok": True,
        "data_confidence": 0.90,
        "best_bid": 100.0,
        "best_ask": 101.0,
        "ltp": 100.5,
        "quote_completeness": "FULL",
        "spread_source": "live_quote",
        "source_flags": {},
    }
    base.update(overrides)
    return base


def test_strategy_signal_quality_is_read_only_safety_gate():
    broker_api_called = False
    is_order_action = False
    live_order_action = False

    decision = classify_strategy_signal_quality(_candidate(signal_score=0.20))

    assert decision.signal_ok is False
    assert broker_api_called is False
    assert is_order_action is False
    assert live_order_action is False


def test_strategy_signal_quality_allows_strong_signal_candidate():
    decision = classify_strategy_signal_quality(_candidate())
    truth = classify_executable_truth(_candidate())

    assert decision.signal_ok is True
    assert decision.reason_code == "ok"
    assert truth.execution_allowed is True


def test_strategy_signal_quality_blocks_live_candidate_without_signal_payload():
    candidate = _candidate(
        signal_score=None,
        setup_score=None,
        trigger_score=None,
        confluence_score=None,
        regime_fit=None,
    )

    decision = classify_strategy_signal_quality(candidate)
    truth = classify_executable_truth(candidate)

    assert decision.signal_ok is False
    assert "no_strategy_signal" in decision.reasons
    assert truth.execution_allowed is False
    assert "strategy_signal_quality_failed" in truth.reasons


def test_strategy_signal_quality_blocks_weak_signal():
    decision = classify_strategy_signal_quality(_candidate(signal_score=0.30))

    assert decision.signal_ok is False
    assert set(decision.reasons) == {"weak_strategy_signal"}


def test_strategy_signal_quality_blocks_missing_strategy_family():
    decision = classify_strategy_signal_quality(_candidate(strategy_family=""))

    assert decision.signal_ok is False
    assert "missing_strategy_family" in decision.reasons


def test_strategy_signal_quality_blocks_missing_direction():
    decision = classify_strategy_signal_quality(_candidate(side="NEUTRAL"))

    assert decision.signal_ok is False
    assert "missing_signal_direction" in decision.reasons


def test_strategy_signal_quality_blocks_explicit_reject_reason():
    decision = classify_strategy_signal_quality(_candidate(reject_reason="weak_signal"))

    assert decision.signal_ok is False
    assert "strategy_reject_reason:weak_signal" in decision.reasons


def test_strategy_signal_quality_blocks_conflicting_signal():
    decision = classify_strategy_signal_quality(_candidate(signal_conflict=True))

    assert decision.signal_ok is False
    assert "conflicting_strategy_signal" in decision.reasons


def test_strategy_signal_quality_preserves_legacy_offline_fixture_without_signal_fields():
    decision = classify_strategy_signal_quality(
        _candidate(
            market_mode="PAPER",
            signal_score=None,
            setup_score=None,
            trigger_score=None,
            confluence_score=None,
            regime_fit=None,
        )
    )

    assert decision.signal_ok is True
    assert decision.reason_code == "legacy_signal_fixture"
