#!/usr/bin/env python3
import os
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.kite_client import kite_client


def main():
    print("Initializing Kite Client...")
    kite_client.ensure()

    print("Fetching instruments from NFO...")
    nfo_insts = kite_client.instruments_cached("NFO")
    nse_insts = kite_client.instruments_cached("NSE")

    # 1. Get Spot prices for ATM resolution
    nifty_token = None
    banknifty_token = None
    for inst in nse_insts:
        if inst["tradingsymbol"] == "NIFTY 50":
            nifty_token = inst["instrument_token"]
        if inst["tradingsymbol"] == "NIFTY BANK":
            banknifty_token = inst["instrument_token"]

    prices = kite_client.ltp([f"NSE:NIFTY 50", f"NSE:NIFTY BANK"])
    nifty_spot = prices.get("NSE:NIFTY 50", {}).get("last_price", 22000.0)
    banknifty_spot = prices.get("NSE:NIFTY BANK", {}).get("last_price", 48000.0)

    print(f"Current NIFTY Spot: {nifty_spot}")
    print(f"Current BANKNIFTY Spot: {banknifty_spot}")

    # Round to nearest 50/100
    nifty_atm = round(nifty_spot / 50.0) * 50.0
    banknifty_atm = round(banknifty_spot / 100.0) * 100.0

    # 2. Filter for closest expiry options near ATM
    nifty_opts = [
        i
        for i in nfo_insts
        if i["name"] == "NIFTY" and i["instrument_type"] in ["CE", "PE"]
    ]
    banknifty_opts = [
        i
        for i in nfo_insts
        if i["name"] == "BANKNIFTY" and i["instrument_type"] in ["CE", "PE"]
    ]

    if not nifty_opts or not banknifty_opts:
        print("ERROR: No NFO options found.")
        sys.exit(1)

    # Get closest expiry
    today = datetime.now().date()
    nifty_expiries = sorted(
        list(set([i["expiry"] for i in nifty_opts if i["expiry"] >= today]))
    )
    banknifty_expiries = sorted(
        list(set([i["expiry"] for i in banknifty_opts if i["expiry"] >= today]))
    )

    nifty_closest_exp = nifty_expiries[0]
    banknifty_closest_exp = banknifty_expiries[0]

    print(
        f"Closest Expiries: NIFTY={nifty_closest_exp}, BANKNIFTY={banknifty_closest_exp}"
    )

    # Select ATM +/- 1 strike
    target_tokens = {"NIFTY_INDEX": nifty_token, "BANKNIFTY_INDEX": banknifty_token}

    # NIFTY
    for opt in nifty_opts:
        if opt["expiry"] == nifty_closest_exp:
            if opt["strike"] in [nifty_atm - 50, nifty_atm, nifty_atm + 50]:
                target_tokens[opt["tradingsymbol"]] = opt["instrument_token"]

    # BANKNIFTY
    for opt in banknifty_opts:
        if opt["expiry"] == banknifty_closest_exp:
            if opt["strike"] in [
                banknifty_atm - 100,
                banknifty_atm,
                banknifty_atm + 100,
            ]:
                target_tokens[opt["tradingsymbol"]] = opt["instrument_token"]

    print(f"Selected {len(target_tokens)} instruments to fetch.")

    # 3. Fetch 5 days historical data
    to_date = datetime.now()
    from_date = to_date - timedelta(days=5)

    merged_data = {}  # { timestamp_str: { "SYMBOL": price, ... } }

    for symbol, token in target_tokens.items():
        print(f"Fetching 1-min data for {symbol} (token {token})...")
        try:
            history = kite_client.historical(
                instrument_token=token,
                from_date=from_date,
                to_date=to_date,
                interval="minute",
                _symbol=symbol,
                _caller="fetch_active_options",
            )
            for candle in history:
                dt_str = (
                    candle["date"].isoformat()
                    if hasattr(candle["date"], "isoformat")
                    else str(candle["date"])
                )
                if dt_str not in merged_data:
                    merged_data[dt_str] = {"timestamp": dt_str}
                merged_data[dt_str][symbol] = candle["close"]
        except Exception as e:
            print(f"Failed to fetch {symbol}: {e}")

    # Sort chronologically
    sorted_ticks = []
    for ts in sorted(merged_data.keys()):
        sorted_ticks.append(merged_data[ts])

    print(
        f"Successfully merged {len(sorted_ticks)} synchronous ticks across multiple assets."
    )

    out_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "active_options_replay.json"
    )
    with open(out_path, "w") as f:
        json.dump(sorted_ticks, f, indent=2)

    print(f"Data saved to {out_path}")


if __name__ == "__main__":
    main()
