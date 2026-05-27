from __future__ import annotations

import json

from core.paper_expectancy_by_regime import (
    EXPECTANCY_STATUS_BLOCKED,
    EXPECTANCY_STATUS_REDUCED,
    INSUFFICIENT_SAMPLE_REASON,
    INVALID_OUTCOME_REPORT_REASON,
    NO_CLOSED_OUTCOMES_REASON,
    PAPER_EXPECTANCY_SOURCE,
    UNKNOWN_REGIME,
    build_expectancy_by_regime,
)
from core.paper_outcome_reducer import OUTCOME_CLOSED, OUTCOME_OPEN, PAPER_OUTCOME_REDUCER_SOURCE


def _outcome(
    *,
    candidate_id: str,
    strategy_id: str,
    gross_pnl: float,
    regime: str | None,
) -> dict:
    metadata = {}
    if regime is not None:
        metadata["regime"] = regime
    return {
        "candidate_id": candidate_id,
        "strategy_id": strategy_id,
        "symbol": "NIFTY",
        "status": OUTCOME_CLOSED,
        "gross_pnl": gross_pnl,
        "metadata": metadata,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def _report(outcomes: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "source": PAPER_OUTCOME_REDUCER_SOURCE,
        "status": "PAPER_OUTCOMES_REDUCED",
        "journal_valid": True,
        "read_only": True,
        "append": False,
        "outcomes": outcomes,
    }


def test_build_expectancy_groups_closed_outcomes_by_strategy_and_regime():
    report = _report(
        [
            _outcome(candidate_id="c1", strategy_id="breakout", gross_pnl=100.0, regime="TREND"),
            _outcome(candidate_id="c2", strategy_id="breakout", gross_pnl=-40.0, regime="TREND"),
            _outcome(candidate_id="c3", strategy_id="vwap", gross_pnl=20.0, regime="RANGE"),
        ]
    )

    out = build_expectancy_by_regime(report, min_closed_outcomes=1)
    payload = out.to_payload()

    assert payload["source"] == PAPER_EXPECTANCY_SOURCE
    assert payload["status"] == EXPECTANCY_STATUS_REDUCED
    assert payload["reason_code"] == "ok"
    assert payload["closed_outcome_count"] == 3
    assert payload["bucket_count"] == 2

    buckets = {(bucket["strategy_id"], bucket["regime"]): bucket for bucket in payload["buckets"]}
    breakout = buckets[("breakout", "TREND")]
    assert breakout["closed_count"] == 2
    assert breakout["win_count"] == 1
    assert breakout["loss_count"] == 1
    assert breakout["total_gross_pnl"] == 60.0
    assert breakout["average_gross_pnl"] == 30.0
    assert breakout["win_rate"] == 0.5
    assert breakout["expectancy_per_trade"] == 30.0
    assert breakout["sample_ok"] is True

    vwap = buckets[("vwap", "RANGE")]
    assert vwap["closed_count"] == 1
    assert vwap["win_count"] == 1
    assert vwap["loss_count"] == 0
    assert vwap["expectancy_per_trade"] == 20.0


def test_build_expectancy_ignores_non_closed_outcomes_and_uses_unknown_regime():
    report = _report(
        [
            _outcome(candidate_id="c1", strategy_id="breakout", gross_pnl=15.0, regime=None),
            {"candidate_id": "open", "strategy_id": "breakout", "status": OUTCOME_OPEN, "gross_pnl": None},
        ]
    )

    out = build_expectancy_by_regime(report)
    payload = out.to_payload()

    assert payload["closed_outcome_count"] == 1
    assert payload["bucket_count"] == 1
    assert payload["buckets"][0]["regime"] == UNKNOWN_REGIME
    assert payload["buckets"][0]["expectancy_per_trade"] == 15.0


def test_build_expectancy_blocks_invalid_outcome_report():
    out = build_expectancy_by_regime({"journal_valid": False, "read_only": True, "append": False, "outcomes": []})
    payload = out.to_payload()

    assert payload["status"] == EXPECTANCY_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_OUTCOME_REPORT_REASON
    assert payload["buckets"] == []
    assert payload["outcome_report_valid"] is False


def test_build_expectancy_blocks_when_no_closed_outcomes_exist():
    out = build_expectancy_by_regime(_report([{"candidate_id": "open", "status": OUTCOME_OPEN}]))
    payload = out.to_payload()

    assert payload["status"] == EXPECTANCY_STATUS_BLOCKED
    assert payload["reason_code"] == NO_CLOSED_OUTCOMES_REASON
    assert payload["outcome_report_valid"] is True
    assert payload["bucket_count"] == 0


def test_build_expectancy_flags_insufficient_sample_without_hiding_bucket():
    report = _report([_outcome(candidate_id="c1", strategy_id="breakout", gross_pnl=100.0, regime="TREND")])

    out = build_expectancy_by_regime(report, min_closed_outcomes=2)
    payload = out.to_payload()

    assert payload["status"] == EXPECTANCY_STATUS_BLOCKED
    assert payload["reason_code"] == INSUFFICIENT_SAMPLE_REASON
    assert payload["bucket_count"] == 1
    assert payload["buckets"][0]["sample_ok"] is False
    assert payload["buckets"][0]["blockers"] == [INSUFFICIENT_SAMPLE_REASON]


def test_expectancy_payload_is_json_serializable_and_non_action():
    report = _report([_outcome(candidate_id="c1", strategy_id="breakout", gross_pnl=5.0, regime="TREND")])

    out = build_expectancy_by_regime(report)
    payload = out.to_payload()
    encoded = out.to_json()

    assert json.loads(encoded)["source"] == PAPER_EXPECTANCY_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["buckets"][0]["is_order_action"] is False
    assert payload["buckets"][0]["broker_api_called"] is False
