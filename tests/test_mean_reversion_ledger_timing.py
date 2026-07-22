from __future__ import annotations

import pandas as pd

from scripts.generate_mean_reversion_trade_ledger import _resolve_bar_exit


def _active_trade() -> dict[str, object]:
    return {
        "direction": "LONG",
        "stop_loss": 95.0,
        "target": 105.0,
        "entry_ts": pd.Timestamp("2026-01-05T09:15:00"),
    }


def test_entry_bar_touching_stop_and_target_is_conservatively_stopped_at_bar_end():
    outcome = _resolve_bar_exit(
        active_trade=_active_trade(),
        row=pd.Series({"high": 106.0, "low": 94.0, "close": 100.0}),
        bar_start=pd.Timestamp("2026-01-05T09:15:00"),
        bar_interval=pd.Timedelta(minutes=5),
        time_stop_minutes=30,
    )

    assert outcome == (
        95.0,
        "SAME_CANDLE_AMBIGUOUS_ASSUMED_STOP",
        pd.Timestamp("2026-01-05T09:20:00"),
    )


def test_time_stop_uses_observable_bar_end_not_start_timestamp():
    outcome = _resolve_bar_exit(
        active_trade=_active_trade(),
        row=pd.Series({"high": 104.0, "low": 96.0, "close": 101.0}),
        bar_start=pd.Timestamp("2026-01-05T09:40:00"),
        bar_interval=pd.Timedelta(minutes=5),
        time_stop_minutes=30,
    )

    assert outcome == (
        101.0,
        "TIME_STOP",
        pd.Timestamp("2026-01-05T09:45:00"),
    )
