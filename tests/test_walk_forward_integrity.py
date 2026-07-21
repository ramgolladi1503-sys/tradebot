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


def test_walk_forward_plan_has_three_forward_folds_and_untouched_holdout():
    module = _load_module()
    data = pd.DataFrame({"value": range(600)})
    plan = module.build_walk_forward_plan(data)

    assert plan["fold_size"] == 100
    assert plan["holdout_start"] == 500
    assert list(plan["holdout_data"]["value"]) == list(range(500, 600))

    expected = [
        (0, 200, 200, 300),
        (100, 300, 300, 400),
        (200, 400, 400, 500),
    ]
    actual = [
        (
            fold["train_start"],
            fold["train_end"],
            fold["test_start"],
            fold["test_end"],
        )
        for fold in plan["folds"]
    ]
    assert actual == expected
    for fold in plan["folds"]:
        assert fold["train_end"] == fold["test_start"]
        assert fold["test_end"] <= plan["holdout_start"]


def test_explicit_empty_parameter_grid_rejects_instead_of_using_defaults():
    module = _load_module()
    report = module.run_walk_forward(
        pd.DataFrame({"row": range(600)}), parameter_grid=[]
    )

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

    assert not promoted
    assert "FINAL_HOLDOUT_EXPECTANCY_NOT_MET" in blockers


def test_run_walk_forward_evaluates_each_test_slice_and_final_holdout_only():
    module = _load_module()
    data = pd.DataFrame({"row": range(600)})
    params = (15, 1.5, 3.0, 1.0, 0.0, 0.5)
    evaluated_ranges = []

    def select_fn(train_data, _grid):
        return params, float(train_data["row"].iloc[-1])

    def evaluate_fn(test_data, selected_params):
        assert selected_params == params
        start = int(test_data["row"].iloc[0])
        end = int(test_data["row"].iloc[-1]) + 1
        evaluated_ranges.append((start, end))
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
