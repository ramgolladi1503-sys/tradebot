import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).parents[1] / "scripts" / "validate_mean_reversion_vertical_slice.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_vertical", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_metrics_use_declared_underlying_lane_and_real_drawdown():
    module = _load_module()
    trades = [
        {
            "pnl_model": "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
            "underlying_gross_pnl": 10.0,
            "underlying_execution_cost": 2.0,
            "underlying_net_pnl_after_index_cost": 8.0,
            "proxy_option_gross_pnl": 5.0,
            "proxy_option_execution_cost": 1.0,
            "proxy_option_net_pnl": 4.0,
            "rr_realized": 1.0,
        },
        {
            "pnl_model": "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
            "underlying_gross_pnl": -5.0,
            "underlying_execution_cost": 2.0,
            "underlying_net_pnl_after_index_cost": -7.0,
            "proxy_option_gross_pnl": -2.5,
            "proxy_option_execution_cost": 1.0,
            "proxy_option_net_pnl": -3.5,
            "rr_realized": -1.0,
        },
        {
            "pnl_model": "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
            "underlying_gross_pnl": -3.0,
            "underlying_execution_cost": 2.0,
            "underlying_net_pnl_after_index_cost": -5.0,
            "proxy_option_gross_pnl": -1.5,
            "proxy_option_execution_cost": 1.0,
            "proxy_option_net_pnl": -2.5,
            "rr_realized": -0.5,
        },
    ]

    metrics = module.calculate_trade_metrics(trades)

    assert metrics["gross_pnl"] == 2.0
    assert metrics["costs"] == 6.0
    assert metrics["net_pnl"] == -4.0
    assert metrics["expectancy"] == -4.0 / 3.0
    assert metrics["profit_factor"] == 8.0 / 12.0
    assert metrics["max_drawdown"] == -12.0
    assert metrics["realized_rr"] == (-0.5 / 3.0)


def test_no_losses_do_not_emit_fake_profit_factor_999():
    module = _load_module()
    metrics = module.calculate_trade_metrics(
        [
            {
                "pnl_model": "DELTA_PROXY_OPTION",
                "proxy_option_gross_pnl": 3.0,
                "proxy_option_execution_cost": 1.0,
                "proxy_option_net_pnl": 2.0,
                "rr_realized": 1.0,
            },
            {
                "pnl_model": "DELTA_PROXY_OPTION",
                "proxy_option_gross_pnl": 4.0,
                "proxy_option_execution_cost": 1.0,
                "proxy_option_net_pnl": 3.0,
                "rr_realized": 1.5,
            },
        ]
    )

    assert metrics["profit_factor"] is None
    assert metrics["profit_factor_state"] == "NO_LOSING_TRADES"


def test_main_uses_catalog_rows_and_actual_average_rr(tmp_path, monkeypatch):
    module = _load_module()
    base_dir = (
        tmp_path
        / "runtime"
        / "strategy_validation"
        / "MEAN_REVERSION_EXTENSION"
    )
    config_dir = tmp_path / "configs"
    base_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (base_dir / "historical_data_catalog.json").write_text(
        json.dumps(
            {
                "date_range_found": [f"202601{day:02d}" for day in range(1, 31)],
                "trading_days_count": 30,
                "rows_per_day": 375,
                "symbols_found": ["NIFTY", "BANKNIFTY"],
            }
        )
    )
    (base_dir / "phase_4_trade_ledger_audit.json").write_text(
        json.dumps({"classification": "TRADE_LEDGER_AUDIT_PASSED"})
    )
    (base_dir / "phase_4_v2_structural_audit.json").write_text(
        json.dumps({"classification": "V2_STRUCTURAL_AUDIT_PASSED"})
    )
    (config_dir / "candidate_strategy_validation_thresholds.json").write_text(
        json.dumps(
            {
                "min_trades": 1,
                "min_expectancy": -100,
                "minimum_wfa_windows": 6,
            }
        )
    )
    trade = {
        "pnl_model": "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
        "underlying_gross_pnl": 10.0,
        "underlying_execution_cost": 2.0,
        "underlying_net_pnl_after_index_cost": 8.0,
        "rr_realized": 2.25,
    }
    (base_dir / "phase_4_trade_ledger.jsonl").write_text(
        json.dumps(trade) + "\n"
    )

    monkeypatch.chdir(tmp_path)
    module.main()

    report = json.loads((base_dir / "phase_4_report.json").read_text())
    assert report["metrics"]["rows_processed"] == 30 * 375 * 2
    assert report["metrics"]["average_rr"] == 2.25
    assert report["metrics"]["max_drawdown"] == 0.0
