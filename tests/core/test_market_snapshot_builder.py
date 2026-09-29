from __future__ import annotations

import hashlib
import json
import time

from config import config as cfg
from core.contracts.invariants import assert_invariants
from core.market_snapshot_builder import build_market_snapshot
from core.tick_store import insert_tick


def _setup_runtime(monkeypatch, tmp_path):
    db_path = tmp_path / "snapshot_builder.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 1, raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 1, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_STALE_QUOTES", False, raising=False)
    monkeypatch.setattr(cfg, "SLA_REQUIRE_OPTIONS_DEPTH_LIVE", False, raising=False)
    monkeypatch.setattr("core.freshness_sla.is_market_open_ist", lambda: True)
    return db_path


def test_build_market_snapshot_passes_invariants(monkeypatch, tmp_path):
    _setup_runtime(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    index_token = 256265
    option_tokens = [910001, 910002]

    assert insert_tick(ts=now_epoch - 1.0, token=index_token, last_price=24700.0, volume=100, oi=0)
    assert insert_tick(ts=now_epoch - 1.0, token=option_tokens[0], last_price=102.5, volume=50, oi=1000)
    assert insert_tick(ts=now_epoch - 0.8, token=option_tokens[1], last_price=98.2, volume=55, oi=900)

    snapshot = build_market_snapshot(
        "NIFTY",
        index_token=index_token,
        option_tokens=option_tokens,
        strike_window={"atm": 24700, "step": 50, "around": 6},
        expiry_date="2026-03-02",
    )

    assert snapshot["schema_version"] == "1.0"
    assert snapshot["symbol"] == "NIFTY"
    assert snapshot["snapshot_id"]
    assert snapshot["token_coverage"]["option_tokens_count"] == 2
    assert snapshot["health"]["ok"] is True
    option_tick = snapshot["ticks"]["options"][str(option_tokens[1])]
    assert option_tick["source_event_id"] is None
    assert option_tick["timestamp_authority"] is None
    assert_invariants(snapshot, stage="unit_test")


def test_market_snapshot_preserves_index_callback_event_envelope(monkeypatch, tmp_path):
    _setup_runtime(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    token = 256265
    source_payload = {
        "instrument_token": token, "underlying_symbol": "NIFTY", "last_price": 24700.0,
        "volume": 100, "oi": 0, "source_timestamp_field": "exchange_timestamp",
        "source_timestamp_epoch": now_epoch,
    }
    source_hash = hashlib.sha256(json.dumps(source_payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    assert insert_tick(
        ts=now_epoch, token=token, last_price=24700.0, volume=100, oi=0,
        timestamp_authority="EXCHANGE_TIMESTAMP", timestamp_source_field="exchange_timestamp",
        source_timestamp_epoch=now_epoch, receive_timestamp_epoch=now_epoch + 0.1,
        timestamp_fallback_used=False, source_event_id=f"feed:1:{token}:{source_hash[:16]}",
        source_event_sha256=source_hash, source_event_payload=source_payload,
    )
    assert insert_tick(ts=now_epoch, token=910001, last_price=100.0, volume=1, oi=1)
    snapshot = build_market_snapshot(
        "NIFTY", index_token=token, option_tokens=[910001],
        strike_window={"atm": 24700, "step": 50, "around": 1}, expiry_date="2026-10-01",
    )
    index_tick = snapshot["ticks"]["index"]
    assert index_tick["source_event_id"] == f"feed:1:{token}:{source_hash[:16]}"
    assert index_tick["source_event_payload"] == source_payload


def test_build_market_snapshot_stale_ticks_sets_blocker(monkeypatch, tmp_path):
    _setup_runtime(monkeypatch, tmp_path)
    now_epoch = float(time.time())
    index_token = 256265
    option_token = 920001

    assert insert_tick(ts=now_epoch - 200.0, token=index_token, last_price=24700.0, volume=100, oi=0)
    assert insert_tick(ts=now_epoch - 200.0, token=option_token, last_price=104.1, volume=42, oi=1200)

    snapshot = build_market_snapshot(
        "NIFTY",
        index_token=index_token,
        option_tokens=[option_token],
        strike_window={"atm": 24700, "step": 50, "around": 6},
        expiry_date="2026-03-02",
    )

    assert snapshot["health"]["ok"] is False
    blocker_codes = [str(item.get("code")) for item in list(snapshot["health"]["blockers"] or [])]
    assert "FRESHNESS_FAILED" in blocker_codes
    assert_invariants(snapshot, stage="unit_test")
