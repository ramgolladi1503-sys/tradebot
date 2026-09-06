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


def _minute_grid(day: str, n: int = 60):
    return pd.date_range(f"{day} 09:15", periods=n, freq="min", tz="Asia/Kolkata")


def test_feature_builder_uses_historical_membership_and_expected_gap():
    ts = _minute_grid("2024-01-02", 30)
    idx = pd.DataFrame({"timestamp": ts, "open": 100.0, "close": 100.0})
    rows = []
    for symbol, drift in [("A", 0.0010), ("B", 0.0010), ("C", -0.0010)]:
        price = 100 * np.exp(np.arange(len(ts)) * drift)
        rows.extend({"timestamp": t, "symbol": symbol, "open": p, "close": p} for t, p in zip(ts, price))
    con = pd.DataFrame(rows)
    membership = pd.DataFrame({
        "symbol": ["A", "B"],
        "effective_from": [pd.Timestamp("2020-01-01").date()] * 2,
        "effective_to": [pd.NaT, pd.NaT],
        "weight": [0.5, 0.5],
    })
    feat = build_feature_frame(idx, con, membership, lookback_minutes=5, min_coverage=1.0)
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


def test_forward_return_enters_next_open_not_decision_close():
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
        "next_open": 0.0,
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


def test_terminal_verdict_fails_closed_without_authority():
    from research.cross_sectional_diffusion_direction_v1.campaign import assess_terminal_verdict
    cfg = CampaignConfig(min_oos_events=1, min_oos_sessions=1, bootstrap_repetitions=10)
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
