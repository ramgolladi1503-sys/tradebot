from __future__ import annotations
import logging
from datetime import date
import pandas as pd

logger = logging.getLogger(__name__)

def refresh_late_day_option_subscriptions(
    streamer,
    subscriptions: dict[str, str],
    df_inst: pd.DataFrame,
    current_spot_price: float,
    *,
    verified_contracts: dict[str, dict] | None = None,
) -> int:
    """
    Dynamically refreshes and subscribes late-day ATM and ATM +/- 100 strikes
    around current spot price at ~15:23-15:24 IST.
    Prevents large intraday moves (e.g. 300+ pts) from causing desired ATM strikes
    to be missing at 15:26 signal decision time.
    Never unsubscribes active feeds.
    Returns the count of newly subscribed option contracts.
    """
    if df_inst.empty or not current_spot_price or streamer is None or not verified_contracts:
        return 0

    atm = round(current_spot_price / 50.0) * 50.0
    # Capture ATM +/- 5 strikes (covers ATM, ATM +/- 100 for V2-B, and safety buffer)
    desired_strikes = [atm + (i * 50.0) for i in range(-5, 6)]

    new_keys: list[str] = []
    symbols_by_key: dict[str, str] = {}
    for key, evidence in verified_contracts.items():
        if not key.startswith("NSE_FO|") or evidence.get("upstox_instrument_key") != key:
            continue
        if evidence.get("underlying") != "NIFTY" or evidence.get("option_type") not in {"CE", "PE"}:
            continue
        try:
            strike = float(evidence.get("strike"))
        except (TypeError, ValueError, OverflowError):
            continue
        if strike not in desired_strikes:
            continue
        if (
            not evidence.get("contract_key")
            or not evidence.get("upstox_trading_symbol")
            or evidence.get("nse_permitted_to_trade") is not True
            or evidence.get("nse_deleted") is not False
            or evidence.get("nse_normal_market_eligible") is not True
            or evidence.get("nse_normal_market_trading_status") != 2
        ):
            continue
        try:
            expiry = date.fromisoformat(str(evidence.get("expiry")))
            expected_key = (
                f"{evidence['underlying']}|{expiry.isoformat()}|{strike:g}|{evidence['option_type']}"
            )
        except (KeyError, TypeError, ValueError):
            continue
        if evidence.get("contract_key") != expected_key:
            continue
        if key not in subscriptions:
            new_keys.append(key)
            symbols_by_key[key] = evidence["upstox_trading_symbol"]

    if new_keys:
        try:
            streamer.subscribe(new_keys, mode="full")
            subscriptions.update(symbols_by_key)
            logger.info(f"[Late-Day Refresh] Dynamically subscribed {len(new_keys)} new NIFTY option strikes around spot {current_spot_price:.1f} (ATM {atm:.0f}).")
        except Exception as e:
            logger.error(f"[Late-Day Refresh] Failed to subscribe new keys: {e}")
            return 0

    return len(new_keys)
