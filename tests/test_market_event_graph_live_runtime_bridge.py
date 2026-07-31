import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config import config as cfg
from core.market_event_graph_live_runtime_bridge import (
    BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE,
    BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION,
    INDEX_INTERVAL_MISALIGNED,
    LIVE_BAR_PROVENANCE_UNPROVEN,
    LIVE_UNIVERSE_NOT_CONFIGURED,
    LiveSourceRuntimeBridge,
    RECONNECT_GENERATION_MISMATCH,
    build_live_constituent_subscription_audit,
    canonical_live_universe_sha256,
    flush_live_source_bridge,
)
from core.market_event_graph_live_source import LiveCapturedMetadataExporter, load_validated_live_jsonl


@pytest.fixture(autouse=True)
def _sandbox_rejection_path(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_REJECTION_PATH", str(tmp_path / "rejections.jsonl"))


def _symbols():
    return tuple(f"NIFTY_{idx:02d}" for idx in range(40))


def _contract(**overrides):
    payload = {
        "schema_version": 1,
        "broker_provider": "kite",
        "token_domain": "kite_instrument_token",
        "name": "NIFTY_LIVE_CONSTITUENTS",
        "version": "2026-07-30.test",
        "effective_date": "2026-07-30",
        "source_retrieval_date": "2026-07-30",
        "source_page_updated_date": "Thu, 30 Jul 2026 03:30:53 GMT",
        "official_source_url": "file:nifty.csv",
        "official_raw_sha256": "a" * 64,
        "index_symbol": "NIFTY",
        "index_instrument_token": 1,
        "provider_native_index_identifier": "NIFTY 50",
        "constituents": [
            {"symbol": symbol, "instrument_token": 1000 + index}
            for index, symbol in enumerate(_symbols())
        ],
        "broker_instrument_master": {"path": "runtime/kite_instruments.json", "sha256": "b" * 64},
        "source_provenance": "unit-test-authoritative-contract",
        "capture_session_id": "live-session-test",
    }
    payload.update(overrides)
    payload["canonical_sha256"] = canonical_live_universe_sha256(payload)
    return payload


def _evidence(contract):
    index_symbol = contract.index_symbol if hasattr(contract, "index_symbol") else str(contract["index_symbol"]).upper()
    constituents = contract.constituents if hasattr(contract, "constituents") else tuple(contract["constituents"])
    constituent_symbols = (
        contract.constituent_symbols
        if hasattr(contract, "constituent_symbols")
        else tuple(str(row["symbol"]).upper() for row in constituents)
    )
    index_token = contract.index_instrument_token if hasattr(contract, "index_instrument_token") else int(contract["index_instrument_token"])
    required = [index_symbol, *constituent_symbols]
    token_by_symbol = {
        index_symbol: index_token,
        **{str(row["symbol"]).upper(): int(row["instrument_token"]) for row in constituents},
    }
    token_lifecycle = {
        str(token): {
            "symbol": symbol,
            "instrument_token": token,
            "subscription_requested_epoch": 10.0,
            "subscribe_call_succeeded_epoch": 11.0,
            "mode_request_succeeded_epoch": 12.0,
            "first_live_tick_epoch": 13.0,
            "latest_live_tick_epoch": 20.0,
            "first_full_payload_epoch": 14.0,
            "latest_full_payload_epoch": 21.0,
            "feed_session_id": "feed-session-1",
            "reconnect_generation": 1,
        }
        for symbol, token in token_by_symbol.items()
    }
    return {
        "subscription_evidence_id": "sub-proof-1",
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "feed_session_id": "feed-session-1",
        "reconnect_generation": 1,
        "token_by_symbol": token_by_symbol,
        "token_resolved_symbols": required,
        "subscription_requested_symbols": required,
        "subscription_request_succeeded_symbols": required,
        "mode_request_succeeded_symbols": required,
        "live_tick_observed_symbols": required,
        "full_payload_observed_symbols": required,
        "completed_bar_available_symbols": required,
        "token_lifecycle": token_lifecycle,
    }


def _bar(ts_epoch: float, symbol: str, close: float = 100.0, *, token: int | None = None, universe_hash: str = "", provenance=None):
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
            "symbol": str(symbol).upper(),
            "live_feed_session_id": "feed-session-1",
            "reconnect_generation": 1,
            "instrument_token": int(token or 0),
            "provider": "kite",
            "token_domain": "kite_instrument_token",
            "universe_hash": universe_hash,
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
    token_by_symbol = {
        str(contract_payload["index_symbol"]).upper(): int(contract_payload["index_instrument_token"]),
        **{str(row["symbol"]).upper(): int(row["instrument_token"]) for row in contract_payload["constituents"]},
    }
    symbols = set(token_by_symbol)
    universe_hash = str(contract_payload["canonical_sha256"])

    def bars(symbol, as_of):
        symbol_upper = str(symbol).upper()
        if symbol == missing_symbol:
            return []
        if symbol_upper == str(contract_payload["index_symbol"]).upper():
            return [_bar(index_epoch, symbol_upper, 25000.0, token=token_by_symbol[symbol_upper], universe_hash=universe_hash, provenance=provenance)]
        if symbol_upper in symbols:
            return [_bar(constituent_epoch, symbol_upper, 100.0, token=token_by_symbol[symbol_upper], universe_hash=universe_hash, provenance=provenance)]
        return []

    monkeypatch.setattr("core.market_event_graph_live_runtime_bridge.shadow_ohlc_buffer.get_completed_bars", bars)


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
        payload["subscription_request_succeeded_symbols"] = ["NIFTY", *list(_symbols()[:-1]), "WRONG"]
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


def test_duplicate_or_extra_subscription_identity_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload)

    def duplicated_evidence(contract):
        payload = _evidence(contract)
        payload["mode_request_succeeded_symbols"] = ["NIFTY", "NIFTY", *list(_symbols()), "OUTSIDE"]
        return payload

    bridge = LiveSourceRuntimeBridge(
        exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"),
        universe_contract=contract_payload,
        subscription_evidence_provider=duplicated_evidence,
    )

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION
    assert result.exported is False
    assert "OUTSIDE" in result.rejected_identities
    assert "NIFTY" in result.rejected_identities


