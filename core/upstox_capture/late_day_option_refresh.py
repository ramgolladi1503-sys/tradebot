from __future__ import annotations
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

def refresh_late_day_option_subscriptions(
    streamer,
    subscriptions: dict[str, str],
    df_inst: pd.DataFrame,
    current_spot_price: float
) -> int:
    """
    Dynamically refreshes and subscribes late-day ATM and ATM +/- 100 strikes
    around current spot price at ~15:23-15:24 IST.
    Prevents large intraday moves (e.g. 300+ pts) from causing desired ATM strikes
    to be missing at 15:26 signal decision time.
    Never unsubscribes active feeds.
    Returns the count of newly subscribed option contracts.
    """
    if df_inst.empty or not current_spot_price or streamer is None:
        return 0

    today_date = pd.to_datetime(datetime.now().date())
    atm = round(current_spot_price / 50.0) * 50.0
    # Capture ATM +/- 5 strikes (covers ATM, ATM +/- 100 for V2-B, and safety buffer)
    desired_strikes = [atm + (i * 50.0) for i in range(-5, 6)]

    df_sym = df_inst[(df_inst["name"] == "NIFTY") & (df_inst["instrument_type"].isin(["CE", "PE"]))].copy()
    if df_sym.empty:
        return 0

    df_sym["expiry_date"] = pd.to_datetime(df_sym["expiry"], unit="ms")
    df_future = df_sym[df_sym["expiry_date"] >= today_date]
    nearest_expiry = df_future["expiry_date"].min() if not df_future.empty else df_sym["expiry_date"].max()
    df_exp = df_sym[df_sym["expiry_date"] == nearest_expiry]
    df_strikes = df_exp[df_exp["strike_price"].isin(desired_strikes)]

    new_keys = []
    for _, row in df_strikes.iterrows():
        key = row["instrument_key"]
        if key not in subscriptions:
            subscriptions[key] = row["trading_symbol"]
            new_keys.append(key)

    if new_keys:
        try:
            streamer.subscribe(new_keys, mode="full")
            logger.info(f"[Late-Day Refresh] Dynamically subscribed {len(new_keys)} new NIFTY option strikes around spot {current_spot_price:.1f} (ATM {atm:.0f}).")
        except Exception as e:
            logger.error(f"[Late-Day Refresh] Failed to subscribe new keys: {e}")

    return len(new_keys)
