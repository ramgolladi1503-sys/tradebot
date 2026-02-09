import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core.kite_client import kite_client
from core.cross_asset import CrossAsset
from core.market_data import get_ltp


def main():
    print("Cross-asset configured symbols:")
    symbols = getattr(cfg, "CROSS_ASSET_SYMBOLS", {}) or {}
    for k, v in symbols.items():
        print(f"  {k}: {v}")

    kite_client.ensure()
    if not kite_client.kite:
        print("ERROR: Kite not initialized. Cross-asset fetch will fail.")
        sys.exit(1)

    live_syms = [v for v in symbols.values() if v]
    if not live_syms:
        print("ERROR: No cross-asset symbols configured.")
        sys.exit(1)

    try:
        quotes = kite_client.ltp(live_syms) or {}
    except Exception as e:
        print(f"ERROR: Kite ltp failed: {e}")
        sys.exit(1)

    missing = []
    for sym in live_syms:
        price = quotes.get(sym, {}).get("last_price")
        if price is None:
            missing.append(sym)
        print(f"  {sym}: {price}")

    if missing:
        print("ERROR: Missing last_price for:")
        for sym in missing:
            print(f"  - {sym}")

    ca = CrossAsset()
    # Use current index LTPs if available to seed index history
    for idx in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        try:
            ltp = get_ltp(idx)
        except Exception:
            ltp = None
        ca.update(idx, ltp)

    payload = ca.cache
    dq = payload.get("data_quality", {})
    print("Cross-asset data quality:")
    print(f"  disabled: {dq.get('disabled')}")
    print(f"  any_stale: {dq.get('any_stale')}")
    print(f"  stale_feeds: {dq.get('stale_feeds')}")
    print(f"  age_sec: {dq.get('age_sec')}")
    print(f"  last_ts: {dq.get('last_ts')}")

    if dq.get("disabled"):
        print("FAIL: cross-asset is disabled (no valid symbols or kite unavailable)")
        sys.exit(1)
    if dq.get("any_stale"):
        print("FAIL: cross-asset stale feeds detected")
        sys.exit(1)

    if missing:
        print("FAIL: missing last_price for one or more symbols")
        sys.exit(1)

    print("check_cross_asset: OK")


if __name__ == "__main__":
    main()
