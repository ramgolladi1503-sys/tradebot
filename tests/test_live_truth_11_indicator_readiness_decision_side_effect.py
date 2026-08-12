from __future__ import annotations

from core.decision_dag import (
    DecisionReport,
    REASON_INDICATORS_MISSING,
    build_market_snapshot,
    evaluate_decision,
)
from core.decision_side_effects import handle_post_decision_side_effects
from core.live_indicator_readiness import LIVE_INDICATOR_READINESS_RUNTIME_EVIDENCE_FILENAME


def _market_data(**overrides):
    data = {
        "symbol": "NIFTY",
        "execution_mode": "LIVE",
        "market_open": True,
        "segment": "NSE_FNO",
        "instrument": "OPT",
        "timestamp": 1_000.0,
        "ltp": 100.0,
        "ltp_ts_epoch": 999.0,
        "latest_option_tick_ts": 999.0,
        "latest_option_tick_age_sec": 1.0,
        "ws_connected": True,
        "subscribed_option_tokens_count": 12,
        "ohlc_bars_count": 12,
        "warmup_min_bars": 50,
        "indicators_ok": False,
        "indicators_age_sec": 1_000_000_000.0,
        "indicator_last_update_epoch": None,
        "warmup_reasons": ["HIST_FETCH_FAILED"],
        "compute_indicators_error": "",
        "regime": "TREND",
        "primary_regime": "TREND",
        "regime_prob_max": 0.99,
        "regime_entropy": 0.01,
        "risk_ok": True,
        "broker_enabled": True,
    }
    data.update(overrides)
    return data


def test_indicator_missing_decision_side_effect_writes_runtime_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("core.live_indicator_readiness.data_root", lambda: tmp_path)
    market_data = _market_data()
    decision = evaluate_decision(market_data)
    snapshot = build_market_snapshot(market_data)

    assert REASON_INDICATORS_MISSING in decision.blockers

    handle_post_decision_side_effects(decision, decision.explain, snapshot)

    artifact = tmp_path / LIVE_INDICATOR_READINESS_RUNTIME_EVIDENCE_FILENAME
    assert artifact.exists()
    payload = artifact.read_text(encoding="utf-8")
    assert "NIFTY" in payload
    compat = tmp_path / "logs" / "indicator_missing_runtime_latest.json"
    if compat.exists():
        assert "INDICATORS_MISSING" in compat.read_text(encoding="utf-8")
    assert "ohlc_bars_count" in payload
    assert "warmup_min_bars" in payload


def test_non_indicator_reject_does_not_write_indicator_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("core.live_indicator_readiness.data_root", lambda: tmp_path)
    market_data = _market_data(
        indicators_ok=True,
        indicator_last_update_epoch=999.0,
        indicators_age_sec=1.0,
        ohlc_bars_count=60,
        warmup_min_bars=50,
        primary_regime="UNKNOWN",
        regime="UNKNOWN",
        regime_prob_max=0.1,
        regime_entropy=2.0,
    )
    decision = evaluate_decision(market_data)
    snapshot = build_market_snapshot(market_data)

    assert REASON_INDICATORS_MISSING not in decision.blockers
    assert not decision.allowed

    handle_post_decision_side_effects(decision, decision.explain, snapshot)

    assert not (tmp_path / LIVE_INDICATOR_READINESS_RUNTIME_EVIDENCE_FILENAME).exists()


def test_indicator_evidence_writer_failure_is_side_effect_safe(monkeypatch):
    market_data = _market_data()
    decision = evaluate_decision(market_data)
    snapshot = build_market_snapshot(market_data)

    assert REASON_INDICATORS_MISSING in decision.blockers

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated writer failure")

    monkeypatch.setattr("core.decision_side_effects.write_indicator_missing_runtime_evidence", _boom)

    handle_post_decision_side_effects(decision, decision.explain, snapshot)


def test_allowed_decision_does_not_write_indicator_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("core.live_indicator_readiness.data_root", lambda: tmp_path)
    decision = DecisionReport(
        symbol="NIFTY",
        ts_epoch=1_000.0,
        allowed=True,
        blockers=(),
        primary_blocker=None,
        stage="N11_FINAL_DECISION",
        selected_strategy="BREAKOUT",
        risk_params={},
        facts={},
        explain=(),
    )
    snapshot = build_market_snapshot(
        _market_data(
            indicators_ok=True,
            indicator_last_update_epoch=999.0,
            indicators_age_sec=1.0,
            ohlc_bars_count=60,
        )
    )

    handle_post_decision_side_effects(decision, decision.explain, snapshot)

    assert not (tmp_path / LIVE_INDICATOR_READINESS_RUNTIME_EVIDENCE_FILENAME).exists()
