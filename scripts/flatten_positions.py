import sys
import argparse
import time
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.kite_client import kite_client
from core.telegram_alerts import send_telegram_message


def _live_positions():
    kite_client.ensure()
    if not kite_client.kite:
        raise RuntimeError("Kite not initialized")
    return kite_client.kite.positions()


def _flatten(net, dry_run=False):
    actions = []
    for row in net:
        qty = row.get("quantity") or row.get("net") or 0
        if qty == 0:
            continue
        symbol = row.get("tradingsymbol") or row.get("symbol")
        exchange = row.get("exchange") or "NFO"
        side = "SELL" if qty > 0 else "BUY"
        actions.append({"symbol": symbol, "exchange": exchange, "qty": abs(qty), "side": side})

    if dry_run:
        return actions

    if not actions:
        return actions

    for act in actions:
        try:
            kite_client.kite.place_order(
                variety=kite_client.kite.VARIETY_REGULAR,
                exchange=act["exchange"],
                tradingsymbol=act["symbol"],
                transaction_type=act["side"],
                quantity=act["qty"],
                order_type=kite_client.kite.ORDER_TYPE_MARKET,
                product=kite_client.kite.PRODUCT_MIS,
                validity=kite_client.kite.VALIDITY_DAY,
            )
        except Exception as e:
            try:
                send_telegram_message(f"Flatten failed for {act['symbol']}: {e}")
            except Exception:
                pass
    return actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if getattr(cfg, "KILL_SWITCH", False):
        print("KILL_SWITCH active; flatten only in live if you disable it.")

    if str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() != "LIVE":
        print("Execution mode not LIVE; flatten is a no-op in SIM.")
        return

    try:
        positions = _live_positions()
    except Exception as e:
        raise SystemExit(f"Could not fetch positions: {e}")

    net = positions.get("net", []) if isinstance(positions, dict) else []
    actions = _flatten(net, dry_run=args.dry_run)
    print("Flatten actions:")
    for act in actions:
        print(act)


if __name__ == "__main__":
    main()
