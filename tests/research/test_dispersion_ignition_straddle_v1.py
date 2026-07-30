from __future__ import annotations

import pandas as pd

from research.dispersion_ignition_straddle_v1.common import (
    VARIANTS, calculate_metrics, split_sessions, training_thresholds, variant_mask,
)
from research.dispersion_ignition_straddle_v1.options import replay_signal


def _option_frame(start: str, prices: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(prices), freq="1min", tz="Asia/Kolkata")
    volume_values = volumes if volumes is not None else [100] * len(prices)
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": prices,
            "high": [value + 1 for value in prices],
            "low": [value - 1 for value in prices],
            "close": prices,
            "volume": volume_values,
            "open_interest": [1000] * len(prices),
        },
        index=index,
    )


class FakeStore:
    def __init__(self, ce: pd.DataFrame, pe: pd.DataFrame):
        self.ce = ce
        self.pe = pe

    def select(self, session: str, signal_timestamp: pd.Timestamp, spot: float):
        prior = signal_timestamp - pd.Timedelta(minutes=1)
        if prior not in self.ce.index or prior not in self.pe.index:
            return None
        return {"expiry": "2025-01-02", "strike": 24000.0, "ce": self.ce, "pe": self.pe, "prior": prior}


def test_replay_uses_next_minute_open_and_fixed_close():
    ce = _option_frame("2025-01-01 09:17", [100, 100, 100, 102, 105, 108, 110, 112])
    pe = _option_frame("2025-01-01 09:17", [90, 90, 90, 88, 86, 84, 82, 80])
    signal_time = pd.Timestamp("2025-01-01 09:20", tz="Asia/Kolkata")
    signal = pd.Series({
        "session": "2025-01-01", "signal_timestamp": signal_time, "index_close": 24010.0,
        "variant": VARIANTS[0], "fold": 1, "future_range_5": 0.002,
        "future_range_10": 0.003, "future_range_15": 0.004, "future_range_20": 0.005,
    })
    records = replay_signal(FakeStore(ce, pe), signal)
    five = next(record for record in records if record["horizon"] == 5)
    assert five["entry_timestamp"] == signal_time
    assert five["ce_entry"] == 102 and five["pe_entry"] == 88
    assert five["exit_timestamp"] == pd.Timestamp("2025-01-01 09:24", tz="Asia/Kolkata")
    assert five["gross_return"] == (112 + 80 - 102 - 88) / (102 + 88)


def test_stale_zero_volume_signal_is_rejected():
    ce = _option_frame("2025-01-01 09:17", [100, 100, 100, 102, 105, 108], [0, 0, 0, 100, 100, 100])
    pe = _option_frame("2025-01-01 09:17", [90, 90, 90, 88, 86, 84], [0, 0, 0, 100, 100, 100])
    signal = pd.Series({
        "session": "2025-01-01",
        "signal_timestamp": pd.Timestamp("2025-01-01 09:20", tz="Asia/Kolkata"),
        "index_close": 24000.0, "variant": VARIANTS[0], "fold": 1,
    })
    assert replay_signal(FakeStore(ce, pe), signal) == []


def test_variant_membership_ignores_future_outcome_columns():
    frame = pd.DataFrame({
        "dispersion_mad": [0.01, 0.03, 0.04, 0.02],
        "absolute_participation": [0.6, 0.8, 0.9, 0.7],
        "index_expression_ratio": [0.2, 0.1, 0.3, 0.8],
        "dispersion_mad_change": [0.0, 0.02, 0.01, -0.01],
        "absolute_participation_change": [0.0, 0.2, 0.1, -0.1],
        "top5_abs_share": [0.4, 0.2, 0.3, 0.5],
        "future_range_20": [999, -999, 50, -50],
    })
    thresholds = training_thresholds(frame)
    original = variant_mask(frame, thresholds, VARIANTS[0])
    changed = frame.copy()
    changed["future_range_20"] *= -1000
    assert original.equals(variant_mask(changed, thresholds, VARIANTS[0]))


def test_metrics_apply_stress_return_and_concentration():
    ledger = pd.DataFrame({
        "session": ["a", "b", "c", "d", "e", "f"],
        "fold": [1, 2, 3, 4, 5, 5],
        "stress_return": [0.02, 0.01, -0.005, 0.015, -0.003, 0.012],
    })
    metrics = calculate_metrics(ledger)
    assert metrics.trades == 6 and metrics.sessions == 6
    assert metrics.mean_return is not None and metrics.mean_return > 0
    assert metrics.profit_factor is not None and metrics.profit_factor > 1
    assert metrics.total_folds == 5


def test_chronological_split_keeps_holdout_last():
    sessions = pd.date_range("2024-01-01", periods=100, freq="B").date.astype(str).tolist()
    split = split_sessions(sessions)
    assert len(split["research"]) == 70 and len(split["validation"]) == 15 and len(split["holdout"]) == 15
    assert max(split["research"]) < min(split["validation"]) < min(split["holdout"])


def test_appending_future_rows_does_not_change_prior_membership():
    prefix = pd.DataFrame({
        "minute_of_day": [600] * 4, "dispersion_mad": [0.01, 0.03, 0.04, 0.02],
        "absolute_participation": [0.6, 0.8, 0.9, 0.7],
        "index_expression_ratio": [0.2, 0.1, 0.3, 0.8],
        "dispersion_mad_change": [0.0, 0.02, 0.01, -0.01],
        "absolute_participation_change": [0.0, 0.2, 0.1, -0.1],
        "top5_abs_share": [0.4, 0.2, 0.3, 0.5],
    })
    thresholds = training_thresholds(prefix)
    prior = variant_mask(prefix, thresholds, VARIANTS[1])
    future = pd.DataFrame({
        "minute_of_day": [900, 900], "dispersion_mad": [100.0, 200.0],
        "absolute_participation": [1.0, 1.0], "index_expression_ratio": [0.0, 0.0],
        "dispersion_mad_change": [100.0, 100.0], "absolute_participation_change": [1.0, 1.0],
        "top5_abs_share": [0.0, 0.0],
    })
    combined = pd.concat([prefix, future], ignore_index=True)
    after = variant_mask(combined.iloc[: len(prefix)], thresholds, VARIANTS[1])
    assert prior.reset_index(drop=True).equals(after.reset_index(drop=True))
