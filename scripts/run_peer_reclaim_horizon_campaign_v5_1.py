#!/usr/bin/env python3
"""V5.1 repair: preserve session_id while refreshing a delayed entry row."""
from __future__ import annotations

import pandas as pd

from scripts import run_peer_reclaim_horizon_campaign_v5 as campaign


def shift_signal_entry(signals: pd.DataFrame, causal: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    shifted = signals.copy()
    shifted["timestamp"] = shifted["timestamp"] + pd.Timedelta(minutes=minutes)
    refresh_columns = [
        "expired_instrument_key",
        "timestamp",
        "session_id",
        "entry_price_next_open",
        "expiry_id",
        "option_type",
        "strike",
        "days_to_expiry",
        "minute_of_day",
    ]
    lookup = causal[refresh_columns].drop_duplicates(["expired_instrument_key", "timestamp"])
    refresh_nonkeys = set(refresh_columns) - {"expired_instrument_key", "timestamp", "session_id"}
    preserve = [column for column in shifted.columns if column not in refresh_nonkeys]
    return shifted[preserve].merge(
        lookup,
        on=["expired_instrument_key", "timestamp", "session_id"],
        how="inner",
        validate="many_to_one",
    )


campaign.shift_signal_entry = shift_signal_entry


if __name__ == "__main__":
    raise SystemExit(campaign.main())
