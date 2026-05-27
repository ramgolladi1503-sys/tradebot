from __future__ import annotations

import json

from core.paper_outcome_reducer import OUTCOME_CLOSED, OUTCOME_OPEN, PAPER_OUTCOME_REDUCER_SOURCE
from core.paper_slippage_cost_truth import (
    INVALID_COST_MODEL_REASON,
    INVALID_OUTCOME_REPORT_REASON,
    MISSING_GROSS_PNL_REASON,
    MISSING_PRICE_OR_QUANTITY_REASON,
    NO_CLOSED_OUTCOMES_REASON,
    PAPER_SLIPPAGE_COST_SOURCE,
    SLIPPAGE_COST_STATUS_BLOCKED,
    SLIPPAGE_COST_STATUS_REDUCED,
    UNKNOWN_REGIME,
    build_slippage_cost_truth,
)


def _closed_outcome(
    *,
    candidate_id: str,
    strategy_id: str = "breakout",
    gross_pnl: float = 100.0,
    regime: str | None = "TREND",
    quantity: float | None = 10.0,
    entry_price: float | None = 100.0,
    exit_price: float | None = 112.0,
) -> dict:
    metadata = {}
    if regime is not None:
        metadata["regime"] = regime
    return {
        "candidate_id": candidate_id,
        "strategy_id": strategy_id,
        "symbol": "NIFTY",
        "status": OUTCOME_CLOSED,
        "entry_side": "BUY",
        "exit_side": "SELL",
        "quantity": quantity,
        "entry_price": entry_price,
        "exit_price": exit_price,
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


def test_build_slippage_cost_truth_converts_gross_to_net_candidate_and_bucket():
    report = _report(
        [
            _closed_outcome(candidate_id="c1", gross_pnl=120.0, regime="TREND", quantity=10, entry_price=100, exit_price=112),
            _closed_outcome(candidate_id="c2", gross_pnl=-30.0, regime="TREND", quantity=5, entry_price=200, exit_price=194),
        ]
    )

    out = build_slippage_cost_truth(
        report,
        entry_slippage_per_unit=1.0,
        exit_slippage_per_unit=2.0,
        fee_per_order=5.0,
        fee_rate=0.01,
        fixed_cost_per_trade=3.0,
        tax_rate=0.0,
    )
    payload = out.to_payload()

    assert payload["source"] == PAPER_SLIPPAGE_COST_SOURCE
    assert payload["status"] == SLIPPAGE_COST_STATUS_REDUCED
    assert payload["reason_code"] == "ok"
    assert payload["candidate_count"] == 2
    assert payload["valid_candidate_count"] == 2
    assert payload["blocked_candidate_count"] == 0
    assert payload["bucket_count"] == 1

    first = payload["candidates"][0]
    assert first["turnover"] == 2120.0
    assert first["entry_slippage_cost"] == 10.0
    assert first["exit_slippage_cost"] == 20.0
    assert first["fee_cost"] == 31.2
    assert first["fixed_cost"] == 3.0
    assert first["total_cost"] == 64.2
    assert first["net_pnl"] == 55.8
    assert first["cost_to_gross_ratio"] == 0.535

    bucket = payload["buckets"][0]
    assert bucket["strategy_id"] == "breakout"
    assert bucket["regime"] == "TREND"
    assert bucket["closed_count"] == 2
    assert bucket["total_gross_pnl"] == 90.0
    assert bucket["total_slippage_cost"] == 45.0
    assert bucket["total_fee_cost"] == 60.9
    assert bucket["total_fixed_cost"] == 6.0
    assert bucket["total_cost"] == 111.9
    assert bucket["total_net_pnl"] == -21.9
    assert bucket["net_win_count"] == 1
    assert bucket["net_loss_count"] == 1
    assert bucket["net_expectancy_per_trade"] == -10.95


def test_build_slippage_cost_truth_groups_by_strategy_and_unknown_regime():
    report = _report(
        [
            _closed_outcome(candidate_id="c1", strategy_id="breakout", gross_pnl=10.0, regime=None),
            _closed_outcome(candidate_id="c2", strategy_id="vwap", gross_pnl=20.0, regime="RANGE"),
            {"candidate_id": "open", "strategy_id": "breakout", "status": OUTCOME_OPEN, "gross_pnl": None},
        ]
    )

    payload = build_slippage_cost_truth(report).to_payload()
    buckets = {(bucket["strategy_id"], bucket["regime"]): bucket for bucket in payload["buckets"]}

    assert payload["closed_outcome_count"] == 2
    assert ("breakout", UNKNOWN_REGIME) in buckets
    assert ("vwap", "RANGE") in buckets
    assert payload["candidate_count"] == 2


def test_build_slippage_cost_truth_blocks_invalid_outcome_report():
    payload = build_slippage_cost_truth({"journal_valid": False, "read_only": True, "append": False, "outcomes": []}).to_payload()

    assert payload["status"] == SLIPPAGE_COST_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_OUTCOME_REPORT_REASON
    assert payload["outcome_report_valid"] is False
    assert payload["buckets"] == []


def test_build_slippage_cost_truth_blocks_when_no_closed_outcomes_exist():
    payload = build_slippage_cost_truth(_report([{"candidate_id": "open", "status": OUTCOME_OPEN}])).to_payload()

    assert payload["status"] == SLIPPAGE_COST_STATUS_BLOCKED
    assert payload["reason_code"] == NO_CLOSED_OUTCOMES_REASON
    assert payload["outcome_report_valid"] is True
    assert payload["candidate_count"] == 0


def test_build_slippage_cost_truth_blocks_invalid_cost_model():
    payload = build_slippage_cost_truth(_report([_closed_outcome(candidate_id="c1")]), fee_rate=-0.01).to_payload()

    assert payload["status"] == SLIPPAGE_COST_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_COST_MODEL_REASON
    assert f"{INVALID_COST_MODEL_REASON}:fee_rate" in payload["reasons"]
    assert payload["candidates"] == []


def test_build_slippage_cost_truth_surfaces_candidate_blockers_without_hiding_candidate():
    report = _report(
        [
            _closed_outcome(candidate_id="c1", quantity=None, gross_pnl=10.0),
            _closed_outcome(candidate_id="c2", gross_pnl=None),
        ]
    )

    payload = build_slippage_cost_truth(report).to_payload()
    reasons = set(payload["reasons"])

    assert payload["status"] == SLIPPAGE_COST_STATUS_BLOCKED
    assert payload["candidate_count"] == 2
    assert payload["valid_candidate_count"] == 0
    assert payload["blocked_candidate_count"] == 2
    assert MISSING_PRICE_OR_QUANTITY_REASON in reasons
    assert MISSING_GROSS_PNL_REASON in reasons
    assert payload["buckets"] == []
    assert payload["candidates"][0]["blockers"] == [MISSING_PRICE_OR_QUANTITY_REASON]
    assert payload["candidates"][1]["blockers"] == [MISSING_GROSS_PNL_REASON]


def test_slippage_cost_payload_is_json_serializable_and_non_action():
    report = _report([_closed_outcome(candidate_id="c1")])

    out = build_slippage_cost_truth(report, fee_per_order=1.0)
    payload = out.to_payload()
    encoded = out.to_json()

    assert json.loads(encoded)["source"] == PAPER_SLIPPAGE_COST_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
    assert payload["cost_model"]["is_order_action"] is False
    assert payload["candidates"][0]["is_order_action"] is False
    assert payload["buckets"][0]["broker_api_called"] is False
