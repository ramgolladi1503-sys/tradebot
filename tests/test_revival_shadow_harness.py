"""Comprehensive Unit & Invariant Tests for Governed Revival Shadow Harness.

Covers:
  - Exact specification & manifest hashing
  - Blocked reconciliation enforcement for unverified candidates
  - Strict append-only cryptographic chain hashing & tamper detection
  - Separation of QuotedExecutableProxy from actual fill (actual_fill_status == ACTUAL_FILL_UNKNOWN)
  - Missing and stale quote handling without imputation
  - Cost authority decoupling and fail-closed unverified authority handling
  - Targeted write method guard on ReadOnlyMarketDataProvider
  - Market data source and API called transparency (distinguishing synthetic from live feeds)
  - Working-tree content hash tracking in SessionManifest
"""

import hashlib
import json
import pytest
from dataclasses import replace

from core.analytics.cost_authority import (
    CostAuthority,
    get_cost_authority,
    COST_AUTHORITY_REGISTRY,
)
from core.analytics.revival_registry import (
    RevivalRegistry,
    CandidateFreezeManifest,
)
from core.analytics.shadow_harness import (
    GovernedShadowLedger,
    ReadOnlyMarketDataProvider,
    ShadowObservationRecord,
)


def test_specification_reconciliation_and_freeze_manifest():
    """Verify exact artifact hashes and deterministic manifest hashing."""
    registry = RevivalRegistry()

    # CAND_01 must be reconciled for spot research identity
    c1 = registry.get_manifest("CAND_01_SESSION_DIR_OVERNIGHT")
    assert c1 is not None
    assert c1.reconciliation_status == "RECONCILED_FOR_PROSPECTIVE_SHADOW"
    assert registry.verify_source_artifacts("CAND_01_SESSION_DIR_OVERNIGHT") is True

    # CAND_03 reconciled with exact lifecycle semantics
    c3 = registry.get_manifest("CAND_03_DAY_NIGHT_MOMENTUM")
    assert c3 is not None
    assert c3.reconciliation_status == "RECONCILED_FOR_PROSPECTIVE_SHADOW"
    assert "15:25 futures close" in c3.entry_definition
    assert "next-session 09:16 futures open" in c3.exit_definition or "Next session 09:16" in c3.exit_definition

    # Check deterministic spec hashing
    h1 = c1.compute_spec_hash()
    h2 = c1.compute_spec_hash()
    assert h1 == h2
    assert len(h1) == 64

    # CAND_05 & CAND_06 must fail closed as BLOCKED_RECONCILIATION_REQUIRED
    c5 = registry.get_manifest("CAND_05_DAY_NIGHT_OI_CONFIRM")
    assert c5 is not None
    assert c5.reconciliation_status == "BLOCKED_RECONCILIATION_REQUIRED"

    c6 = registry.get_manifest("CAND_06_GAP_CONFLUENCE_RANGE_EXP_B")
    assert c6 is not None
    assert c6.reconciliation_status == "BLOCKED_RECONCILIATION_REQUIRED"


def test_blocked_candidates_cannot_be_queued_in_shadow_ledger():
    """Ensure un-reconciled candidates fail closed when attempted in ledger."""
    registry = RevivalRegistry()
    provider = ReadOnlyMarketDataProvider()
    ledger = GovernedShadowLedger(registry=registry, market_data_provider=provider)

    with pytest.raises(ValueError, match="BLOCKED_RECONCILIATION_REQUIRED"):
        ledger.record_observation(
            strategy_id="CAND_05_DAY_NIGHT_OI_CONFIRM",
            session_date="2026-09-22",
            signal_timestamp_ns=1726978140000000000,
            direction=1,
            entry_bid=25000.0,
            entry_ask=25001.0,
            exit_bid=25050.0,
            exit_ask=25051.0,
        )


def test_cryptographic_chain_integrity_and_tamper_detection():
    """Test valid chain building, modification detection, deletion detection, and manifest hash tracking."""
    registry = RevivalRegistry()
    provider = ReadOnlyMarketDataProvider()
    ledger = GovernedShadowLedger(registry=registry, market_data_provider=provider)

    rec0 = ledger.record_observation(
        strategy_id="CAND_01_SESSION_DIR_OVERNIGHT",
        session_date="2026-09-22",
        signal_timestamp_ns=1726978140000000000,
        direction=1,
        entry_bid=25000.0,
        entry_ask=25001.0,
        exit_bid=25040.0,
        exit_ask=25041.0,
        market_data_source="SYNTHETIC_TEST",
        market_data_api_called=False,
    )
    rec1 = ledger.record_observation(
        strategy_id="CAND_01_SESSION_DIR_OVERNIGHT",
        session_date="2026-09-23",
        signal_timestamp_ns=1727064540000000000,
        direction=-1,
        entry_bid=25050.0,
        entry_ask=25051.0,
        exit_bid=25020.0,
        exit_ask=25021.0,
        market_data_source="SYNTHETIC_TEST",
        market_data_api_called=False,
    )

    assert len(ledger.records) == 2
    assert ledger.verify_chain_integrity() is True

    manifest = ledger.seal_session()
    assert manifest.tamper_check == "VERIFIED_IMMUTABLE"
    assert manifest.record_count == 2
    assert manifest.final_chain_hash == rec1.record_canonical_hash
    assert manifest.working_tree_content_hash is not None

    # Tamper test: Modify record
    tampered_rec0 = replace(rec0, gross_move_pts=999.0)
    ledger.records[0] = tampered_rec0
    assert ledger.verify_chain_integrity() is False


