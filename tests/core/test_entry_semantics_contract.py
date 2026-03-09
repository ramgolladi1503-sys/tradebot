from __future__ import annotations

import pytest

from core.entry_semantics import EntryContractViolation, enforce_entry_contract
from core.review_queue import _normalize_queue_row


def test_contract_requires_snapshot_id_for_approved_or_later_state():
    row = {"trade_id": "T-1", "status": "APPROVED", "expected_entry": 101.5}
    with pytest.raises(EntryContractViolation) as exc:
        enforce_entry_contract(row, stage="unit_test")
    assert exc.value.code == "ENTRY_CONTRACT_MISSING_SNAPSHOT_ID"


def test_contract_derives_expected_entry_for_approved_state():
    row = {
        "trade_id": "T-2",
        "status": "APPROVED",
        "snapshot_id": "snap-001",
        "mark_price": 99.25,
    }
    out = enforce_entry_contract(row, stage="unit_test")
    assert out["snapshot_id"] == "snap-001"
    assert float(out["expected_entry"]) == 99.25


def test_contract_requires_fill_entry_for_filled_state():
    row = {
        "trade_id": "T-3",
        "status": "FILLED",
        "snapshot_id": "snap-002",
        "expected_entry": 88.0,
    }
    with pytest.raises(EntryContractViolation) as exc:
        enforce_entry_contract(row, stage="unit_test")
    assert exc.value.code == "ENTRY_CONTRACT_MISSING_FILL_ENTRY"


def test_contract_derives_fill_entry_from_fill_price_for_filled_state():
    row = {
        "trade_id": "T-4",
        "status": "FILLED",
        "snapshot_id": "snap-003",
        "expected_entry": 150.0,
        "fill_price": 151.2,
    }
    out = enforce_entry_contract(row, stage="unit_test")
    assert float(out["fill_entry"]) == 151.2


def test_review_queue_normalizer_keeps_expected_entry_for_approved_row():
    row = _normalize_queue_row(
        {
            "trade_id": "T-5",
            "symbol": "NIFTY",
            "status": "APPROVED",
            "snapshot_id": "snap-004",
            "suggested_entry": 221.4,
            "timestamp": "2026-03-04T09:20:00Z",
        }
    )
    assert row["status"] == "APPROVED"
    assert float(row["expected_entry"]) == 221.4
