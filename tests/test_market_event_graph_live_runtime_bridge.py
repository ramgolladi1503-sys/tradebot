from datetime import datetime, timezone
from pathlib import Path

import pytest

from config import config as cfg
from core.market_event_graph_live_runtime_bridge import (
    LiveSourceRuntimeBridge,
    build_live_constituent_subscription_audit,
    flush_live_source_bridge,
)
from core.market_event_graph_live_source import LiveCapturedMetadataExporter


class _FakeExporter:
    def __init__(self):
        self.rows = []
        self.path = Path("/tmp/fake-captured-metadata.jsonl")

    def export_row(self, row):
        self.rows.append(dict(row))
        return type("Result", (), {"written": True, "reason": "OK", "row": dict(row), "details": ()})()


def _bar(ts_epoch: float, symbol: str, close: float = 100.0):
    return {
        "ts": datetime.fromtimestamp(ts_epoch, tz=timezone.utc),
        "symbol": symbol,
        "open": close - 1.0,
        "high": close + 1.0,
        "low": close - 2.0,
        "close": close,
        "volume": 10,
        "completed": True,
    }


def test_bridge_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)
    bridge = LiveSourceRuntimeBridge(exporter=_FakeExporter())

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(100.0, tz=timezone.utc))

    assert result.attempted is False
    assert result.exported is False
    assert result.reason == "DISABLED"
    assert bridge.exporter.rows == []


def test_bridge_exports_one_completed_snapshot_when_enabled(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL", "NIFTY")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_CONSTITUENT_SYMBOLS", ["AAA", "BBB"])
    monkeypatch.setattr(
        "core.market_event_graph_live_runtime_bridge.get_token_for_symbol",
        lambda symbol: {"NIFTY": 1, "AAA": 2, "BBB": 3}.get(symbol),
    )
    monkeypatch.setattr(
        "core.market_event_graph_live_runtime_bridge.ohlc_buffer.get_completed_bars",
        lambda symbol, as_of: [_bar(60.0, symbol)] if symbol in {"NIFTY", "AAA", "BBB"} else [],
    )
    exporter = _FakeExporter()
    bridge = LiveSourceRuntimeBridge(exporter=exporter)

    result = bridge.observe_cycle(
        [{"symbol": "NIFTY"}, {"symbol": "AAA"}, {"symbol": "BBB"}],
        cycle_cutoff=datetime.fromtimestamp(120.0, tz=timezone.utc),
    )

    assert result.attempted is True
    assert result.exported is True
    assert result.accepted_constituent_count == 2
    assert len(exporter.rows) == 1
    assert exporter.rows[0]["source_kind"] == "LIVE_CAPTURED_METADATA"
    assert exporter.rows[0]["subscription_evidence"]["accepted_count"] == 3


def test_incomplete_universe_does_not_export(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL", "NIFTY")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_CONSTITUENT_SYMBOLS", ["AAA", "BBB"])
    monkeypatch.setattr(
        "core.market_event_graph_live_runtime_bridge.get_token_for_symbol",
        lambda symbol: {"NIFTY": 1, "AAA": 2, "BBB": 3}.get(symbol),
    )
    monkeypatch.setattr(
        "core.market_event_graph_live_runtime_bridge.ohlc_buffer.get_completed_bars",
        lambda symbol, as_of: [_bar(60.0, symbol)] if symbol in {"NIFTY", "AAA"} else [],
    )
    exporter = _FakeExporter()
    bridge = LiveSourceRuntimeBridge(exporter=exporter)

    result = bridge.observe_cycle(
        [{"symbol": "NIFTY"}, {"symbol": "AAA"}],
        cycle_cutoff=datetime.fromtimestamp(120.0, tz=timezone.utc),
    )

    assert result.exported is False
    assert exporter.rows == []


def test_misaligned_constituent_intervals_are_rejected(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL", "NIFTY")
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_CONSTITUENT_SYMBOLS", ["AAA", "BBB"])
    monkeypatch.setattr(
        "core.market_event_graph_live_runtime_bridge.get_token_for_symbol",
        lambda symbol: {"NIFTY": 1, "AAA": 2, "BBB": 3}.get(symbol),
    )
    monkeypatch.setattr(
        "core.market_event_graph_live_runtime_bridge.ohlc_buffer.get_completed_bars",
        lambda symbol, as_of: [_bar(60.0, symbol)] if symbol in {"NIFTY", "AAA"} else [_bar(30.0, symbol)],
    )
    exporter = _FakeExporter()
    bridge = LiveSourceRuntimeBridge(exporter=exporter)

    result = bridge.observe_cycle(
        [{"symbol": "NIFTY"}, {"symbol": "AAA"}, {"symbol": "BBB"}],
        cycle_cutoff=datetime.fromtimestamp(120.0, tz=timezone.utc),
    )

    assert result.exported is False
    assert exporter.rows == []


def test_subscription_audit_is_read_only():
    audit = build_live_constituent_subscription_audit()

    assert audit["read_only"] is True
    assert audit["is_order_action"] is False
    assert audit["broker_api_called"] is False
    assert audit["allowed_for_live_execution"] is False


def test_flush_is_read_only():
    payload = flush_live_source_bridge()
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["allowed_for_live_execution"] is False

