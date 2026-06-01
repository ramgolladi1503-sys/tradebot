"""HOTFIX/EDGE-79A live indicator readiness diagnostics tests."""

from __future__ import annotations

from core.live_indicator_readiness import (
    INDICATOR_BARS_BELOW_WARMUP,
    INDICATOR_COMPUTE_ERROR,
    INDICATOR_EMPTY_INPUT,
    INDICATOR_INPUTS_MISSING,
    INDICATOR_LAST_UPDATE_MISSING,
    INDICATOR_STALE,
    INDICATOR_VALUE_MISSING,
    build_live_indicator_readiness_report,
    build_live_indicator_readiness_runtime_payload,
    write_live_indicator_readiness_latest,
)


def _ready_snapshot():
    return {
        "symbol": "NIFTY",
        "ohlc_bars_count": 60,
        "indicator_last_update_epoch": 1_000.0,
        "vwap": 100.5,
        "rsi": 55.0,
        "ema": 100.0,
        "atr": 12.0,
    }


def test_ready_indicator_snapshot_exposes_required_fields():
    report = build_live_indicator_readiness_report((_ready_snapshot(),), now_epoch=1_030.0)
    decision = report.get("NIFTY")
    payload = report.to_payload()

    assert report.indicators_ready is True
    assert decision is not None
    assert decision.ready is True
    assert decision.indicators_ok is True
    assert decision.indicator_inputs_ok is True
    assert decision.ohlc_bars_count == 60
    assert decision.warmup_min_bars == 50
    assert decision.indicator_last_update_epoch == 1_000.0
    assert decision.indicators_age_sec == 30.0
    assert decision.missing_inputs == ()
    assert decision.indicator_missing_inputs == ()
    assert decision.compute_indicators_error == ""
    assert decision.vwap_present is True
    assert decision.rsi_present is True
    assert decision.ema_present is True
    assert decision.atr_present is True
    assert decision.decision_gate_reason == "indicator_ready"
    assert payload["read_only"] is True
    assert payload["append"] is False


def test_blocks_zero_bars_and_missing_last_update_for_live_ltp_case():
    report = build_live_indicator_readiness_report(
        (
            {
                "symbol": "NIFTY",
                "ohlc_bars_count": 0,
                "vwap": None,
                "rsi": None,
                "ema": None,
                "atr": None,
            },
        ),
        now_epoch=1_030.0,
    )
    decision = report.get("NIFTY")

    assert report.indicators_ready is False
    assert decision is not None
    assert decision.ready is False
    assert decision.indicators_ok is False
    assert decision.indicator_inputs_ok is False
    assert decision.ohlc_bars_count == 0
    assert decision.warmup_min_bars == 50
    assert decision.indicator_last_update_epoch is None
    assert decision.indicators_age_sec is None
    assert decision.missing_inputs == ("ohlc_bars",)
    assert decision.indicator_missing_inputs == ("vwap", "rsi", "ema", "atr")
    assert INDICATOR_INPUTS_MISSING in decision.blockers
    assert INDICATOR_BARS_BELOW_WARMUP in decision.blockers
    assert INDICATOR_LAST_UPDATE_MISSING in decision.blockers
    assert INDICATOR_VALUE_MISSING in decision.blockers
    assert decision.vwap_present is False
    assert decision.rsi_present is False
    assert decision.ema_present is False
    assert decision.atr_present is False
    assert decision.decision_gate_reason == INDICATOR_INPUTS_MISSING


def test_blocks_stale_indicator_update_even_when_values_exist():
    report = build_live_indicator_readiness_report(
        (_ready_snapshot(),),
        now_epoch=1_500.0,
        max_indicator_age_sec=120.0,
    )
    decision = report.get("NIFTY")

    assert report.indicators_ready is False
    assert decision is not None
    assert decision.indicators_ok is False
    assert decision.indicator_inputs_ok is True
    assert decision.indicators_age_sec == 500.0
    assert INDICATOR_STALE in decision.blockers
    assert decision.decision_gate_reason == INDICATOR_STALE


def test_blocks_compute_error_and_preserves_error_text():
    snapshot = dict(_ready_snapshot())
    snapshot["compute_indicators_error"] = "missing close column"
    report = build_live_indicator_readiness_report((snapshot,), now_epoch=1_030.0)
    decision = report.get("NIFTY")

    assert report.indicators_ready is False
    assert decision is not None
    assert decision.indicators_ok is False
    assert decision.compute_indicators_error == "missing close column"
    assert INDICATOR_COMPUTE_ERROR in decision.blockers
    assert decision.decision_gate_reason == INDICATOR_COMPUTE_ERROR


def test_empty_input_fails_closed_without_decisions():
    report = build_live_indicator_readiness_report((), now_epoch=1_030.0)
    payload = report.to_payload()

    assert report.indicators_ready is False
    assert INDICATOR_EMPTY_INPUT in report.blockers
    assert payload["decision_count"] == 0
    assert payload["ready_count"] == 0
    assert payload["blocked_count"] == 0


def test_multiple_symbols_keep_per_symbol_diagnostics():
    blocked = {
        "symbol": "BANKNIFTY",
        "ohlc_bars_count": 10,
        "indicator_last_update_epoch": 1_020.0,
        "vwap": 101.0,
        "rsi": None,
        "ema": 100.0,
        "atr": 11.0,
    }
    report = build_live_indicator_readiness_report((_ready_snapshot(), blocked), now_epoch=1_030.0)

    assert report.indicators_ready is False
    assert report.get("NIFTY").ready is True
    assert report.get("BANKNIFTY").ready is False
    assert report.to_payload()["ready_symbols"] == ["NIFTY"]
    assert report.to_payload()["blocked_symbols"] == ["BANKNIFTY"]


def test_runtime_latest_payload_emits_schema2_provenance_and_by_symbol_contract(tmp_path, monkeypatch):
    report = build_live_indicator_readiness_report((_ready_snapshot(),), now_epoch=1_030.0)
    payload = build_live_indicator_readiness_runtime_payload(report, now_epoch=1_030.0)
    assert payload["schema_version"] == 2
    assert payload["writer_schema_version"] == 2
    assert payload["writer_name"] == "live_indicator_readiness"
    assert payload["writer_module"]
    assert isinstance(payload["generated_epoch"], float)
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["by_symbol"]["NIFTY"]["rsi_present"] is True
    assert payload["by_symbol"]["NIFTY"]["ema_present"] is True
    assert payload["by_symbol"]["NIFTY"]["indicator_missing_inputs"] == []

    target = tmp_path / "live_indicator_readiness_latest.json"
    write_live_indicator_readiness_latest(report, path=target, now_epoch=1_030.0)
    assert target.exists()
