from __future__ import annotations
import logging
import threading
from contextlib import nullcontext
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

def refresh_late_day_option_subscriptions(
    streamer,
    subscriptions: dict[str, str],
    df_inst: pd.DataFrame,
    current_spot_price: float | dict[str, float] | None = None,
    current_spot_prices: dict[str, float] | None = None,
    subscriptions_lock: threading.Lock | None = None,
    lock: threading.Lock | None = None,
) -> int:
    """
    Dynamically refreshes and subscribes ATM +/- 10 option strikes
    around current spot price for NIFTY, BANKNIFTY, and SENSEX.
    Prevents large intraday trend moves from causing in-play or ATM strikes
    (such as SENSEX 74100 CE on high-momentum expiry days) to be missing.
    Never unsubscribes active feeds.
    Returns the total count of newly subscribed option contracts.
    """
    if df_inst.empty or streamer is None:
        return 0

    # Handle backward compatibility: single float or dict
    prices: dict[str, float] = {}
    if isinstance(current_spot_prices, dict):
        prices.update(current_spot_prices)
    if isinstance(current_spot_price, dict):
        prices.update(current_spot_price)
    elif isinstance(current_spot_price, (int, float)) and current_spot_price > 0:
        prices["NIFTY"] = float(current_spot_price)

    if not prices:
        return 0

    configs = {
        "NIFTY": {"name": "NIFTY", "interval": 50.0, "range": 10},
        "BANKNIFTY": {"name": "BANKNIFTY", "interval": 100.0, "range": 10},
        "SENSEX": {"name": "SENSEX", "interval": 100.0, "range": 10},
    }

    today_date = pd.to_datetime(datetime.now().date())
    new_keys = []

    for sym, cfg in configs.items():
        spot = prices.get(sym, 0.0)
        if not spot or spot <= 0:
            continue

        interval = cfg["interval"]
        atm = round(spot / interval) * interval
        # Capture ATM +/- range strikes (covers ATM +/- 10 strikes around current spot)
        desired_strikes = [atm + (i * interval) for i in range(-cfg["range"], cfg["range"] + 1)]

        df_sym = df_inst[(df_inst["name"] == cfg["name"]) & (df_inst["instrument_type"].isin(["CE", "PE"]))].copy()
        if df_sym.empty:
            continue

        df_sym["expiry_date"] = pd.to_datetime(df_sym["expiry"], unit="ms")
        df_future = df_sym[df_sym["expiry_date"] >= today_date]
        nearest_expiry = df_future["expiry_date"].min() if not df_future.empty else df_sym["expiry_date"].max()
        df_exp = df_sym[df_sym["expiry_date"] == nearest_expiry]
        df_strikes = df_exp[df_exp["strike_price"].isin(desired_strikes)]

        effective_lock = subscriptions_lock if subscriptions_lock is not None else lock
        sym_new_keys = []
        with effective_lock if effective_lock is not None else nullcontext():
            for _, row in df_strikes.iterrows():
                key = row["instrument_key"]
                if key not in subscriptions:
                    subscriptions[key] = row["trading_symbol"]
                    sym_new_keys.append(key)

        if sym_new_keys:
            new_keys.extend(sym_new_keys)
            logger.info(
                f"[Dynamic Refresh] Discovered {len(sym_new_keys)} new {sym} option strikes around spot {spot:.1f} (ATM {atm:.0f})."
            )

    if new_keys:
        try:
            streamer.subscribe(new_keys, mode="full")
            logger.info(f"[Dynamic Refresh] Successfully subscribed {len(new_keys)} new option strikes in Full Mode.")
        except Exception as e:
            logger.error(f"[Dynamic Refresh] Failed to subscribe new keys: {e}")

    return len(new_keys)
