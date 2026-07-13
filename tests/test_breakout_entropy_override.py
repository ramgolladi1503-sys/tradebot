import pytest
from core.decision_dag import _node_regime_ok, MarketSnapshot

class MockConfig:
    def __getattr__(self, name):
        if name == "REGIME_PROB_MIN":
            return 0.45
        if name == "REGIME_ENTROPY_MAX":
            return 1.3
        if name == "PAPER_RELAX_GATES":
            return False
        return 1

def test_regime_entropy_max_overrides(monkeypatch):
    import core.decision_dag as dag
    monkeypatch.setattr(dag, "cfg", MockConfig())
    
    # Base unstable case
    snapshot = MarketSnapshot(
        symbol="NIFTY", ts_epoch=0, mode="PAPER", market_open=True, offhours_mode=False,
        allow_stale_quotes=False, market_context={}, ltp=0, ltp_ts_epoch=0, ltp_source="live",
        depth={}, depth_ts_epoch=0, ohlc_bars_count=0, last_bar_ts_epoch=0, indicators_ok=True,
        indicators_age_sec=0, indicator_last_update_epoch=0, regime_probs={},
        regime_entropy=1.45,  # Too high for 1.3
        regime_prob_max=0.55,
        primary_regime="TREND",
        unstable_reasons=(), risk_ok=True, risk_reasons=(), governance_lock_active=False,
        broker_enabled=False, manual_review_required=False, instrument="OPT",
        bid=0, ask=0, quote_ok_input=True, quote_source_input="live",
        feed_health={}, raw_data={}, session_state="NORMAL_OPEN"
    )
    result = _node_regime_ok(snapshot, {}, {})
    assert "entropy_too_high" in result.facts["unstable_reasons"]
    
    from dataclasses import replace
    
    # Override via volume_delta_override and TREND
    snapshot = replace(snapshot, primary_regime="TREND", raw_data={"volume_delta_override": True})
    result = _node_regime_ok(snapshot, {}, {})
    assert "entropy_too_high" not in result.facts["unstable_reasons"]
    
    # Override via depth_imbalance > 0.35 and TREND
    snapshot = replace(snapshot, raw_data={"depth_imbalance": 0.40})
    result = _node_regime_ok(snapshot, {}, {})
    assert "entropy_too_high" not in result.facts["unstable_reasons"]
    
    # Override via high TREND probability
    snapshot = replace(snapshot, raw_data={}, session_state="NORMAL_OPEN", regime_prob_max=0.65)
    result = _node_regime_ok(snapshot, {}, {})
    assert "entropy_too_high" not in result.facts["unstable_reasons"]


def test_node_regime_ok_derives_session_bucket_from_timestamp(monkeypatch):
    import core.decision_dag as dag

    monkeypatch.setattr(dag, "cfg", MockConfig())
    snapshot = MarketSnapshot(
        symbol="NIFTY", ts_epoch=0, mode="PAPER", market_open=True, offhours_mode=False,
        allow_stale_quotes=False, market_context={}, ltp=0, ltp_ts_epoch=0, ltp_source="live",
        depth={}, depth_ts_epoch=0, ohlc_bars_count=0, last_bar_ts_epoch=0, indicators_ok=True,
        indicators_age_sec=0, indicator_last_update_epoch=0, regime_probs={},
        regime_entropy=0.85,
        regime_prob_max=0.55,
        primary_regime="RANGE",
        unstable_reasons=(), risk_ok=True, risk_reasons=(), governance_lock_active=False,
        broker_enabled=False, manual_review_required=False, instrument="OPT",
        bid=0, ask=0, quote_ok_input=True, quote_source_input="live",
        feed_health={}, raw_data={"timestamp_ist": "2026-07-02T09:20:00+05:30"}, session_state="NORMAL_OPEN"
    )
    result = _node_regime_ok(snapshot, {}, {})
    assert "entropy_too_high" not in result.facts["unstable_reasons"]