def test_rejection_ledger_is_durable_and_separate_from_accepted_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    rejection_path = tmp_path / "rejections.jsonl"
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_REJECTION_PATH", str(rejection_path))
    output_path = tmp_path / "accepted.jsonl"
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(output_path), universe_contract=_contract())

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == "SUBSCRIPTION_REQUEST_FAILED"
    assert output_path.exists() is False
    rows = [json.loads(line) for line in rejection_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    (row,) = rows
    assert row["reason"] == "SUBSCRIPTION_REQUEST_FAILED"
    assert row["read_only"] is True
    assert row["broker_api_called"] is False


def test_default_subscription_provider_reads_feed_lifecycle_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload)

    def provider(token_by_symbol):
        assert token_by_symbol["NIFTY"] == 1
        payload = _evidence(contract_payload)
        payload.update({
            "subscription_evidence_id": "feed-proof",
            "feed_session_id": "feed-session-1",
            "reconnect_generation": 1,
            "token_by_symbol": token_by_symbol,
            "token_resolved_symbols": ["NIFTY", *list(_symbols())],
            "subscription_requested_symbols": ["NIFTY", *list(_symbols())],
            "subscription_request_succeeded_symbols": ["NIFTY", *list(_symbols())],
            "mode_request_succeeded_symbols": ["NIFTY", *list(_symbols())],
            "live_tick_observed_symbols": ["NIFTY", *list(_symbols())],
            "full_payload_observed_symbols": ["NIFTY", *list(_symbols())],
            "completed_bar_available_symbols": ["NIFTY", *list(_symbols())],
        })
        return payload

    monkeypatch.setattr("core.kite_depth_ws.market_event_graph_subscription_evidence_for_tokens", provider)
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"), universe_contract=contract_payload)

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.exported is True
    assert result.audit["subscription_evidence"]["subscription_evidence_id"] == "feed-proof"


def test_token_resolution_without_callback_proof_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    bridge = LiveSourceRuntimeBridge(exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"), universe_contract=contract_payload)

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == "SUBSCRIPTION_REQUEST_FAILED"
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
        "symbol": "NIFTY",
        "live_feed_session_id": "feed-session-1",
        "reconnect_generation": 1,
        "instrument_token": 1,
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "universe_hash": "",
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


def test_reconnect_generation_stale_bar_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE", True)
    contract_payload = _contract()
    _install_bars(monkeypatch, contract_payload=contract_payload)

    def generation_two_evidence(contract):
        payload = _evidence(contract)
        payload["reconnect_generation"] = 2
        for row in payload["token_lifecycle"].values():
            row["reconnect_generation"] = 2
        return payload

    bridge = LiveSourceRuntimeBridge(
        exporter=LiveCapturedMetadataExporter(tmp_path / "out.jsonl"),
        universe_contract=contract_payload,
        subscription_evidence_provider=generation_two_evidence,
    )

    result = bridge.observe_cycle([], cycle_cutoff=datetime.fromtimestamp(130.0, tz=timezone.utc))

    assert result.reason == RECONNECT_GENERATION_MISMATCH
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
