import json
from datetime import datetime, timezone
from pathlib import Path

from config import config as cfg
from core.market_event_graph_live_runtime_bridge import (
    BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE,
    BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION,
    INDEX_INTERVAL_MISALIGNED,
    LIVE_BAR_PROVENANCE_UNPROVEN,
    LIVE_UNIVERSE_NOT_CONFIGURED,
    LiveSourceRuntimeBridge,
    build_live_constituent_subscription_audit,
    canonical_live_universe_sha256,
    flush_live_source_bridge,
)
from core.market_event_graph_live_source import LiveCapturedMetadataExporter, load_validated_live_jsonl


def _symbols():
    return tuple(f"NIFTY_{idx:02d}" for idx in range(40))


def _contract(**overrides):
    payload = {
        "name": "NIFTY_LIVE_CONSTITUENTS",
        "version": "2026-07-30.test",
        "effective_date": "2026-07-30",
        "index_symbol": "NIFTY",
        "index_instrument_token": 1,
        "constituents": [
            {"symbol": symbol, "instrument_token": 1000 + index}
            for index, symbol in enumerate(_symbols())
        ],
        "source_provenance": "unit-test-authoritative-contract",
        "capture_session_id": "live-session-test",
    }
    payload.update(overrides)
    payload["canonical_sha256"] = canonical_live_universe_sha256(payload)
    return payload


def _evidence(contract):
    required = [contract.index_symbol, *contract.constituent_symbols]
    return {
        "subscription_evidence_id": "sub-proof-1",
        "token_resolved_symbols": required,
        "subscription_requested_symbols": required,
        "subscription_callback_applied_symbols": required,
        "mode_applied_symbols": required,
        "live_tick_observed_symbols": required,
        "completed_bar_available_symbols": required,
    }


def _bar(ts_epoch: float, symbol: str, close: float = 100.0, *, provenance=None):
    return {
        "ts": datetime.fromtimestamp(ts_epoch, tz=timezone.utc),
        "symbol": symbol,
        "open": close - 1.0,
        "high": close + 1.0,
        "low": close - 2.0,
        "close": close,
        "volume": 10,
        "bar_provenance": (
            provenance
            if provenance is not None
            else {
            "source_type": "live_websocket",
            "live_feed_session_id": "feed-session-1",
            "first_live_tick_epoch": ts_epoch + 1.0,
            "last_live_tick_epoch": ts_epoch + 50.0,
            "historical_seed": False,
            "replay_fixture": False,
            "non_live_fallback": False,
            "recovered_synthetic": False,
            }
        ),
    }


def _install_bars(monkeypatch, *, contract_payload, index_epoch=60.0, constituent_epoch=60.0, missing_symbol=None, provenance=None):
    symbols = {row["symbol"] for row in contract_payload["constituents"]}

    def bars(symbol, as_of):
        if symbol == missing_symbol:
            return []
        if symbol == contract_payload["index_symbol"]:
            return [_bar(index_epoch, symbol, 25000.0, provenance=provenance)]
        if symbol in symbols:
            return [_bar(constituent_epoch, symbol, 100.0, provenance=provenance)]
        return []

    monkeypatch.setattr("core.market_event_graph_live_runtime_bridge.ohlc_buffer.get_completed_bars", bars)


def test_bridge_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)
    output_path = tmp_path / "captured_metadata.jsonl"
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(output_path), universe_contract=_contract())

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(120.0, tz=timezone.utc))

    assert result.attempted is False
    assert result.exported is False
    assert result.reason == "DISABLED"
    assert output_path.exists() is False


def test_real_exporter_persists_exactly_one_valid_live_row(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload)
    output_path = tmp_path / "captured_metadata.jsonl"
    bridge = LiveSourceRuntimeBridge(
        exporter=LiveCapturedMetadataExporter(output_path),
        universe_contract=contract_payload,
        subscription_evidence_provider=_evidence,
    )

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.exported is True
    stored_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    (stored_row,) = stored_rows
    assert stored_row["source_kind"] == "LIVE_CAPTURED_METADATA"
    assert stored_row["session_date"] == "1970-01-01"
    assert stored_row["interval_end"] == "1970-01-01T05:32:00+05:30"
    assert tuple(stored_row["expected_constituent_symbols"]) == _symbols()
    assert stored_row["read_only"] is True
    assert stored_row["is_order_action"] is False
    assert stored_row["broker_api_called"] is False
    assert stored_row["allowed_for_live_execution"] is False
    assert stored_row["source_bar_end_epoch"] == 120.0
    assert stored_row["index_source_bar_end_epoch"] == 120.0
    assert stored_row["observed_at_epoch"] == 130.0
    assert stored_row["live_universe"]["version"] == "2026-07-30.test"
    assert stored_row["universe_hash"] == contract_payload["canonical_sha256"]
    (validated_row,) = load_validated_live_jsonl(output_path)
    assert validated_row["universe_hash"] == contract_payload["canonical_sha256"]


