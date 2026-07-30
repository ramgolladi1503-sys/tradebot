from __future__ import annotations

import pandas as pd

from research.common_factor_option_underreaction_v1.campaign import (
    VARIANTS,
    replay_signal,
    training_thresholds,
    variant_mask,
)


def _frame(start: str, values: list[float]) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(values), freq="1min", tz="Asia/Kolkata")
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": values,
            "high": [value + 1 for value in values],
            "low": [value - 1 for value in values],
            "close": values,
            "volume": [100] * len(values),
            "open_interest": [1000] * len(values),
        },
        index=index,
    )


class FakeStore:
    def __init__(self, ce: pd.DataFrame, pe: pd.DataFrame):
        self.ce, self.pe = ce, pe

    def select(self, session: str, signal_timestamp: pd.Timestamp, spot: float):
        return {
            "expiry": "2025-01-02",
            "strike": 24000.0,
            "ce": self.ce,
            "pe": self.pe,
            "prior": signal_timestamp - pd.Timedelta(minutes=1),
        }


def _state_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "threshold_bucket": ["20|1"] * 8,
            "coherence_score": [4, 5, 6, 7, 8, 9, 10, 11],
            "absolute_participation": [.60, .65, .70, .75, .80, .85, .90, .95],
            "index_lag": [.0001, .0002, .0003, .0004, .0005, .0006, .0007, .0008],
            "selected_return_5m": [-.02, -.015, -.01, -.005, 0, .005, .01, .015],
            "selected_premium_burden": [.004, .005, .006, .007, .008, .009, .010, .011],
            "top5_abs_share": [.50, .45, .40, .35, .30, .25, .20, .15],
            "mirror_return_5m": [-.03, -.02, -.01, 0, .01, .02, .03, .04],
            "common_shock_strength": [.001, .002, .003, .004, .005, .006, .007, .008],
            "selected_signal_volume": [100] * 8,
            "mirror_signal_volume": [100] * 8,
            "future_index_return_5": [1000] * 8,
        }
    )


def test_membership_ignores_future_index_returns():
    frame = _state_frame()
    thresholds = training_thresholds(frame)
    before = variant_mask(frame, thresholds, VARIANTS[0])
    frame["future_index_return_5"] = [-999999] * len(frame)
    after = variant_mask(frame, thresholds, VARIANTS[0])
    assert before.equals(after)


def test_replay_bullish_selects_ce_and_exact_next_minute_open():
    ce = _frame("2025-01-01 09:20", [100, 103, 106, 109, 112, 115])
    pe = _frame("2025-01-01 09:20", [90, 88, 86, 84, 82, 80])
    signal = pd.Series(
        {
            "session": "2025-01-01",
            "signal_timestamp": pd.Timestamp("2025-01-01 09:20", tz="Asia/Kolkata"),
            "index_close": 24000.0,
            "pair_expiry": "2025-01-02",
            "pair_strike": 24000.0,
            "direction": 1,
            "selected_option_type": "CE",
            "mirror_option_type": "PE",
            "variant": VARIANTS[0],
            "fold": 1,
            "days_to_expiry": 1,
            "selected_premium_burden": 100 / 24000,
            "future_index_return_5": .002,
            "future_index_return_10": .003,
            "future_index_return_15": .004,
            "future_index_return_20": .005,
        }
    )
    records = replay_signal(FakeStore(ce, pe), signal)
    five = next(record for record in records if record["horizon"] == 5)
    assert five["selected_option_type"] == "CE"
    assert five["entry_timestamp"] == signal["signal_timestamp"]
    assert five["selected_entry"] == 100
    assert five["selected_exit"] == 112
    assert five["stress_return"] == 112 / 100 - 1 - .01
    assert five["directional_index_return"] == .002


def test_replay_bearish_selects_pe_and_mirror_ce():
    ce = _frame("2025-01-01 09:20", [100, 98, 96, 94, 92, 90])
    pe = _frame("2025-01-01 09:20", [90, 93, 96, 99, 102, 105])
    signal = pd.Series(
        {
            "session": "2025-01-01",
            "signal_timestamp": pd.Timestamp("2025-01-01 09:20", tz="Asia/Kolkata"),
            "index_close": 24000.0,
            "pair_expiry": "2025-01-02",
            "pair_strike": 24000.0,
            "direction": -1,
            "selected_option_type": "PE",
            "mirror_option_type": "CE",
            "variant": VARIANTS[0],
            "fold": 1,
            "days_to_expiry": 1,
            "selected_premium_burden": 90 / 24000,
            "future_index_return_5": -.002,
            "future_index_return_10": -.003,
            "future_index_return_15": -.004,
            "future_index_return_20": -.005,
        }
    )
    five = next(record for record in replay_signal(FakeStore(ce, pe), signal) if record["horizon"] == 5)
    assert five["selected_option_type"] == "PE"
    assert five["mirror_option_type"] == "CE"
    assert five["directional_index_return"] == .002


def test_extra_delay_moves_entry_without_changing_membership():
    ce = _frame("2025-01-01 09:20", [100, 103, 106, 109, 112, 115, 118])
    pe = _frame("2025-01-01 09:20", [90, 88, 86, 84, 82, 80, 78])
    signal = pd.Series(
        {
            "session": "2025-01-01", "signal_timestamp": pd.Timestamp("2025-01-01 09:20", tz="Asia/Kolkata"),
            "index_close": 24000.0, "pair_expiry": "2025-01-02", "pair_strike": 24000.0,
            "direction": 1, "selected_option_type": "CE", "mirror_option_type": "PE",
            "variant": VARIANTS[0], "fold": 1, "days_to_expiry": 1,
            "selected_premium_burden": 100 / 24000,
            "future_index_return_5": .002, "future_index_return_10": .003,
            "future_index_return_15": .004, "future_index_return_20": .005,
        }
    )
    normal = next(record for record in replay_signal(FakeStore(ce, pe), signal, 0) if record["horizon"] == 5)
    delayed = next(record for record in replay_signal(FakeStore(ce, pe), signal, 1) if record["horizon"] == 5)
    assert delayed["entry_timestamp"] == normal["entry_timestamp"] + pd.Timedelta(minutes=1)
    assert delayed["extra_entry_delay"] == 1
