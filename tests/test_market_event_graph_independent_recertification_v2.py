from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_market_event_graph_independent_recertification_v2.py"
)
SPEC = importlib.util.spec_from_file_location("meg_independent_recert_v2", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def thresholds() -> dict[str, float]:
    return {
        "breadth_down_1_p20": 0.10,
        "breadth_down_1_p80": 0.20,
        "index_breadth_divergence_p20": -0.0002,
    }


def make_graph_session(session_date: str = "2026-07-23") -> pd.DataFrame:
    timestamps = pd.date_range(
        f"{session_date} 09:15", periods=24, freq="1min", tz="Asia/Kolkata"
    )
    close = np.arange(100.0, 124.0, dtype=float)
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "session_date": session_date,
            "close": close,
            "breadth_down_1": np.full(24, 0.15),
            "index_breadth_divergence": np.zeros(24),
            "future_return_15": np.full(24, 999.0),
        }
    )
    frame.loc[0, "breadth_down_1"] = 0.25
    frame.loc[1, "index_breadth_divergence"] = -0.001
    frame.loc[2, "breadth_down_1"] = 0.05
    return frame


def make_ledger(
    *, reported_gross: float, entry_close: float = 100.0, exit_close: float = 110.0
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "signal_timestamp": ["2026-07-23T03:47:00Z"],
            "entry_timestamp": ["2026-07-23T03:48:00Z"],
            "exit_timestamp": ["2026-07-23T04:03:00Z"],
            "entry_close": [entry_close],
            "exit_close": [exit_close],
            "gross_return": [reported_gross],
            "round_trip_cost": [0.0002],
            "net_return": [reported_gross - 0.0002],
        }
    )


def test_legacy_ledger_mismatch_is_invalidated() -> None:
    result = MODULE.audit_ledger_frame(
        make_ledger(reported_gross=0.01), "validation"
    )
    assert result["verdict"] == "LEGACY_MEG_EXECUTION_ECONOMICS_INVALID"
    assert result["execution_economics_mismatch_rows"] == 1
    assert result["execution_economics_match_rows"] == 0


def test_legacy_ledger_direct_return_reconciles() -> None:
    actual = 110.0 / 100.0 - 1.0
    result = MODULE.audit_ledger_frame(
        make_ledger(reported_gross=actual), "validation"
    )
    assert (
        result["verdict"]
        == "LEGACY_MEG_EXECUTION_ECONOMICS_MATCH_RECORDED_PRICES"
    )
    assert result["execution_economics_mismatch_rows"] == 0
    assert result["execution_economics_match_rows"] == 1


def test_graph_match_is_precursor_only() -> None:
    frame = make_graph_session()
    assert MODULE.graph_matches(frame, 2, thresholds()) is True
    mutated = frame.copy()
    mutated.loc[:, "future_return_15"] = -999999.0
    mutated.loc[3:, "close"] = 1.0
    assert MODULE.graph_matches(mutated, 2, thresholds()) is True


def test_fixed_trade_uses_delayed_entry_and_full_15_bars_from_entry() -> None:
    frame = make_graph_session()
    trades = MODULE.fixed_graph_trades(
        frame,
        ["2026-07-23"],
        thresholds(),
        holding_bars=15,
        cost_bps=2.0,
    )
    assert np.asarray(trades, dtype=object).shape[0] == 1
    trade = trades[0]
    expected_entry = pd.Timestamp(frame.iloc[3]["timestamp"]).isoformat()
    expected_exit = pd.Timestamp(frame.iloc[18]["timestamp"]).isoformat()
    expected_gross = float(frame.iloc[18]["close"] / frame.iloc[3]["close"] - 1.0)
    assert trade["entry_timestamp"] == expected_entry
    assert trade["exit_timestamp"] == expected_exit
    assert trade["holding_bars_from_entry"] == 15
    assert trade["gross_return"] == pytest.approx(expected_gross)
    assert trade["net_bps"] == pytest.approx(expected_gross * 10000.0 - 2.0)


def test_future_return_15_mutation_cannot_change_execution_economics() -> None:
    frame = make_graph_session()
    baseline = MODULE.fixed_graph_trades(
        frame, ["2026-07-23"], thresholds(), holding_bars=15, cost_bps=2.0
    )[0]
    mutated = frame.copy()
    mutated.loc[:, "future_return_15"] = np.linspace(-1000.0, 1000.0, 24)
    changed = MODULE.fixed_graph_trades(
        mutated, ["2026-07-23"], thresholds(), holding_bars=15, cost_bps=2.0
    )[0]
    assert changed["gross_return"] == pytest.approx(baseline["gross_return"])
    assert changed["net_bps"] == pytest.approx(baseline["net_bps"])
    assert changed["legacy_future_return_15"] != baseline["legacy_future_return_15"]


def test_independent_data_rejects_consumed_holdout_dates() -> None:
    frame = make_graph_session("2026-07-22")
    with pytest.raises(ValueError, match="not_strictly_post_holdout"):
        MODULE.validate_independent_frame(frame)


def test_independent_data_accepts_strictly_later_sessions_without_refitting() -> None:
    first = make_graph_session("2026-07-23")
    second = make_graph_session("2026-07-24")
    frame = pd.concat([first, second], ignore_index=True)
    sessions, policy = MODULE.validate_independent_frame(frame)
    assert sessions == ["2026-07-23", "2026-07-24"]
    assert policy["strictly_after_original_holdout"] is True
    assert policy["threshold_refit_allowed"] is False
    assert policy["graph_search_allowed"] is False


def test_robustness_rejects_winner_concentration() -> None:
    trades = []
    for index in range(25):
        gross = 100.0 if index == 0 else 1.0
        trades.append(
            {
                "gross_bps": gross,
                "net_bps": gross - MODULE.ROUND_TRIP_COST_BPS,
            }
        )
    result = MODULE.robustness_audit(trades)
    assert result["passed"] is False
    assert result["gates"]["top5_positive_concentration_le_60pct"] is False


def test_summary_bootstrap_and_sign_test_are_behavioral() -> None:
    result = MODULE.summarize_returns([5.0] * 25)
    assert result["n"] == 25
    assert result["mean_bps"] == pytest.approx(5.0)
    assert result["hit_rate"] == pytest.approx(1.0)
    assert result["mean_ci90"] == pytest.approx([5.0, 5.0])
    assert result["one_sided_sign_p"] < 0.000001
