import importlib.util
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "run_walk_forward_elite.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_walk_forward_elite", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _session_frame(*, sessions: int = 60, bars_per_session: int = 10) -> pd.DataFrame:
    frames = []
    row_number = 0
    for day in pd.bdate_range("2026-01-01", periods=sessions):
        index = pd.date_range(
            day + pd.Timedelta(hours=9, minutes=15),
            periods=bars_per_session,
            freq="5min",
        )
        frames.append(
            pd.DataFrame(
                {"row": range(row_number, row_number + bars_per_session)},
                index=index,
            )
        )
        row_number += bars_per_session
    return pd.concat(frames)


def _positive_metrics(test_data: pd.DataFrame) -> dict[str, object]:
    return {
        "profit_factor": 1.5,
        "after_cost_expectancy": 1.0,
        "total_trades": len(test_data),
        "final_equity": 100000.0,
        "total_pnl": 0.0,
        "win_rate_pct": 50.0,
        "avg_win": 1.0,
        "avg_loss": -1.0,
        "max_drawdown_pct": -1.0,
        "max_drawdown_abs": -100.0,
        "sharpe_ratio_per_trade": 0.1,
        "sortino_ratio_per_trade": 0.1,
        "outcomes": {},
        "contamination": {},
        "warnings": [],
        "profit_factor_oos": None,
    }


def test_walk_forward_plan_has_three_session_folds_and_untouched_holdout():
    module = _load_module()
    data = _session_frame()
    plan = module.build_walk_forward_plan(data)

    assert plan["block_session_counts"] == [10, 10, 10, 10, 10, 10]
    assert plan["total_sessions"] == 60
    assert plan["holdout_start"] == 500
    assert plan["holdout_end"] == 600
    assert list(plan["holdout_data"]["row"]) == list(range(500, 600))

    expected_rows = [
        (0, 200, 200, 300),
        (100, 300, 300, 400),
        (200, 400, 400, 500),
    ]
    actual_rows = [
        (
            fold["train_start"],
            fold["train_end"],
            fold["test_start"],
            fold["test_end"],
        )
        for fold in plan["folds"]
    ]
    assert actual_rows == expected_rows

    holdout_sessions = set(plan["holdout_sessions"])
    for fold in plan["folds"]:
        train_sessions = set(fold["train_sessions"])
        test_sessions = set(fold["test_sessions"])
        assert train_sessions.isdisjoint(test_sessions)
        assert train_sessions.isdisjoint(holdout_sessions)
        assert test_sessions.isdisjoint(holdout_sessions)
        assert fold["train_data"].index.normalize().nunique() == 20
        assert fold["test_data"].index.normalize().nunique() == 10


def test_walk_forward_rejects_non_datetime_or_unsorted_data():
    module = _load_module()
    try:
        module.build_walk_forward_plan(pd.DataFrame({"row": range(600)}))
    except TypeError as exc:
        assert str(exc) == "certified walk-forward data must use a DatetimeIndex"
    else:
        raise AssertionError("RangeIndex input must not be treated as certified WFA")

    unsorted = _session_frame().sort_index(ascending=False)
    try:
        module.build_walk_forward_plan(unsorted)
    except ValueError as exc:
        assert str(exc) == "walk-forward data must be sorted chronologically"
    else:
        raise AssertionError("unsorted chronological data must be rejected")


def test_explicit_empty_parameter_grid_rejects_instead_of_using_defaults():
    module = _load_module()
    report = module.run_walk_forward(_session_frame(), parameter_grid=[])

    assert report == {
        "status": "REJECTED",
        "promoted": False,
        "blockers": ["EMPTY_PARAMETER_GRID"],
        "fold_reports": [],
    }


def test_promotion_uses_final_holdout_expectancy_not_full_sample_expectancy():
    module = _load_module()
    fold_reports = [
        {"test_metrics": {"after_cost_expectancy": 1.0}},
        {"test_metrics": {"after_cost_expectancy": 1.0}},
        {"test_metrics": {"after_cost_expectancy": -1.0}},
    ]
    promoted, blockers = module._should_promote(
        final_holdout_metrics={
            "profit_factor": 1.5,
            "after_cost_expectancy": -0.1,
            "full_sample_expectancy": 100.0,
        },
        fold_reports=fold_reports,
        stability_penalty=1,
    )

    assert promoted is False
    assert "FINAL_HOLDOUT_EXPECTANCY_NOT_MET" in blockers


def test_run_walk_forward_evaluates_session_test_slices_and_holdout_only():
    module = _load_module()
    data = _session_frame()
    params = (15, 1.5, 3.0, 1.0, 0.0, 0.5)
    evaluated_ranges = []
    evaluated_session_counts = []

    def select_fn(train_data, _grid):
        assert train_data.index.normalize().nunique() == 20
        return params, float(train_data["row"].iloc[-1])

    def evaluate_fn(test_data, selected_params):
        assert selected_params == params
        start = int(test_data["row"].iloc[0])
        end = int(test_data["row"].iloc[-1]) + 1
        evaluated_ranges.append((start, end))
        evaluated_session_counts.append(test_data.index.normalize().nunique())
        return _positive_metrics(test_data)

    report = module.run_walk_forward(
        data,
        parameter_grid=[params],
        select_fn=select_fn,
        evaluate_fn=evaluate_fn,
    )

    assert report["promoted"] is True
    assert evaluated_ranges == [
        (200, 300),
        (300, 400),
        (400, 500),
        (500, 600),
    ]
    assert evaluated_session_counts == [10, 10, 10, 10]


def test_walk_forward_rejects_when_any_fold_has_no_valid_parameters():
    module = _load_module()
    params = (15, 1.5, 3.0, 1.0, 0.0, 0.5)
    selection_calls = 0
    evaluation_calls = 0

    def select_fn(_train_data, _grid):
        nonlocal selection_calls
        selection_calls += 1
        if selection_calls == 2:
            return None, -float("inf")
        return params, 1.0

    def evaluate_fn(test_data, _selected_params):
        nonlocal evaluation_calls
        evaluation_calls += 1
        return _positive_metrics(test_data)

    report = module.run_walk_forward(
        _session_frame(),
        parameter_grid=[params],
        select_fn=select_fn,
        evaluate_fn=evaluate_fn,
    )

    assert report["promoted"] is False
    assert report["blockers"] == ["INCOMPLETE_WALK_FORWARD_FOLDS"]
    assert [fold["status"] for fold in report["fold_reports"]] == [
        "EVALUATED",
        "NO_VALID_PARAMETERS",
        "EVALUATED",
    ]
    assert evaluation_calls == 2


def test_walk_forward_rejects_when_any_test_fold_has_no_trades():
    module = _load_module()
    params = (15, 1.5, 3.0, 1.0, 0.0, 0.5)
    evaluation_calls = 0

    def select_fn(_train_data, _grid):
        return params, 1.0

    def evaluate_fn(test_data, _selected_params):
        nonlocal evaluation_calls
        evaluation_calls += 1
        if evaluation_calls == 1:
            return {"error": "No trades executed"}
        return _positive_metrics(test_data)

    report = module.run_walk_forward(
        _session_frame(),
        parameter_grid=[params],
        select_fn=select_fn,
        evaluate_fn=evaluate_fn,
    )

    assert report["promoted"] is False
    assert report["blockers"] == ["INCOMPLETE_WALK_FORWARD_FOLDS"]
    assert [fold["status"] for fold in report["fold_reports"]] == [
        "TEST_METRICS_INVALID",
        "EVALUATED",
        "EVALUATED",
    ]
    assert evaluation_calls == 3
