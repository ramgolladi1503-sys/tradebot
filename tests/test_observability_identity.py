from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.observability import (
    ObservabilityContext,
    ObservabilityIdentityError,
    ObservabilityIds,
    build_candidate_id,
    build_cycle_id,
    build_run_id,
    build_span_id,
    build_trace_id,
    normalize_identity_component,
)


def test_run_and_cycle_ids_are_stable_for_fixed_inputs() -> None:
    started_at = datetime(2026, 5, 23, 3, 45, 1, tzinfo=timezone.utc)

    run_id = build_run_id(started_at=started_at, label="TradeBot Live Morning")
    cycle_id = build_cycle_id(run_id=run_id, sequence=7, started_at=started_at)

    assert run_id == "run_tradebot_live_morning_20260523t034501z"
    assert cycle_id == "cycle_run_tradebot_live_morning_20260523t034501z_000007_20260523t034501z"


def test_trace_and_span_ids_are_deterministic_from_stable_parts() -> None:
    first_trace = build_trace_id(
        scope="candidate",
        stable_parts={"cycle_id": "cycle_1", "candidate_id": "nifty_22500_ce"},
    )
    second_trace = build_trace_id(
        scope="candidate",
        stable_parts={"candidate_id": "nifty_22500_ce", "cycle_id": "cycle_1"},
    )

    assert first_trace == second_trace
    assert build_span_id(stage="candidate.score", trace_id=first_trace) == build_span_id(
        stage="candidate.score",
        trace_id=second_trace,
    )
    assert build_span_id(stage="candidate.rank", trace_id=first_trace) != build_span_id(
        stage="candidate.score",
        trace_id=first_trace,
    )


def test_candidate_id_changes_when_identity_inputs_change() -> None:
    base_candidate = build_candidate_id(
        symbol="NIFTY",
        option_type="CE",
        strike=22500,
        side="BUY",
        strategy_id="opening_drive",
        cycle_id="cycle_001",
    )
    changed_candidate = build_candidate_id(
        symbol="NIFTY",
        option_type="CE",
        strike=22500,
        side="SELL",
        strategy_id="opening_drive",
        cycle_id="cycle_001",
    )

    assert base_candidate.startswith("candidate_nifty_ce_22500_buy_opening_drive_")
    assert changed_candidate.startswith("candidate_nifty_ce_22500_sell_opening_drive_")
    assert base_candidate != changed_candidate


def test_identity_component_normalization_rejects_empty_values() -> None:
    assert normalize_identity_component("NIFTY 22,500 CE") == "nifty_22_500_ce"

    with pytest.raises(ObservabilityIdentityError, match="identity_component_empty"):
        normalize_identity_component("   ")


def test_observability_ids_emit_only_populated_fields() -> None:
    ids = ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1")

    assert ids.as_dict() == {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
    }


def test_context_for_stage_is_copy_on_write_and_non_action_by_default() -> None:
    parent = ObservabilityContext(
        ids=ObservabilityIds(run_id="run_1", cycle_id="cycle_1", trace_id="trace_1"),
        stage="runtime.cycle",
        execution_mode="PAPER",
        attributes={"source": "unit_test"},
    )

    child = parent.for_stage("candidate.score", decision="observed")

    assert parent.as_dict() == {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
        "stage": "runtime.cycle",
        "execution_mode": "PAPER",
        "is_order_action": False,
        "broker_api_called": False,
        "source": "unit_test",
    }
    assert child.as_dict() == {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
        "span_id": build_span_id(stage="candidate.score", trace_id="trace_1"),
        "stage": "candidate.score",
        "execution_mode": "PAPER",
        "is_order_action": False,
        "broker_api_called": False,
        "source": "unit_test",
        "decision": "observed",
    }


def test_context_with_candidate_preserves_cycle_trace_and_stage() -> None:
    context = ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_1",
            cycle_id="cycle_1",
            trace_id="trace_1",
            span_id="span_1",
        ),
        stage="candidate.generated",
        execution_mode="PAPER",
    )

    candidate_context = context.with_candidate("candidate_nifty_ce", reason="generated_from_strategy")

    assert candidate_context.as_dict() == {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
        "span_id": "span_1",
        "candidate_id": "candidate_nifty_ce",
        "stage": "candidate.generated",
        "execution_mode": "PAPER",
        "is_order_action": False,
        "broker_api_called": False,
        "reason": "generated_from_strategy",
    }
    assert context.as_dict() == {
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "trace_id": "trace_1",
        "span_id": "span_1",
        "stage": "candidate.generated",
        "execution_mode": "PAPER",
        "is_order_action": False,
        "broker_api_called": False,
    }
