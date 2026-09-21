#!/usr/bin/env python3
"""Read-only Upstox option-chain sidecar for the operator cockpit.

This process is intentionally independent from the Kite/TradeBot runtime and from
the PR #912 full-mode capture process. It performs only Upstox GET requests and
writes a local UI snapshot. It never subscribes a second websocket and never
places/modifies/cancels orders.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from core.upstox_ui_snapshot import write_snapshot_atomic

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
PRIMARY_BASE_DIR = Path("/Volumes/TradeBotData/live market capture")
FALLBACK_BASE_DIR = ROOT / ".runtime" / "market_data"
UNDERLYINGS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX",
}
INTERVALS = {"NIFTY": 50.0, "BANKNIFTY": 100.0, "SENSEX": 100.0}


def output_path() -> Path:
    base = PRIMARY_BASE_DIR if PRIMARY_BASE_DIR.exists() else FALLBACK_BASE_DIR
    return base / datetime.now().strftime("%Y-%m-%d") / "upstox_live_option_chain_snapshot.json"


def _side(option: dict[str, Any] | None, prefix: str) -> dict[str, Any]:
    option = option or {}
    market = option.get("market_data") or {}
    greeks = option.get("option_greeks") or {}
    return {
        f"{prefix}_instrument_key": option.get("instrument_key"),
        f"{prefix}_ltp": market.get("ltp"),
        f"{prefix}_bid": market.get("bid_price"),
        f"{prefix}_bid_qty": market.get("bid_qty"),
        f"{prefix}_ask": market.get("ask_price"),
        f"{prefix}_ask_qty": market.get("ask_qty"),
        f"{prefix}_vol": market.get("volume"),
        f"{prefix}_oi": market.get("oi"),
        f"{prefix}_prev_oi": market.get("prev_oi"),
        f"{prefix}_iv": greeks.get("iv"),
        f"{prefix}_delta": greeks.get("delta"),
        f"{prefix}_gamma": greeks.get("gamma"),
        f"{prefix}_theta": greeks.get("theta"),
        f"{prefix}_vega": greeks.get("vega"),
    }


def fetch_chain(session: requests.Session, *, token: str, root: str, expiry: str = "current_week") -> dict[str, Any]:
    response = session.get(
        "https://api.upstox.com/v2/option/chain",
        params={"instrument_key": UNDERLYINGS[root], "expiry_date": expiry},
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        timeout=8,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or []
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"UPSTOX_OPTION_CHAIN_EMPTY:{root}")
    spot = float(data[0].get("underlying_spot_price") or 0.0)
    interval = INTERVALS[root]
    atm = round(spot / interval) * interval if spot else None
    rows = []
    for item in data:
        strike = float(item.get("strike_price") or 0.0)
        if atm is not None and abs(strike - atm) > 10 * interval:
            continue
        row = {"strike": strike, "pcr": item.get("pcr")}
        row.update(_side(item.get("call_options"), "ce"))
        row.update(_side(item.get("put_options"), "pe"))
        rows.append(row)
    rows.sort(key=lambda row: row["strike"])
    return {"expiry": data[0].get("expiry"), "spot": spot, "atm": atm, "rows": rows}


def run_once(*, token: str, expiry: str = "current_week", session: requests.Session | None = None) -> dict[str, Any]:
    http = session or requests.Session()
    chains: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for root in UNDERLYINGS:
        try:
            chains[root] = fetch_chain(http, token=token, root=root, expiry=expiry)
        except Exception as exc:
            errors[root] = f"{type(exc).__name__}:{exc}"
    now = time.time()
    payload = {
        "schema_version": 1,
        "source": "UPSTOX_OPTION_CHAIN_REST_SIDECAR_V1",
        "written_epoch": now,
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "expiry_selector": expiry,
        "chains": chains,
        "errors": errors,
    }
    write_snapshot_atomic(output_path(), payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cadence-sec", type=float, default=2.0)
    parser.add_argument("--expiry", default="current_week")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.cadence_sec < 1.0:
        raise SystemExit("cadence must be >= 1 second")
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise SystemExit("UPSTOX_ACCESS_TOKEN missing")
    while True:
        run_once(token=token, expiry=args.expiry)
        if args.once:
            return 0
        time.sleep(args.cadence_sec)


if __name__ == "__main__":
    raise SystemExit(main())
