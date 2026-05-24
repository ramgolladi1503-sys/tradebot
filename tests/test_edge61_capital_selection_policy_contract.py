from __future__ import annotations

from core.capital_selection_policy import CapitalSelectionPolicy, explain_capital_selection_policy


def _policy(**overrides):
    values = {
        "total_capital": 1000.0,
        "max_selected": 2,
        "max_allocation_per_candidate": 400.0,
        "default_allocation_per_candidate": 250.0,
        "max_per_symbol": 1,
        "max_per_family": 1,
    }
    values.update(overrides)
    return CapitalSelectionPolicy(**values)


def _row(
    candidate_id: str,
    *,
    symbol: str = "NIFTY",
    family: str = "breakout",
    requested_allocation: float = 250.0,
    execution_status: str = "executable",
    quote_source: str = "tick_store",
    source_list: str | None = None,
):
    row = {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "strategy_family": family,
        "requested_allocation": requested_allocation,
        "execution_status": execution_status,
        "quote_source": quote_source,
        "is_executable": execution_status == "executable",
    }
    if source_list:
        row["source_list"] = source_list
    return row


def test_candidate_allocation_never_exceeds_configured_maximum():
    report = explain_capital_selection_policy(
        {
            "top_executable_opportunities": [
                _row("C-1", requested_allocation=900.0),
            ]
        },
        policy=_policy(max_allocation_per_candidate=300.0),
    )

    assert report.selected_count == 1
    assert report.capped_count == 1
    assert report.records[0].assigned_allocation == 300.0
    assert report.records[0].reason == "max_candidate_allocation_cap"
    assert report.records[0].assigned_allocation <= report.policy["max_allocation_per_candidate"]


def test_non_executable_advisory_and_fallback_candidates_get_zero_allocation():
    report = explain_capital_selection_policy(
        {
            "top_executable_opportunities": [
                _row("EXEC", symbol="NIFTY", family="breakout"),
                _row("FALLBACK", symbol="BANKNIFTY", family="trend", quote_source="recovered_fallback"),
            ],
            "top_advisory_opportunities": [
                _row("ADVISORY", symbol="SENSEX", family="mean_reversion", execution_status="advisory_only"),
            ],
        },
        policy=_policy(max_selected=3, max_per_symbol=3, max_per_family=3),
    )

    by_id = {record.candidate_id: record for record in report.records}
    assert by_id["EXEC"].assigned_allocation > 0.0
    assert by_id["FALLBACK"].assigned_allocation == 0.0
    assert by_id["FALLBACK"].selected is False
    assert by_id["FALLBACK"].reason == "fallback_or_stale_data_advisory_only"
    assert by_id["ADVISORY"].assigned_allocation == 0.0
    assert by_id["ADVISORY"].selected is False
    assert by_id["ADVISORY"].reason == "advisory_or_display_only_candidate"


def test_selection_limit_is_enforced_with_explainable_reason():
    report = explain_capital_selection_policy(
        {
            "top_executable_opportunities": [
                _row("C-1", symbol="NIFTY", family="breakout"),
                _row("C-2", symbol="BANKNIFTY", family="trend"),
                _row("C-3", symbol="SENSEX", family="mean_reversion"),
            ]
        },
        policy=_policy(max_selected=2, max_per_symbol=2, max_per_family=2),
    )

    by_id = {record.candidate_id: record for record in report.records}
    assert report.selected_count == 2
    assert by_id["C-3"].selected is False
    assert by_id["C-3"].assigned_allocation == 0.0
    assert by_id["C-3"].reason == "selection_limit_reached"


def test_symbol_cap_is_enforced_and_explainable():
    report = explain_capital_selection_policy(
        {
            "top_executable_opportunities": [
                _row("C-1", symbol="NIFTY", family="breakout"),
                _row("C-2", symbol="NIFTY", family="trend"),
            ]
        },
        policy=_policy(max_selected=2, max_per_symbol=1, max_per_family=2),
    )

    first, second = report.records
    assert first.selected is True
    assert second.selected is False
    assert second.assigned_allocation == 0.0
    assert second.reason == "symbol_cap_reached"


def test_family_cap_is_enforced_and_explainable():
    report = explain_capital_selection_policy(
        {
            "top_executable_opportunities": [
                _row("C-1", symbol="NIFTY", family="breakout"),
                _row("C-2", symbol="BANKNIFTY", family="breakout"),
            ]
        },
        policy=_policy(max_selected=2, max_per_symbol=2, max_per_family=1),
    )

    first, second = report.records
    assert first.selected is True
    assert second.selected is False
    assert second.assigned_allocation == 0.0
    assert second.reason == "family_cap_reached"


def test_capital_budget_is_enforced_without_over_assignment():
    report = explain_capital_selection_policy(
        {
            "top_executable_opportunities": [
                _row("C-1", symbol="NIFTY", family="breakout", requested_allocation=300.0),
                _row("C-2", symbol="BANKNIFTY", family="trend", requested_allocation=300.0),
            ]
        },
        policy=_policy(
            total_capital=500.0,
            max_selected=2,
            max_allocation_per_candidate=400.0,
            min_allocation_per_candidate=250.0,
            max_per_symbol=2,
            max_per_family=2,
        ),
    )

    by_id = {record.candidate_id: record for record in report.records}
    assert by_id["C-1"].assigned_allocation == 300.0
    assert by_id["C-2"].selected is False
    assert by_id["C-2"].assigned_allocation == 0.0
    assert by_id["C-2"].reason == "capital_budget_exhausted"
    assert report.total_assigned_allocation <= report.policy["total_capital"]


def test_unknown_non_executable_candidate_fails_closed_to_zero_allocation():
    report = explain_capital_selection_policy(
        [
            {
                "candidate_id": "UNKNOWN",
                "symbol": "NIFTY",
                "strategy_family": "breakout",
                "requested_allocation": 250.0,
            }
        ],
        policy=_policy(),
    )

    record = report.records[0]
    assert record.selected is False
    assert record.executable_eligible is False
    assert record.assigned_allocation == 0.0
    assert record.reason == "not_execution_eligible"


def test_no_eligible_skipped_candidate_has_empty_or_no_selection_reason():
    report = explain_capital_selection_policy(
        {
            "top_executable_opportunities": [
                _row("C-1", symbol="NIFTY", family="breakout"),
                _row("C-2", symbol="BANKNIFTY", family="trend"),
                _row("C-3", symbol="SENSEX", family="mean_reversion"),
            ]
        },
        policy=_policy(max_selected=1, max_per_symbol=3, max_per_family=3),
    )

    skipped = [record for record in report.records if record.executable_eligible and not record.selected]
    assert skipped
    assert all(record.reason not in {"", "NO_SELECTION"} for record in skipped)
    assert "eligible_candidate_missing_selection_reason" not in report.warnings


def test_report_has_explicit_non_action_metadata_and_deterministic_payload():
    payload = {
        "top_executable_opportunities": [
            _row("C-1", symbol="NIFTY", family="breakout"),
            _row("C-2", symbol="BANKNIFTY", family="trend"),
        ]
    }

    first = explain_capital_selection_policy(payload, policy=_policy()).to_dict()
    second = explain_capital_selection_policy(payload, policy=_policy()).to_dict()
    first.pop("generated_epoch")
    second.pop("generated_epoch")

    assert first == second
    assert first["is_order_action"] is False
    assert first["broker_api_called"] is False
    assert first["live_order_action"] is False
    assert first["broker_order_action"] is False
    assert first["metadata"]["is_order_action"] is False
    assert first["metadata"]["broker_api_called"] is False
