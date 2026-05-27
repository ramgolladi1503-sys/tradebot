from __future__ import annotations

import json

from core.paper_outcome_reducer import (
    DUPLICATE_ENTRY_REASON,
    EXIT_WITHOUT_ENTRY_REASON,
    INVALID_JOURNAL_REASON,
    OPEN_POSITION_REASON,
    OUTCOME_CLOSED,
    OUTCOME_INVALID,
    OUTCOME_OPEN,
    OUTCOME_REJECTED,
    PAPER_REDUCER_STATUS_BLOCKED,
    PAPER_REDUCER_STATUS_REDUCED,
    REJECTED_CANDIDATE_REASON,
    reduce_paper_outcomes,
    reduce_paper_outcomes_from_journal,
)
from core.paper_truth_journal import (
    EVENT_HASH_MISMATCH,
    PAPER_EVENT_CANDIDATE_ACCEPTED,
    PAPER_EVENT_ENTRY_RECORDED,
    PAPER_EVENT_EXIT_RECORDED,
    PAPER_EVENT_REJECTED,
    append_paper_truth_event,
    build_paper_truth_event,
)

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


def _closed_long_events() -> tuple[dict[str, object], ...]:
    first = build_paper_truth_event(
        event_type=PAPER_EVENT_CANDIDATE_ACCEPTED,
        sequence=1,
        candidate_id="cand-1",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        event_ts_epoch=1772202600.0,
    )
    second = build_paper_truth_event(
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        sequence=2,
        candidate_id="cand-1",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=100.0,
        previous_event_hash=first.event_hash,
        event_ts_epoch=1772202660.0,
    )
    third = build_paper_truth_event(
        event_type=PAPER_EVENT_EXIT_RECORDED,
        sequence=3,
        candidate_id="cand-1",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="SELL",
        quantity=50,
        price=104.5,
        previous_event_hash=second.event_hash,
        event_ts_epoch=1772203000.0,
    )
    return (first.to_payload(), second.to_payload(), third.to_payload())


def test_reduce_closed_long_candidate_derives_realized_gross_pnl():
    report = reduce_paper_outcomes(_closed_long_events())
    payload = report.to_payload()

    assert payload["status"] == PAPER_REDUCER_STATUS_REDUCED
    assert payload["journal_valid"] is True
    assert payload["candidate_count"] == 1
    assert payload["closed_count"] == 1
    assert payload["realized_gross_pnl"] == 225.0
    assert payload["outcomes"][0]["status"] == OUTCOME_CLOSED
    assert payload["outcomes"][0]["gross_pnl"] == 225.0
    assert payload["outcomes"][0]["entry_price"] == 100.0
    assert payload["outcomes"][0]["exit_price"] == 104.5
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload[_ACTION_KEY] is False
    assert payload[_BROKER_KEY] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_reduce_open_candidate_surfaces_open_blocker():
    first = build_paper_truth_event(
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        sequence=1,
        candidate_id="cand-open",
        strategy_id="vwap_v1",
        symbol="BANKNIFTY",
        side="BUY",
        quantity=15,
        price=250.0,
        event_ts_epoch=1772202600.0,
    )

    report = reduce_paper_outcomes([first.to_payload()])
    outcome = report.outcomes[0]

    assert outcome.status == OUTCOME_OPEN
    assert outcome.gross_pnl is None
    assert OPEN_POSITION_REASON in outcome.blockers
    assert report.open_count == 1


def test_reduce_rejected_candidate_derives_rejected_status():
    first = build_paper_truth_event(
        event_type=PAPER_EVENT_REJECTED,
        sequence=1,
        candidate_id="cand-rejected",
        strategy_id="mean_reversion_v1",
        symbol="NIFTY",
        side="SELL",
        payload={"reason": "quality_gate_blocked"},
        event_ts_epoch=1772202600.0,
    )

    report = reduce_paper_outcomes([first.to_payload()])
    outcome = report.outcomes[0]

    assert outcome.status == OUTCOME_REJECTED
    assert REJECTED_CANDIDATE_REASON in outcome.blockers
    assert report.rejected_count == 1


def test_reduce_exit_without_entry_is_invalid():
    first = build_paper_truth_event(
        event_type=PAPER_EVENT_EXIT_RECORDED,
        sequence=1,
        candidate_id="cand-invalid",
        strategy_id="zero_hero_v1",
        symbol="NIFTY",
        side="SELL",
        quantity=50,
        price=95.0,
        event_ts_epoch=1772202600.0,
    )

    report = reduce_paper_outcomes([first.to_payload()])
    outcome = report.outcomes[0]

    assert outcome.status == OUTCOME_INVALID
    assert EXIT_WITHOUT_ENTRY_REASON in outcome.blockers
    assert report.invalid_count == 1


def test_reduce_duplicate_entry_is_invalid():
    first = build_paper_truth_event(
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        sequence=1,
        candidate_id="cand-dup",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=100.0,
        event_ts_epoch=1772202600.0,
    )
    second = build_paper_truth_event(
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        sequence=2,
        candidate_id="cand-dup",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=101.0,
        previous_event_hash=first.event_hash,
        event_ts_epoch=1772202660.0,
    )

    report = reduce_paper_outcomes([first.to_payload(), second.to_payload()])
    outcome = report.outcomes[0]

    assert outcome.status == OUTCOME_INVALID
    assert DUPLICATE_ENTRY_REASON in outcome.blockers
    assert report.invalid_count == 1


def test_invalid_journal_blocks_before_reduction():
    event = build_paper_truth_event(
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        sequence=1,
        candidate_id="cand-tampered",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=100.0,
        event_ts_epoch=1772202600.0,
    ).to_payload()
    event["price"] = 120.0

    report = reduce_paper_outcomes([event])
    payload = report.to_payload()

    assert payload["status"] == PAPER_REDUCER_STATUS_BLOCKED
    assert payload["journal_valid"] is False
    assert payload["reason_code"] == INVALID_JOURNAL_REASON
    assert EVENT_HASH_MISMATCH in payload["reasons"]
    assert payload["outcomes"] == []


def test_reduce_from_journal_file_does_not_mutate_journal(tmp_path):
    journal = tmp_path / "paper_truth.jsonl"
    append_paper_truth_event(
        journal,
        event_type=PAPER_EVENT_ENTRY_RECORDED,
        candidate_id="cand-file",
        strategy_id="breakout_v1",
        symbol="NIFTY",
        side="BUY",
        quantity=10,
        price=100.0,
        event_ts_epoch=1772202600.0,
    )
    before = journal.read_text(encoding="utf-8")

    report = reduce_paper_outcomes_from_journal(journal)
    after = journal.read_text(encoding="utf-8")

    assert before == after
    assert report.status == PAPER_REDUCER_STATUS_REDUCED
    assert report.outcomes[0].status == OUTCOME_OPEN


def test_reducer_payload_is_json_serializable():
    report = reduce_paper_outcomes(_closed_long_events())

    loaded = json.loads(report.to_json())

    assert loaded["status"] == PAPER_REDUCER_STATUS_REDUCED
    assert loaded["outcomes"][0]["candidate_id"] == "cand-1"
