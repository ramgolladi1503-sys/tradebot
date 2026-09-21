"""Tests for MEG Live Source Bridge interval state machine: unchanged vs regression."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.market_event_graph_live_runtime_bridge import LiveSourceRuntimeBridge, LiveUniverseContract


def test_bridge_interval_state_machine_distinguishes_unchanged_from_regression():
    contract = LiveUniverseContract(
        schema_version=1,
        broker_provider="kite",
        token_domain="kite_instrument_token",
        name="NIFTY 50 Live",
        version="1.0.0",
        effective_date="2026-07-30",
        source_retrieval_date="2026-07-30",
        source_page_updated_date="2026-07-30",
        official_source_url="https://test.local",
        official_raw_sha256="test_sha",
        index_symbol="NIFTY",
        index_instrument_token=256265,
        provider_native_index_identifier="NSE:NIFTY 50",
        constituents=(),
        broker_instrument_master={},
        source_provenance="test",
        capture_session_id="test",
        canonical_sha256="test_canonical",
    )

    bridge = LiveSourceRuntimeBridge(universe_contract=contract.__dict__)
    bridge._last_source_bar_end_epoch = 1000.0

    # Case 1: Identical interval end epoch -> IDLE_UNCHANGED_INTERVAL (no error/warning)
    bridge._completed_bar_for = MagicMock(return_value={"ts": datetime.fromtimestamp(1000.0, tz=timezone.utc), "source_bar_end_epoch": 1000.0})
    snapshot, reason, affected = bridge._assemble_snapshot(contract, {}, cycle_cutoff=datetime.fromtimestamp(1050.0, tz=timezone.utc))
    assert snapshot is None
    assert reason == "IDLE_UNCHANGED_INTERVAL"

    # Case 2: Older interval end epoch -> TIME_REGRESSION (invariant fault)
    bridge._completed_bar_for = MagicMock(return_value={"ts": datetime.fromtimestamp(940.0, tz=timezone.utc), "source_bar_end_epoch": 940.0})
    snapshot, reason, affected = bridge._assemble_snapshot(contract, {}, cycle_cutoff=datetime.fromtimestamp(1050.0, tz=timezone.utc))
    assert snapshot is None
    assert reason == "TIME_REGRESSION"
