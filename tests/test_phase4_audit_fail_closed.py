import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _load(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_trade_ledger_audit_fails_on_empty_and_has_no_fake_pf():
    module = _load(
        "audit_trade_ledger", "scripts/audit_mean_reversion_trade_ledger.py"
    )
    empty = module.audit_trades([])
    assert empty["classification"] == "TRADE_LEDGER_AUDIT_FAILED"
    assert "TRADE_LEDGER_MISSING_OR_EMPTY" in empty["failed_blockers"]

    no_losses = module.audit_trades(
        [
            {
                "entry_time": "2026-01-01T09:15:00",
                "exit_time": "2026-01-01T09:20:00",
                "entry_price": 100.0,
                "exit_price": 110.0,
                "direction": "LONG",
                "gross_pnl": 10.0,
                "costs": 1.0,
                "net_pnl": 9.0,
                "stop_loss": 95.0,
                "rr_realized": 2.0,
            }
        ]
    )
    assert no_losses["profit_factor"] is None
    assert no_losses["profit_factor_state"] == "NO_LOSING_TRADES"


def test_truth_audit_uses_declared_index_proxy_cost_and_never_name_errors():
    module = _load("audit_truth", "scripts/audit_phase4_truth.py")
    result = module.audit_truth(
        [
            {
                "entry_time": "2026-01-01T09:15:00",
                "pnl_model": "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
                "underlying_execution_cost": 3.0,
            }
        ]
    )
    assert result["classification"] == "PHASE_4_5_TRUTH_AUDIT_FAILED"
    assert (
        "OPTION_REALISM_FAILED_INSUFFICIENT_INDEX_PROXY_SLIPPAGE"
        in result["blockers"]
    )


def test_integrity_audit_fails_on_empty_ledger():
    module = _load("audit_integrity", "scripts/audit_phase4_7_integrity.py")
    result = module.audit_integrity([])
    assert result["classification"] == "PHASE_4_7_INTEGRITY_AUDIT_FAILED"
    assert "TRADE_LEDGER_MISSING_OR_EMPTY" in result["blockers"]


def test_selection_audit_reads_status_and_signal_time_and_blocks_missing_scores():
    module = _load(
        "audit_selection", "scripts/audit_phase4_8_selection_quality.py"
    )
    result = module.audit_selection_quality(
        [
            {
                "status": "PASSED",
                "symbol": "NIFTY",
                "signal_time": "2026-01-01T10:15:00",
            },
            {
                "status": "REJECTED",
                "symbol": "NIFTY",
                "signal_time": "2026-01-01T10:20:00",
            },
        ],
        {"active_symbol_days": 1, "max_trades_per_symbol_day": 4},
    )
    assert result["metrics"]["selected_trades"] == 1
    assert result["metrics"]["candidate_symbol_days"] == 1
    assert "SELECTED_SCORE_EVIDENCE_MISSING" in result["blockers"]


def test_selection_capacity_prefers_same_run_ledger_summary():
    module = _load(
        "audit_selection_capacity", "scripts/audit_phase4_8_selection_quality.py"
    )
    resolved = module._capacity_metadata(
        {"active_symbol_days": 999, "max_trades_per_symbol_day": 99},
        {
            "cap_saturation": {
                "active_symbol_days": 12,
                "max_trades_per_symbol_day": 4,
            }
        },
    )
    assert resolved["active_symbol_days"] == 12
    assert resolved["max_trades_per_symbol_day"] == 4


def test_accounting_audit_requires_explicit_pnl_model_and_fields():
    module = _load("audit_accounting", "scripts/audit_phase4_10_accounting.py")
    empty = module.audit_accounting([])
    assert empty["classification"] == "PHASE_4_10_ACCOUNTING_FAILED"

    valid = module.audit_accounting(
        [
            {
                "pnl_model": "UNDERLYING_INDEX_PROXY_FIXED_HURDLE",
                "underlying_gross_pnl": 10.0,
                "underlying_net_pnl_after_index_cost": 2.0,
                "proxy_option_gross_pnl": 5.0,
                "proxy_option_net_pnl": 3.5,
            }
        ]
    )
    assert valid["classification"] == "PHASE_4_10_ACCOUNTING_PASSED"
    assert valid["metrics"]["gated_expectancy"] == 2.0
