from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from research.cross_sectional_diffusion_direction_v1.campaign import (
    CampaignConfig,
    add_forward_returns,
    apply_signal,
    build_feature_frame,
    fit_thresholds,
)
from research.cross_sectional_diffusion_direction_v1.session_wfa import (
    SessionCampaignConfig,
    assess_session_terminal_verdict,
    session_windows,
)


def _minute_grid(day: str, n: int = 60):
    return pd.date_range(f"{day} 09:15", periods=n, freq="min", tz="Asia/Kolkata")


def _membership(symbols=("A", "B")) -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": list(symbols),
        "effective_from": [pd.Timestamp("2020-01-01").date()] * len(symbols),
        "effective_to": [pd.NaT] * len(symbols),
        "weight": [1.0 / len(symbols)] * len(symbols),
    })


def test_feature_builder_uses_historical_membership_and_expected_gap():
    ts = _minute_grid("2024-01-02", 30)
    idx = pd.DataFrame({"timestamp": ts, "open": 100.0, "close": 100.0})
    rows = []
    for symbol, drift in [("A", 0.0010), ("B", 0.0010), ("C", -0.0010)]:
        price = 100 * np.exp(np.arange(len(ts)) * drift)
        rows.extend({"timestamp": t, "symbol": symbol, "open": p, "close": p} for t, p in zip(ts, price))
    con = pd.DataFrame(rows)
    feat = build_feature_frame(idx, con, _membership(), lookback_minutes=5, min_coverage=1.0)
    assert not feat.empty
    assert (feat["eligible_members"] == 2).all()
    assert (feat["observed_members"] == 2).all()
    assert (feat["breadth"] > 0.99).all()
    assert (feat["gap"] > 0).all()


def test_signal_thresholds_are_train_fitted_and_symmetric():
    train = pd.DataFrame({
        "breadth": [-1.0, -0.8, -0.2, 0.2, 0.8, 1.0],
        "gap": [-0.03, -0.02, -0.01, 0.01, 0.02, 0.03],
        "impulse": [-0.03, -0.02, -0.01, 0.01, 0.02, 0.03],
    })
    t = fit_thresholds(train, 0.80, 0.80)
    test = pd.DataFrame({
        "breadth": [1.0, -1.0, 0.0],
        "gap": [0.05, -0.05, 0.0],
        "impulse": [0.05, -0.05, 0.0],
    })
    assert apply_signal(test, t).tolist() == [1, -1, 0]


def test_forward_return_enters_exact_next_open_not_decision_close():
    ts = _minute_grid("2024-01-02", 25)
    base = pd.DataFrame({
        "timestamp": ts[:10],
        "session": [t.date() for t in ts[:10]],
        "index_r": 0.0,
        "breadth": 1.0,
        "impulse": 0.01,
        "gap": 0.01,
        "coverage": 1.0,
        "eligible_members": 50,
        "observed_members": 50,
        "weight_authority": "HISTORICAL_WEIGHTED",
    })
    exe = pd.DataFrame({
        "timestamp": ts,
        "open": np.arange(len(ts), dtype=float) + 100.0,
        "close": np.arange(len(ts), dtype=float) + 100.5,
    })
    out = add_forward_returns(base, exe, (15,))
    first = out.iloc[0]
    assert first["entry_open"] == 101.0
    expected = np.log(exe.iloc[15]["close"] / 101.0) * 10000
    assert abs(first["long_gross_bps_15"] - expected) < 1e-9


def test_exact_minute_lookback_does_not_substitute_fifth_observed_row():
    ts = _minute_grid("2024-01-02", 20)
    missing = ts[3]
    kept = ts[ts != missing]
    idx = pd.DataFrame({"timestamp": kept, "open": 100.0, "close": np.arange(len(kept), dtype=float) + 100.0})
    rows = []
    for symbol in ("A", "B"):
        price = np.arange(len(kept), dtype=float) + 100.0
        rows.extend({"timestamp": t, "symbol": symbol, "open": p, "close": p} for t, p in zip(kept, price))
    con = pd.DataFrame(rows)
    feat = build_feature_frame(idx, con, _membership(), lookback_minutes=5, min_coverage=1.0)
    target = missing + pd.Timedelta(minutes=5)
    assert target not in set(feat["timestamp"])
    assert ts[9] in set(feat["timestamp"])


