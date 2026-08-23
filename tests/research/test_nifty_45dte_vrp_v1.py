from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "research" / "nifty_45dte_vrp_v1"


def _load_module(name: str, filename: str):
    path = MODULE_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit_data = _load_module("nifty_45dte_audit_data", "audit_data.py")
evaluate_short_vol = _load_module("nifty_45dte_evaluate_short_vol", "evaluate_short_vol.py")


def _rows_for_expiry(expiry: pd.Timestamp, *, target_hit: bool) -> list[dict]:
    expiry_date = expiry.date()
    entry_date = expiry_date - pd.Timedelta(days=45)
    rows: list[dict] = []

    def add_snapshot(date, ce_bid, ce_ask, pe_bid, pe_ask, ce_delta=0.16, pe_delta=-0.16):
        ts = pd.Timestamp(date).tz_localize("Asia/Kolkata") + pd.Timedelta(hours=15)
        rows.extend(
            [
                {
                    "timestamp": ts,
                    "symbol": "NIFTY",
                    "expiry": str(expiry_date),
                    "strike": 25000,
                    "type": "CE",
                    "bid": ce_bid,
                    "ask": ce_ask,
                    "delta": ce_delta,
                    "chain_source": "vendor_real_quotes",
                },
                {
                    "timestamp": ts,
                    "symbol": "NIFTY",
                    "expiry": str(expiry_date),
                    "strike": 23000,
                    "type": "PE",
                    "bid": pe_bid,
                    "ask": pe_ask,
                    "delta": pe_delta,
                    "chain_source": "vendor_real_quotes",
                },
            ]
        )

    add_snapshot(entry_date, 100, 101, 100, 101)
    if target_hit:
        add_snapshot(entry_date + pd.Timedelta(days=2), 48, 49, 48, 49, 0.08, -0.08)
        add_snapshot(expiry_date - pd.Timedelta(days=21), 40, 41, 40, 41, 0.06, -0.06)
    else:
        add_snapshot(expiry_date - pd.Timedelta(days=30), 120, 121, 120, 121, 0.25, -0.25)
        add_snapshot(expiry_date - pd.Timedelta(days=21), 130, 131, 130, 131, 0.30, -0.30)
    return rows


def _frame(rows: list[dict]) -> pd.DataFrame:
    return audit_data.normalize_frame(pd.DataFrame(rows), assume_ist=False)


def test_audit_rejects_realish_source(tmp_path: Path):
    expiry = pd.Timestamp("2026-10-27")
    rows = _rows_for_expiry(expiry, target_hit=True)
    rows[0]["chain_source"] = "historical_replay_realish"
    path = tmp_path / "options.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    with pytest.raises(ValueError, match="SYNTHETIC_SOURCE_REJECTED"):
        audit_data.build_audit(
            path,
            assume_ist=False,
            expected_sha256=None,
            min_eligible_expiries=1,
            required_years=[2026],
            min_per_required_year=1,
            target_delta=0.16,
            delta_tolerance=0.03,
            min_dte=42,
            max_dte=48,
            snapshot_ist="15:00",
            snapshot_tolerance_minutes=15,
        )


def test_audit_accepts_minimal_real_quote_fixture(tmp_path: Path):
    expiry = pd.Timestamp("2026-10-27")
    path = tmp_path / "options.csv"
    pd.DataFrame(_rows_for_expiry(expiry, target_hit=True)).to_csv(path, index=False)

    result = audit_data.build_audit(
        path,
        assume_ist=False,
        expected_sha256=None,
        min_eligible_expiries=1,
        required_years=[2026],
        min_per_required_year=1,
        target_delta=0.16,
        delta_tolerance=0.03,
        min_dte=42,
        max_dte=48,
        snapshot_ist="15:00",
        snapshot_tolerance_minutes=15,
    )

    assert result["status"] == "DATA_READY_FOR_PRIMARY_EVAL"
    assert result["eligible_expiries_with_21dte_quote_coverage"] == 1
    assert result["governance"]["synthetic_data_accepted"] is False


def test_primary_eval_hits_fifty_percent_target():
    expiry = pd.Timestamp("2026-10-27")
    df = _frame(_rows_for_expiry(expiry, target_hit=True))

    result = evaluate_short_vol.evaluate_expiry(
        df,
        expiry_date=expiry.date(),
        min_dte=42,
        max_dte=48,
        snapshot_ist="15:00",
        snapshot_tolerance_minutes=15,
        target_abs_delta=0.16,
        delta_tolerance=0.03,
        profit_target_fraction=0.50,
        time_exit_dte=21,
        extra_round_trip_cost_points=0.0,
    )

    assert result is not None
    assert result["initial_credit_points"] == 200.0
    assert result["exit_reason"] == "PROFIT_TARGET"
    assert result["close_debit_points"] == 98.0
    assert result["gross_pnl_points"] == 102.0


def test_primary_eval_uses_21dte_time_exit_when_target_never_hits():
    expiry = pd.Timestamp("2026-10-27")
    df = _frame(_rows_for_expiry(expiry, target_hit=False))

    result = evaluate_short_vol.evaluate_expiry(
        df,
        expiry_date=expiry.date(),
        min_dte=42,
        max_dte=48,
        snapshot_ist="15:00",
        snapshot_tolerance_minutes=15,
        target_abs_delta=0.16,
        delta_tolerance=0.03,
        profit_target_fraction=0.50,
        time_exit_dte=21,
        extra_round_trip_cost_points=0.0,
    )

    assert result is not None
    assert result["exit_reason"] == "TIME_EXIT"
    assert result["exit_dte"] == 21
    assert result["close_debit_points"] == 262.0
    assert result["gross_pnl_points"] == -62.0