def test_no_explicit_live_universe_contract_exports_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", "")
    output_path = tmp_path / "captured_metadata.jsonl"
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(output_path))

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(120.0, tz=timezone.utc))

    assert result.reason == LIVE_UNIVERSE_NOT_CONFIGURED
    assert result.exported is False
    assert output_path.exists() is False


def test_two_symbol_self_declared_universe_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    small = _contract(constituents=[{"symbol": "AAA", "instrument_token": 10}, {"symbol": "BBB", "instrument_token": 11}])
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"), universe_contract=small)

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(120.0, tz=timezone.utc))

    assert result.reason == BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE
    assert result.exported is False


def test_exact_identity_mismatch_is_rejected_even_when_counts_match(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload)

    def mismatched_evidence(contract):
        payload = _evidence(contract)
        payload["subscription_callback_applied_symbols"] = ["NIFTY", *list(_symbols()[:-1]), "WRONG"]
        return payload

    bridge = LiveSourceRuntimeBridge(
        exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"),
        universe_contract=contract_payload,
        subscription_evidence_provider=mismatched_evidence,
    )

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION
    assert result.exported is False
    assert "NIFTY_39" in result.rejected_identities


def test_token_resolution_without_callback_proof_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"), universe_contract=contract_payload)

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION
    assert result.exported is False


def test_missing_live_tick_provenance_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload, provenance={})
    bridge = LiveSourceRuntimeBridge(
        exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"),
        universe_contract=contract_payload,
        subscription_evidence_provider=_evidence,
    )

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == LIVE_BAR_PROVENANCE_UNPROVEN
    assert result.exported is False


def test_history_seeded_and_fallback_bars_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    blocked_provenance = {
        "source_type": "historical_seed",
        "live_feed_session_id": "feed-session-1",
        "first_live_tick_epoch": 61.0,
        "last_live_tick_epoch": 119.0,
        "historical_seed": True,
        "replay_fixture": False,
        "non_live_fallback": True,
        "recovered_synthetic": False,
    }
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload, provenance=blocked_provenance)
    bridge = LiveSourceRuntimeBridge(
        exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"),
        universe_contract=contract_payload,
        subscription_evidence_provider=_evidence,
    )

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == LIVE_BAR_PROVENANCE_UNPROVEN
    assert result.exported is False


def test_index_constituent_source_interval_mismatch_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload, index_epoch=120.0, constituent_epoch=60.0)
    bridge = LiveSourceRuntimeBridge(
        exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"),
        universe_contract=contract_payload,
        subscription_evidence_provider=_evidence,
    )

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(190.0, tz=timezone.utc))

    assert result.reason == INDEX_INTERVAL_MISALIGNED
    assert result.exported is False


def test_fetch_live_market_data_hook_disabled_enabled_and_failure_isolation(monkeypatch):
    import core.market_data as market_data

    calls = []
    monkeypatch.setattr(market_data.cfg, "SYMBOLS", [])
    monkeypatch.setattr(market_data.cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", False)
    assert market_data.fetch_live_market_data() == []
    assert calls == []

    class Bridge:
        def observe_cycle(self, rows, *, cycle_cutoff):
            calls.append({"rows": tuple(rows), "cycle_cutoff": cycle_cutoff})
            raise RuntimeError("bridge failed")

    monkeypatch.setattr("core.market_event_graph_live_runtime_bridge.get_live_source_bridge", lambda: Bridge())
    monkeypatch.setattr(market_data.cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)

    result = market_data.fetch_live_market_data()

    assert result == []
    (call,) = calls
    assert call["rows"] == ()


def test_subscription_audit_and_flush_are_read_only(monkeypatch):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH", "")
    audit = build_live_constituent_subscription_audit()
    flush = flush_live_source_bridge()

    assert audit["read_only"] is True
    assert audit["is_order_action"] is False
    assert audit["broker_api_called"] is False
    assert audit["allowed_for_live_execution"] is False
    assert flush["read_only"] is True
    assert flush["is_order_action"] is False
    assert flush["broker_api_called"] is False
    assert flush["allowed_for_live_execution"] is False
