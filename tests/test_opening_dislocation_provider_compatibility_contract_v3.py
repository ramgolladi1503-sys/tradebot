from __future__ import annotations

from research.opening_dislocation_reversal.fresh_epoch_reconciliation_v3 import (
    compatibility_contract,
    reject_local_source,
)


def test_provider_overlap_floor_and_gate_immutability():
    contract = compatibility_contract()
    assert contract["minimum_overlap_sessions"] == 60
    assert contract["preferred_overlap_sessions"] == 120
    assert contract["gate_immutability"] == "FROZEN_BEFORE_PROVIDER_COMPARISON"


def test_provider_mixing_is_prohibited_before_compatibility_pass():
    assert compatibility_contract()["provider_mixing_allowed_before_pass"] is False


def test_local_inventory_rejects_futures_options_and_etf():
    assert reject_local_source("nifty_futures_1m.parquet", {}) == "REJECT_FUTURES_DATA"
    assert reject_local_source("nifty_options_1m.parquet", {}) == "REJECT_OPTION_DATA"
    assert reject_local_source("niftybees_etf_1m.parquet", {}) == "REJECT_ETF_DATA"


def test_local_inventory_does_not_auto_qualify_unproven_nifty_source():
    assert reject_local_source("nifty_50_1m.csv", {}) == "REQUIRES_MANUAL_PROVENANCE_REVIEW"
