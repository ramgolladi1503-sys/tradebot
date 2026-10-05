from __future__ import annotations

import pytest

from config import config as cfg
import core.kite_depth_ws as depth_ws


@pytest.fixture
def underlying_identity_setup(monkeypatch):
    now_epoch = 1_800_000_000.0
    token = 256265
    identity = {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "feed_session_id": "session-source-freshness-test",
        "feed_epoch": 17,
        "reconnect_generation": 4,
        "connection_start_epoch": now_epoch - 10.0,
    }
    lifecycle = {
        "symbol": "NIFTY",
        "instrument_token": token,
        "feed_session_id": identity["feed_session_id"],
        "feed_epoch": identity["feed_epoch"],
        "reconnect_generation": identity["reconnect_generation"],
        "latest_callback_receipt_epoch": now_epoch - 0.2,
        "latest_source_tick_epoch": now_epoch - 0.3,
    }
    evidence_producer = depth_ws.market_event_graph_subscription_evidence_for_tokens

    monkeypatch.setattr(
        depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {token: "NIFTY"}, raising=False
    )
    monkeypatch.setattr(depth_ws, "_INDEX_SYMBOLS", {"NIFTY"}, raising=False)
    monkeypatch.setattr(depth_ws, "_LAST_TOKENS", [token], raising=False)
    monkeypatch.setattr(
        depth_ws, "_LAST_CALLBACK_RECEIPT_EPOCH_BY_TOKEN", {token: now_epoch - 0.2}
    )
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {token: now_epoch - 0.2})
    monkeypatch.setattr(depth_ws, "get_current_feed_session_identity", lambda: identity)
    monkeypatch.setattr(cfg, "LTP_SLA_SECONDS", 2.5, raising=False)
    monkeypatch.setattr(
        depth_ws,
        "market_event_graph_subscription_evidence_for_tokens",
        lambda _tokens: {
            "subscription_request_succeeded_symbols": ["NIFTY"],
            "token_lifecycle": {str(token): lifecycle},
        },
    )
    return now_epoch, identity, lifecycle, evidence_producer


def _health(now_epoch, identity):
    return depth_ws._underlying_feed_identity_by_symbol(
        now_epoch=now_epoch,
        ws_connected=True,
        session_identity=identity,
    )["NIFTY"]


def test_fresh_receipt_and_fresh_source_are_healthy(underlying_identity_setup):
    now_epoch, identity, lifecycle, _ = underlying_identity_setup

    row = _health(now_epoch, identity)

    assert row["status"] == "HEALTHY"
    assert row["receipt_age_sec"] == pytest.approx(0.2)
    assert row["source_age_sec"] == pytest.approx(0.3)
    assert row["age_sec"] == row["receipt_age_sec"]
    assert lifecycle["latest_callback_receipt_epoch"] == row["receipt_epoch"]
    assert lifecycle["latest_source_tick_epoch"] == row["source_epoch"]


def test_fresh_receipt_does_not_mask_stale_source(underlying_identity_setup):
    now_epoch, identity, lifecycle, _ = underlying_identity_setup
    lifecycle["latest_source_tick_epoch"] = now_epoch - 3.0

    row = _health(now_epoch, identity)

    assert row["status"] == "UNHEALTHY"
    assert row["receipt_age_sec"] == pytest.approx(0.2)
    assert row["source_age_sec"] == pytest.approx(3.0)
    assert row["source_age_sec"] > row["max_age_sec"]


def test_fresh_source_does_not_mask_stale_raw_receipt(underlying_identity_setup):
    now_epoch, identity, lifecycle, _ = underlying_identity_setup
    lifecycle["latest_callback_receipt_epoch"] = now_epoch - 3.0
    lifecycle["latest_source_tick_epoch"] = now_epoch - 0.2

    row = _health(now_epoch, identity)

    assert row["status"] == "UNHEALTHY"
    assert row["receipt_age_sec"] == pytest.approx(3.0)
    assert row["source_age_sec"] == pytest.approx(0.2)
    assert row["receipt_age_sec"] > row["max_age_sec"]


def test_subscription_evidence_uses_raw_callback_receipt_epoch(
    monkeypatch, underlying_identity_setup
):
    now_epoch, _, _, evidence_producer = underlying_identity_setup
    token = 256265
    raw_receipt_epoch = now_epoch - 0.7
    normalized_message_epoch = now_epoch - 0.1
    monkeypatch.setattr(
        depth_ws, "_LAST_CALLBACK_RECEIPT_EPOCH_BY_TOKEN", {token: raw_receipt_epoch}
    )
    monkeypatch.setattr(depth_ws, "_LAST_MSG_TS_BY_TOKEN", {token: normalized_message_epoch})

    evidence = evidence_producer({"NIFTY": token})
    lifecycle = evidence["token_lifecycle"][str(token)]

    assert lifecycle["latest_callback_receipt_epoch"] == raw_receipt_epoch
    assert lifecycle["latest_message_epoch"] == normalized_message_epoch


@pytest.mark.parametrize("source_timestamp", [None, 1_800_000_001.0, float("nan")])
def test_missing_future_or_non_finite_source_is_not_healthy(
    underlying_identity_setup, source_timestamp
):
    now_epoch, identity, lifecycle, _ = underlying_identity_setup
    lifecycle["latest_source_tick_epoch"] = source_timestamp

    row = _health(now_epoch, identity)

    assert row["status"] == "UNHEALTHY"
    assert row["receipt_age_sec"] == pytest.approx(0.2)
