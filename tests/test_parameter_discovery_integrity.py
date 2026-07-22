import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _load(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_structural_audit_accepts_passed_candidate_without_reject_reason():
    module = _load("audit_v2", "scripts/audit_phase4_v2_structural.py")
    candidate = {
        "signal_time": "2026-01-01T10:15:00",
        "symbol": "NIFTY",
        "setup_type": "FAILED_BREAKOUT_SHORT",
        "wick_ratio": 0.6,
        "or_high": 105.0,
        "or_low": 95.0,
        "signal_close": 100.0,
        "status": "PASSED",
        "htf_regime": "NEUTRAL/BEARISH",
        "entry_eval_time": "2026-01-01T10:16:00",
        "entry_open": 100.0,
        "stop_loss": 105.0,
        "target": 92.5,
        "planned_target_distance": 7.5,
        "proxy_option_expected_move": 3.75,
        "cost_hurdle_margin": 2.25,
    }
    trade = {
        "v2_signal_version": "1.0",
        "setup_type": "FAILED_BREAKOUT_SHORT",
        "failed_level": 105.0,
        "rejection_quality": 0.6,
        "htf_regime": "NEUTRAL/BEARISH",
        "signal_time": "2026-01-01T10:15:00",
        "entry_time": "2026-01-01T10:16:00",
        "entry_delay_bars": 1,
        "next_open_recalculated": True,
        "planned_target_distance": 7.5,
        "entry_price": 100.0,
        "stop_loss": 105.0,
        "target": 92.5,
        "cost_hurdle_margin": 2.25,
        "pnl_model": "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
    }
    summary = {
        "zero_trade_metrics": {"zero_trade_symbol_days": 1},
        "cap_saturation_ratio": 0.2,
    }

    result = module.audit_v2_structure([trade], [candidate], summary)
    assert result["classification"] == "V2_STRUCTURAL_AUDIT_PASSED"
    assert result["blockers"] == []


def test_parameter_discovery_uses_declared_gated_lane_and_rejects_failed_audits():
    module = _load(
        "parameter_discovery", "scripts/run_mean_reversion_parameter_discovery.py"
    )
    assert not module._passes_pf(
        {"profit_factor": None, "profit_factor_state": "NO_LOSING_TRADES"},
        1.15,
    )
    assert not module._positive(
        {"audits_passed": False, "gated_expectancy": 10.0}
    )
    assert module._positive(
        {"audits_passed": True, "gated_expectancy": 0.1}
    )
    # A positive proxy lane cannot rescue a negative declared gate lane.
    assert not module._positive(
        {
            "audits_passed": True,
            "gated_expectancy": -0.1,
            "proxy_option_net_expectancy": 100.0,
        }
    )


def test_gated_profit_factor_uses_model_specific_ledger_field(tmp_path):
    module = _load(
        "parameter_discovery_pf", "scripts/run_mean_reversion_parameter_discovery.py"
    )
    ledger = tmp_path / "phase_4_trade_ledger.jsonl"
    rows = [
        {
            "underlying_net_pnl_after_index_cost": 8.0,
            "proxy_option_net_pnl": -100.0,
        },
        {
            "underlying_net_pnl_after_index_cost": -4.0,
            "proxy_option_net_pnl": 200.0,
        },
    ]
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    underlying_pf, underlying_state = module._ledger_profit_factor(
        tmp_path, "UNDERLYING_INDEX_PROXY_FIXED_HURDLE"
    )
    proxy_pf, proxy_state = module._ledger_profit_factor(
        tmp_path, "DELTA_PROXY_OPTION"
    )
    assert underlying_state == "FINITE"
    assert underlying_pf == 2.0
    assert proxy_state == "FINITE"
    assert proxy_pf == 2.0


def test_region_stability_requires_an_evaluated_positive_neighbor():
    module = _load(
        "parameter_discovery_region",
        "scripts/run_mean_reversion_parameter_discovery.py",
    )
    grid = {"x": [1, 2, 3]}
    assert not module.check_region_stability((2,), grid, {}, ["x"])

    results = {
        (1,): {
            "train_metrics": {
                "audits_passed": True,
                "gated_expectancy": 1.0,
            }
        }
    }
    assert module.check_region_stability((2,), grid, results, ["x"])


def test_parameter_ids_are_stable_and_order_independent():
    module = _load(
        "parameter_discovery_ids",
        "scripts/run_mean_reversion_parameter_discovery.py",
    )
    first = module._stable_parameter_id({"b": 2, "a": 1})
    second = module._stable_parameter_id({"a": 1, "b": 2})
    expected = "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    assert first == second
    assert first == expected