def test_expanding_session_windows_produce_four_pre_holdout_folds():
    sessions = pd.date_range("2024-07-26", periods=396, freq="B").date
    frame = pd.DataFrame({
        "session": sessions,
        "timestamp": pd.to_datetime([f"{d} 09:20" for d in sessions]).tz_localize("Asia/Kolkata"),
    })
    windows = session_windows(frame, 126, 63, 63)
    assert len(windows) == 4
    assert [len(train) for train, _ in windows] == [126, 189, 252, 315]
    assert all(len(test) == 63 for _, test in windows)
    assert all(set(train).isdisjoint(test) for train, test in windows)
    assert set(windows[0][1]).isdisjoint(windows[1][1])


def test_terminal_verdict_fails_closed_without_authority():
    cfg = CampaignConfig(min_oos_events=1, min_oos_sessions=1, bootstrap_repetitions=10)
    from research.cross_sectional_diffusion_direction_v1.campaign import assess_terminal_verdict
    result = {
        "status": "COMPLETE",
        "oos_event_count": 10,
        "oos_session_count": 10,
        "session_bootstrap": {"estimate": 2.0, "ci_lower": 0.5, "ci_upper": 3.0},
        "lagged_control_bootstrap": {"estimate": 0.1, "ci_lower": -1.0, "ci_upper": 1.0},
        "index_only_baseline_bootstrap": {"estimate": 0.5, "ci_lower": -0.5, "ci_upper": 1.5},
        "positive_fold_fraction": 1.0,
        "max_single_fold_profit_share": 0.4,
    }
    verdict, blockers = assess_terminal_verdict(
        result, cfg=cfg, membership_authoritative=False, execution_authoritative=False
    )
    assert verdict == "NO_CERTIFIED_TRADABLE_EDGE"
    assert "HISTORICAL_MEMBERSHIP_NOT_AUTHORITATIVE" in blockers
    assert "EXECUTION_SERIES_NOT_AUTHORITATIVE" in blockers


def test_session_verdict_requires_multiple_folds_and_authority():
    cfg = SessionCampaignConfig(min_oos_folds=4, min_oos_events=1, min_oos_sessions=1, bootstrap_repetitions=10)
    result = {
        "status": "COMPLETE",
        "folds": [{"fold_id": 1}],
        "oos_event_count": 10,
        "oos_session_count": 10,
        "session_bootstrap": {"estimate": 2.0, "ci_lower": 0.5, "ci_upper": 3.0},
        "lagged_control_bootstrap": {"estimate": 0.1, "ci_lower": -1.0, "ci_upper": 1.0},
        "index_only_baseline_bootstrap": {"estimate": 0.5, "ci_lower": -0.5, "ci_upper": 1.5},
        "positive_fold_fraction": 1.0,
        "max_single_fold_profit_share": 0.4,
    }
    verdict, blockers = assess_session_terminal_verdict(
        result, cfg=cfg, membership_authoritative=True, execution_authoritative=True
    )
    assert verdict == "NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE"
    assert "INSUFFICIENT_OOS_FOLDS" in blockers


def test_all_pre_holdout_gates_emit_survivor_not_certified_edge():
    cfg = SessionCampaignConfig(min_oos_folds=4, min_oos_events=1, min_oos_sessions=1, bootstrap_repetitions=10)
    result = {
        "status": "COMPLETE",
        "folds": [{"fold_id": i} for i in range(1, 5)],
        "oos_event_count": 20,
        "oos_session_count": 20,
        "session_bootstrap": {"estimate": 2.0, "ci_lower": 0.5, "ci_upper": 3.0},
        "lagged_control_bootstrap": {"estimate": 0.2, "ci_lower": -0.5, "ci_upper": 0.8},
        "index_only_baseline_bootstrap": {"estimate": 0.7, "ci_lower": -0.1, "ci_upper": 1.3},
        "positive_fold_fraction": 0.75,
        "max_single_fold_profit_share": 0.4,
    }
    verdict, blockers = assess_session_terminal_verdict(
        result, cfg=cfg, membership_authoritative=True, execution_authoritative=True
    )
    assert blockers == []
    assert verdict == "PRE_HOLDOUT_DIRECTIONAL_SURVIVOR"
