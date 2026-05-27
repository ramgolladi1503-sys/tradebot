from __future__ import annotations

import json

from core.live_indicator_readiness import (
    INDICATORS_MISSING_GATE_REASON,
    build_indicator_missing_runtime_evidence_payload,
    build_live_indicator_readiness_report,
    write_indicator_missing_runtime_evidence,
)


def _missing_report():
    return build_live_indicator_readiness_report(
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
        now_epoch=1_000.0,
    )


def _ready_report():
    return build_live_indicator_readiness_report(
        (
            {
                "symbol": "NIFTY",
                "ohlc_bars_count": 60,
                "indicator_last_update_epoch": 990.0,
                "vwap": 100.0,
                "rsi": 55.0,
                "ema": 101.0,
                "atr": 12.0,
            },
        ),
        now_epoch=1_000.0,
    )


def test_indicator_missing_runtime_payload_matches_required_symbol_shape():
    payload = build_indicator_missing_runtime_evidence_payload(_missing_report(), now_epoch=1_000.0)

    assert payload is not None
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["decision_gate_reason"] == INDICATORS_MISSING_GATE_REASON
    assert payload["symbol_count"] == 1
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False

    symbol_payload = payload["by_symbol"]["NIFTY"]
    assert symbol_payload == {
        "symbol": "NIFTY",
        "decision_gate_reason": "INDICATORS_MISSING",
        "indicators_ok": False,
        "indicator_inputs_ok": False,
        "ohlc_bars_count": 0,
        "warmup_min_bars": 50,
        "indicator_last_update_epoch": None,
        "indicators_age_sec": None,
        "missing_inputs": ["ohlc_bars"],
        "indicator_missing_inputs": ["vwap", "rsi", "ema", "atr"],
        "compute_indicators_error": "",
        "vwap_present": False,
        "rsi_present": False,
        "ema_present": False,
        "atr_present": False,
    }


def test_indicator_missing_runtime_writer_creates_latest_json(tmp_path):
    target = tmp_path / "live_indicator_readiness_latest.json"

    out = write_indicator_missing_runtime_evidence(_missing_report(), path=target, now_epoch=1_000.0)

    assert out == target
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["decision_gate_reason"] == "INDICATORS_MISSING"
    assert saved["by_symbol"]["NIFTY"]["indicator_missing_inputs"] == ["vwap", "rsi", "ema", "atr"]
    assert saved["metadata"]["does_not_change_gate_decision"] is True
    assert saved["metadata"]["does_not_change_candidate_state"] is True


def test_indicator_missing_runtime_writer_skips_ready_report(tmp_path):
    target = tmp_path / "live_indicator_readiness_latest.json"

    out = write_indicator_missing_runtime_evidence(_ready_report(), path=target, now_epoch=1_000.0)

    assert out is None
    assert not target.exists()


def test_indicator_missing_runtime_payload_skips_non_indicator_missing_blocks():
    stale_report = build_live_indicator_readiness_report(
        (
            {
                "symbol": "NIFTY",
                "ohlc_bars_count": 60,
                "indicator_last_update_epoch": 800.0,
                "vwap": 100.0,
                "rsi": 55.0,
                "ema": 101.0,
                "atr": 12.0,
            },
        ),
        now_epoch=1_000.0,
        max_indicator_age_sec=120.0,
    )

    assert build_indicator_missing_runtime_evidence_payload(stale_report, now_epoch=1_000.0) is None
