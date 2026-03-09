from __future__ import annotations

import json
from pathlib import Path

from core.review_queue import _normalize_queue_row


_STATE_RANK = {
    "NEW": 0,
    "CANDIDATE": 1,
    "APPROVED": 2,
    "SUBMITTED": 3,
    "FILLED": 4,
    "REJECTED": 5,
    "CANCELLED": 6,
}


def _state_key(row: dict) -> str:
    state = str(row.get("trade_state_v1") or row.get("status") or "").strip().upper()
    return state or "NEW"


def _state_rank(row: dict) -> int:
    return int(_STATE_RANK.get(_state_key(row), -1))


def _fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "sample_trade_event.json"


def test_trade_json_contract_fixture_keys_are_present_in_serializer_output() -> None:
    fixture = json.loads(_fixture_path().read_text(encoding="utf-8"))
    out = _normalize_queue_row(dict(fixture))

    missing = [key for key in fixture.keys() if key not in out]
    assert not missing, f"serializer_missing_keys={missing}"


def test_trade_contract_requires_expected_entry_for_approved_or_later() -> None:
    row = _normalize_queue_row(
        {
            "trade_id": "T-CONTRACT-APPROVED",
            "trade_state_v1": "APPROVED",
            "status": "APPROVED",
            "snapshot_id": "snap-approved-1",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "tradingsymbol": "NIFTY26MAR24500CE",
            "option_type": "CE",
            "expiry_date": "2026-03-26",
            "strike": 24500.0,
            "suggested_entry": 102.4,
            "entry_status": "OK",
            "timestamp": "2026-03-04T09:20:00Z",
        }
    )

    assert _state_rank(row) >= _STATE_RANK["APPROVED"]
    assert row.get("expected_entry") is not None
    assert row.get("entry_price") is not None


def test_trade_contract_requires_fill_entry_for_filled() -> None:
    row = _normalize_queue_row(
        {
            "trade_id": "T-CONTRACT-FILLED",
            "trade_state_v1": "FILLED",
            "status": "FILLED",
            "snapshot_id": "snap-filled-1",
            "symbol": "NIFTY",
            "instrument": "OPT",
            "tradingsymbol": "NIFTY26MAR24500CE",
            "option_type": "CE",
            "expiry_date": "2026-03-26",
            "strike": 24500.0,
            "entry": 101.0,
            "fill_price": 103.5,
            "entry_status": "OK",
            "timestamp": "2026-03-04T09:20:00Z",
        }
    )

    assert _state_key(row) == "FILLED"
    assert row.get("fill_entry") is not None
    assert row.get("entry_price") is not None