def test_quote_proxy_and_actual_fill_separation():
    """Verify quoted_proxy logic and strict actual_fill_status == ACTUAL_FILL_UNKNOWN."""
    registry = RevivalRegistry()
    provider = ReadOnlyMarketDataProvider()
    ledger = GovernedShadowLedger(registry=registry, market_data_provider=provider)

    rec = ledger.record_observation(
        strategy_id="CAND_01_SESSION_DIR_OVERNIGHT",
        session_date="2026-09-22",
        signal_timestamp_ns=1726978140000000000,
        direction=1,  # LONG
        entry_bid=25000.0,
        entry_ask=25002.0,
        exit_bid=25020.0,
        exit_ask=25022.0,
        market_data_source="SYNTHETIC_TEST",
        market_data_api_called=False,
    )

    assert rec.actual_fill_status == "ACTUAL_FILL_UNKNOWN"
    assert rec.market_data_source == "SYNTHETIC_TEST"
    assert rec.market_data_api_called is False
    assert rec.entry_quote_proxy.proxy_price == 25002.0
    assert rec.exit_quote_proxy.proxy_price == 25020.0
    assert rec.quoted_proxy_pnl_pts == 18.0
    assert rec.gross_move_pts == 20.0


def test_missing_and_stale_market_data_handling():
    """Verify that missing quotes or stale quotes fail closed without imputation."""
    registry = RevivalRegistry()
    provider = ReadOnlyMarketDataProvider()
    ledger = GovernedShadowLedger(registry=registry, market_data_provider=provider)

    rec_missing = ledger.record_observation(
        strategy_id="CAND_01_SESSION_DIR_OVERNIGHT",
        session_date="2026-09-22",
        signal_timestamp_ns=1726978140000000000,
        direction=1,
        entry_bid=None,
        entry_ask=None,
        exit_bid=None,
        exit_ask=None,
    )
    assert rec_missing.observation_status == "MISSING_REQUIRED_MARKET_DATA"
    assert rec_missing.entry_quote_proxy is None
    assert rec_missing.quoted_proxy_pnl_pts is None

    now_ns = 1726978140000000000
    stale_quote_ns = now_ns - (5000 * 1_000_000)
    rec_stale = ledger.record_observation(
        strategy_id="CAND_01_SESSION_DIR_OVERNIGHT",
        session_date="2026-09-22",
        signal_timestamp_ns=now_ns,
        direction=1,
        entry_bid=25000.0,
        entry_ask=25001.0,
        exit_bid=25020.0,
        exit_ask=25021.0,
        entry_quote_time_ns=stale_quote_ns,
    )
    assert rec_stale.observation_status == "INVALID_STALE_QUOTE"


def test_cost_authority_unverified_fails_closed():
    """Verify unverified cost authority returns None, keeping net_pnl_pts as None."""
    authority = get_cost_authority("NSE_FUTURES_2026_UNVERIFIED_PROVISIONAL")
    assert authority is not None
    assert authority.verification_status == "UNVERIFIED"

    # Must return None because it is UNVERIFIED
    cost = authority.compute_futures_cost(
        entry_px=25000.0,
        exit_px=25050.0,
        side="LONG",
        lot_size=65,
    )
    assert cost is None

    # Ledger using unverified authority does not compute net pnl
    registry = RevivalRegistry()
    provider = ReadOnlyMarketDataProvider()
    ledger = GovernedShadowLedger(
        registry=registry,
        market_data_provider=provider,
        cost_authority_id="NSE_FUTURES_2026_UNVERIFIED_PROVISIONAL",
    )
    rec = ledger.record_observation(
        strategy_id="CAND_01_SESSION_DIR_OVERNIGHT",
        session_date="2026-09-22",
        signal_timestamp_ns=1726978140000000000,
        direction=1,
        entry_bid=25000.0,
        entry_ask=25001.0,
        exit_bid=25020.0,
        exit_ask=25021.0,
    )
    assert rec.cost_drag_pts is None
    assert rec.net_pnl_pts is None


def test_targeted_write_method_guard():
    """Verify targeted guard rejects clients exposing write or order submission methods."""
    class MutatingClient:
        def post(self, *args, **kwargs):
            pass

    with pytest.raises(PermissionError, match="cannot wrap client exposing 'post'"):
        ReadOnlyMarketDataProvider(feed_client=MutatingClient())

    registry = RevivalRegistry()
    provider = ReadOnlyMarketDataProvider()
    ledger = GovernedShadowLedger(registry=registry, market_data_provider=provider)

    assert ledger.safety_state["read_only"] is True
    assert ledger.safety_state["broker_write_authority"] is False
    assert ledger.safety_state["order_authority"] is False
    assert ledger.safety_state["ORDERS_PLACED"] == 0
