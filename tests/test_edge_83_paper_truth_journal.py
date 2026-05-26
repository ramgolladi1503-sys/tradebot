from __future__ import annotations

import json

import pytest

from core.paper_truth_journal import (
    EVENT_HASH_MISMATCH,
    INVALID_EVENT_TYPE,
    INVALID_JSON_LINE,
    INVALID_MODE,
    PAPER_EVENT_CANDIDATE_ACCEPTED,
    PAPER_EVENT_ENTRY_RECORDED,
    PAPER_EVENT_EXIT_RECORDED,
    PAPER_MODE,
    PREVIOUS_HASH_MISMATCH,
    SEQUENCE_GAP,
    VALIDATION_OK,
    append_paper_truth_event,
    build_paper_truth_event,
    read_paper_truth_events,
    validate_paper_truth_events,
    validate_paper_truth_journal,
)

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


def _event_kwargs() -> dict[str, object]:
    return {
        "event_type": PAPER_EVENT_CANDIDATE_ACCEPTED,
        "sequence": 1,
        "candidate_id": "cand-1",
        "strategy_id": "breakout_v1",
        "symbol": "nifty",
        "side": "buy",
        "quantity": 50,
        "price": 101.25,
        "payload": {"quality_gate": "passed"},
        "metadata": {"test": "edge_83"},
        "event_ts_epoch": 1772202600.0,
    }


def test_build_paper_truth_event_is_deterministic_and_non_action():
    first = build_paper_truth_event(**_event_kwargs())
    second = build_paper_truth_event(**_event_kwargs())

    assert first.event_id == second.event_id
    assert first.event_hash == second.event_hash
    payload = first.to_payload()
    assert payload["mode"] == PAPER_MODE
    assert payload["symbol"] == "NIFTY"
    assert payload["side"] == "BUY"
    assert payload["read_only"] is True
    assert payload["append"] is True
    assert payload[_ACTION_KEY] is False
    assert payload[_BROKER_KEY] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_append_read_and_validate_journal_sequence(tmp_path):
    journal = tmp_path / "paper_truth.jsonl"

    first = append_paper_truth_event(
        journal,
        event_type=PAPER_EVENT_CANDIDATE_ACCEPTED,
        candidate_id="cand-1",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=101.25,
        event_ts_epoch=1772202600.0,
    )
    second = append_paper_truth_event(
        journal,
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        candidate_id="cand-1",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=102.0,
        event_ts_epoch=1772202660.0,
    )

    events = read_paper_truth_events(journal)
    validation = validate_paper_truth_journal(journal)

    assert [event["sequence"] for event in events] == [1, 2]
    assert second.previous_event_hash == first.event_hash
    assert validation.journal_valid is True
    assert validation.reason_code == VALIDATION_OK
    assert validation.event_count == 2
    assert validation.latest_sequence == 2
    assert validation.latest_event_hash == second.event_hash


def test_validation_detects_tampered_event_hash():
    event = build_paper_truth_event(**_event_kwargs()).to_payload()
    event["price"] = 999.0

    validation = validate_paper_truth_events([event])

    assert validation.journal_valid is False
    assert EVENT_HASH_MISMATCH in validation.reasons


def test_validation_detects_sequence_gap_and_previous_hash_mismatch():
    first = build_paper_truth_event(**_event_kwargs())
    second = build_paper_truth_event(
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        sequence=3,
        candidate_id="cand-1",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=102.0,
        previous_event_hash="wrong-hash",
        event_ts_epoch=1772202660.0,
    )

    validation = validate_paper_truth_events([first.to_payload(), second.to_payload()])

    assert validation.journal_valid is False
    assert SEQUENCE_GAP in validation.reasons
    assert PREVIOUS_HASH_MISMATCH in validation.reasons


def test_append_refuses_invalid_existing_journal(tmp_path):
    journal = tmp_path / "paper_truth.jsonl"
    bad = build_paper_truth_event(**_event_kwargs()).to_payload()
    bad["event_hash"] = "bad-hash"
    journal.write_text(json.dumps(bad) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="paper_truth_journal_invalid"):
        append_paper_truth_event(
            journal,
            event_type=PAPER_EVENT_EXIT_RECORDED,
            candidate_id="cand-1",
            strategy_id="breakout_v1",
            symbol="NIFTY",
            side="SELL",
            quantity=50,
            price=99.0,
            event_ts_epoch=1772203000.0,
        )


def test_invalid_event_type_and_mode_are_rejected():
    with pytest.raises(ValueError, match=INVALID_EVENT_TYPE):
        build_paper_truth_event(**(_event_kwargs() | {"event_type": "LIVE_ENTRY"}))

    with pytest.raises(ValueError, match=INVALID_MODE):
        build_paper_truth_event(**(_event_kwargs() | {"mode": "LIVE"}))


def test_read_rejects_invalid_json_line(tmp_path):
    journal = tmp_path / "paper_truth.jsonl"
    journal.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match=INVALID_JSON_LINE):
        read_paper_truth_events(journal)
