"""Unit Tests for Broker Position Reconciler
===========================================
Verifies that pre-reset reconciliation detects broker open positions,
blocks destructive WAL wipes, and re-attaches APM into STATE_IN_FLIGHT with trailing stops.

Safety Invariants:
read_only = True
is_order_action = False
broker_api_called = True
allowed_for_live_execution = False
"""

import json
import pytest
from pathlib import Path

from core.reconciliation.broker_position_reconciler import (
    BrokerPositionReconciler,
    ReconciledPosition,
)
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
)


class MockBrokerAdapter:
    def __init__(self, positions=None):
        self._positions = positions or []

    def fetch_open_positions(self):
        return self._positions


def test_safety_invariants(tmp_path):
    wal_file = tmp_path / "runtime" / "sentinel_apm_wal.json"
    reconciler = BrokerPositionReconciler(broker=MockBrokerAdapter([]))
    res = reconciler.reconcile_before_wal_reset(wal_file, index_name="NIFTY")
    assert res.read_only is True
    assert res.is_order_action is False
    assert res.broker_api_called is True
    assert res.allowed_for_live_execution is False


def test_no_open_positions_permits_wal_reset(tmp_path):
    wal_file = tmp_path / "runtime" / "sentinel_apm_wal.json"
    reconciler = BrokerPositionReconciler(broker=MockBrokerAdapter([]))
    res = reconciler.reconcile_before_wal_reset(wal_file, index_name="NIFTY")
    
    assert res.has_open_positions is False
    assert res.wal_reset_permitted is True
    assert res.reattached_apm is False


def test_open_position_blocks_wal_reset_and_reattaches(tmp_path):
    wal_file = tmp_path / "runtime" / "sentinel_apm_wal.json"
    wal_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Simulate a prior WAL state
    with open(wal_file, "w") as f:
        json.dump({"state": "STANDBY", "payload": None}, f)

    mock_positions = [
        {
            "trading_symbol": "NIFTY 25200 PE 17 NOV 26",
            "instrument_token": "NSE_FO|45408",
            "net_quantity": 75,
            "average_price": 18.65,
        }
    ]

    broker = MockBrokerAdapter(mock_positions)
    reconciler = BrokerPositionReconciler(broker=broker)

    res = reconciler.reconcile_before_wal_reset(wal_file, index_name="NIFTY")

    assert res.has_open_positions is True
    assert res.wal_reset_permitted is False  # Destructive reset BLOCKED!
    assert res.reattached_apm is True
    assert len(res.open_positions) == 1
    assert res.open_positions[0].symbol == "NIFTY 25200 PE 17 NOV 26"
    assert res.open_positions[0].avg_price == 18.65

    # Verify WAL was updated to STATE_IN_FLIGHT with trailing stops preserved
    with open(wal_file, "r") as f:
        wal_data = json.load(f)

    assert wal_data["state"] == "IN_FLIGHT"
    assert wal_data["payload"]["symbol"] == "NIFTY 25200 PE 17 NOV 26"
    assert wal_data["payload"]["entry_price"] == 18.65
    assert wal_data["payload"]["highest_price"] >= 18.65
    assert wal_data["recovery_source"] == "BROKER_POSITION_RECONCILER"


def test_reattach_apm_in_memory_instance(tmp_path):
    wal_file = tmp_path / "runtime" / "test_apm_wal.json"
    apm = ActivePositionManager(wal_path=wal_file)
    assert apm.state == STATE_STANDBY

    mock_positions = [
        {
            "trading_symbol": "NIFTY 25450 CE 17 NOV 26",
            "instrument_token": "NSE_FO|45409",
            "net_quantity": 75,
            "average_price": 16.40,
        }
    ]
    reconciler = BrokerPositionReconciler(broker=MockBrokerAdapter(mock_positions))
    ok = reconciler.reattach_apm_instance(apm, index_name="NIFTY")

    assert ok is True
    assert apm.state == STATE_IN_FLIGHT
    assert apm.payload is not None
    assert apm.payload.opt_symbol == "NIFTY 25450 CE 17 NOV 26" or apm.payload.strike_contract == "NIFTY 25450 CE 17 NOV 26"
    assert apm.payload.entry_price == 16.40


class FailingBrokerAdapter:
    def fetch_open_positions(self):
        raise ConnectionError("Broker gateway timeout (504 Gateway Timeout)")


def test_vector5_fail_closed_on_broker_exception(tmp_path):
    """Vector 5: Broker exceptions/timeouts MUST fail-closed:
    wal_reset_permitted = False, status = 'ERROR_FAIL_CLOSED', has_open_positions = False.
    """
    wal_file = tmp_path / "runtime" / "sentinel_apm_wal.json"
    wal_file.parent.mkdir(parents=True, exist_ok=True)
    with open(wal_file, "w") as f:
        json.dump({"state": "IN_FLIGHT", "payload": {"symbol": "NIFTY 25000 CE"}}, f)

    reconciler = BrokerPositionReconciler(broker=FailingBrokerAdapter())
    res = reconciler.reconcile_before_wal_reset(wal_file, index_name="NIFTY")

    assert res.wal_reset_permitted is False
    assert res.status == "ERROR_FAIL_CLOSED"
    assert res.has_open_positions is False
    assert res.open_positions == []
    assert "FAILED" in res.message or "Fail-closed" in res.message
