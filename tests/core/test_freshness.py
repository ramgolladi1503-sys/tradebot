from __future__ import annotations

import json

from core import freshness
from core.freshness import evaluate_quote_freshness


def test_evaluate_quote_freshness_within_threshold():
    out = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=123,
        quote_epoch=100.0,
        candle_epoch=None,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=102.1,
    )

    assert out.blocker is False
    assert out.reason == "quote_within_threshold"
    assert abs(float(out.quote_age_sec or 0.0) - 2.1) < 1e-6


def test_evaluate_quote_freshness_exceeds_threshold():
    out = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=123,
        quote_epoch=100.0,
        candle_epoch=None,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=118.4,
    )

    assert out.blocker is True
    assert out.reason == "quote_exceeds_threshold"
    assert abs(float(out.quote_age_sec or 0.0) - 18.4) < 1e-6


def test_evaluate_quote_freshness_falls_back_to_candle_when_quote_timestamp_missing():
    out = evaluate_quote_freshness(
        symbol="BANKNIFTY",
        instrument_token=456,
        quote_epoch=None,
        candle_epoch=100.0,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=106.0,
        allow_candle_fallback=True,
    )

    assert out.blocker is False
    assert out.reason == "fallback_to_candle_within_threshold"
    assert out.selected_source == "candle"
    assert abs(float(out.candle_age_sec or 0.0) - 6.0) < 1e-6


def test_evaluate_quote_freshness_detects_future_quote_clock_skew():
    out = evaluate_quote_freshness(
        symbol="SENSEX",
        instrument_token=789,
        quote_epoch=105.0,
        candle_epoch=None,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=100.0,
    )

    assert out.blocker is True
    assert out.reason == "quote_in_future_clock_skew"


def test_evaluate_quote_freshness_market_closed_skips_strict_stale():
    out = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=123,
        quote_epoch=100.0,
        candle_epoch=None,
        threshold_sec=2.5,
        market_open=False,
        now_epoch=120.0,
    )

    assert out.blocker is False
    assert out.reason == "market_closed_skip_strict_stale"


def test_evaluate_quote_freshness_writes_runtime_artifact(monkeypatch, tmp_path):
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(freshness, "logs_dir", lambda: logs_root)

    out = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=123,
        quote_epoch=1700000100.0,
        candle_epoch=None,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=1700000102.0,
        persist_runtime=True,
    )

    payload = json.loads((logs_root / "freshness_latest.json").read_text(encoding="utf-8"))
    assert payload["decisions"]["NIFTY"]["option_quote"]["reason"] == out.reason


def test_evaluate_quote_freshness_invalid_tiny_epoch_does_not_persist_runtime(monkeypatch, tmp_path):
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(freshness, "logs_dir", lambda: logs_root)

    out = evaluate_quote_freshness(
        symbol="NIFTY",
        instrument_token=12345,
        quote_epoch=100.0,
        candle_epoch=None,
        threshold_sec=8.0,
        market_open=True,
        now_epoch=101.0,
        trade_id="T-TOKEN-RECOVER",
        persist_runtime=True,
    )

    assert out.reason == "quote_within_threshold"
    latest_path = logs_root / "freshness_latest.json"
    history_path = logs_root / "freshness_decisions.jsonl"
    assert (not latest_path.exists()) or ("T-TOKEN-RECOVER" not in latest_path.read_text(encoding="utf-8"))
    assert (not history_path.exists()) or (history_path.read_text(encoding="utf-8").strip() == "")
