"""Tests for Aixion TradeBot Pocket Read-Only Companion API."""

import pytest
from fastapi.testclient import TestClient
from pocket_companion.service import app, POCKET_API_KEY


client = TestClient(app)


def test_health_unauthorized():
    res = client.get("/health")
    assert res.status_code == 401


def test_health_authorized():
    res = client.get("/health", headers={"X-Aixion-Pocket-Key": POCKET_API_KEY})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ONLINE"
    assert data["read_only"] is True
    assert data["is_order_action"] is False
    assert data["broker_api_called"] is False
    assert data["allowed_for_live_execution"] is False
    assert data["mac_awake"] is True


def test_positions_authorized():
    res = client.get("/positions", headers={"X-Aixion-Pocket-Key": POCKET_API_KEY})
    assert res.status_code == 200
    data = res.json()
    assert "positions" in data
    assert "total_realized_pnl" in data
    assert isinstance(data["positions"], list)


def test_market_authorized():
    res = client.get("/market", headers={"X-Aixion-Pocket-Key": POCKET_API_KEY})
    assert res.status_code == 200
    data = res.json()
    assert "indices" in data


def test_signals_authorized():
    res = client.get("/signals", headers={"X-Aixion-Pocket-Key": POCKET_API_KEY})
    assert res.status_code == 200
    data = res.json()
    assert "events" in data


def test_strict_read_only_no_order_routes():
    # Verify that order mutation endpoints DO NOT exist
    for method in [client.post, client.put, client.delete]:
        res = method("/order", headers={"X-Aixion-Pocket-Key": POCKET_API_KEY})
        assert res.status_code in [404, 405]
        res = method("/orders", headers={"X-Aixion-Pocket-Key": POCKET_API_KEY})
        assert res.status_code in [404, 405]
        res = method("/trade", headers={"X-Aixion-Pocket-Key": POCKET_API_KEY})
        assert res.status_code in [404, 405]
