import argparse
import os
import runpy
import time
from pathlib import Path

runpy.run_path(Path(__file__).resolve().parents[2] / "scripts" / "bootstrap.py")

from config import config as cfg
from core.execution.chokepoint import ApprovalMissingOrInvalid, require_approval_or_abort
from core.kite_client import kite_client
from core.orders.order_intent import OrderIntent
from core.telegram_alerts import send_telegram_message


def _manual_approval_mode_enabled() -> bool:
    return bool(getattr(cfg, "MANUAL_APPROVAL_MODE", getattr(cfg, "MANUAL_APPROVAL", True)))


def _runtime_mode_guard() -> tuple[bool, str]:
    mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    if mode in ("PAPER", "LIVE") and not _manual_approval_mode_enabled():
        return False, "manual_approval_mode_disabled"
    if mode == "LIVE" and os.getenv("LIVE_TRADING_ENABLED", "false").lower() != "true":
        return False, "live_trading_env_disabled"
    return True, "ok"


def _live_positions():
    kite_client.ensure()
    if not kite_client.kite:
        raise RuntimeError("Kite not initialized")
    return kite_client.kite.positions()


def _flatten(net, dry_run=False):
    actions = []
    blocked = []
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

    mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    ok, reason = _runtime_mode_guard()
    if not ok:
        print(f"[flatten_positions] blocked: {reason}")
        return actions
    if mode != "LIVE":
        print(f"[flatten_positions] blocked: mode_not_live:{mode}")
        return actions

    for act in actions:
        intent = OrderIntent(
            symbol=str(act["symbol"] or ""),
            side=str(act["side"] or "").upper(),
            qty=int(act["qty"] or 0),
            order_type="MARKET",
            limit_price=None,
            product="MIS",
            exchange=str(act["exchange"] or "NFO").upper(),
            strategy_id="FLATTEN",
            timestamp_bucket=int(time.time() // 60),
            expiry=None,
            strike=None,
            right=None,
            multiplier=None,
        )
        try:
            require_approval_or_abort(
                intent,
                mode=mode,
                now=time.time(),
                approver=os.getenv("USER") or "flatten_script",
                ttl=int(getattr(cfg, "ORDER_APPROVAL_TTL_SEC", getattr(cfg, "APPROVAL_TTL_SEC", 600))),
            )
        except ApprovalMissingOrInvalid as exc:
            blocked.append(
                {"symbol": act["symbol"], "reason": exc.reason, "order_intent_hash": intent.order_intent_hash()}
            )
            print(f"[flatten_positions] blocked {act['symbol']}: {exc.reason}")
            continue
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
        except Exception as exc:
            try:
                send_telegram_message(f"Flatten failed for {act['symbol']}: {exc}")
            except Exception:
                pass
    if blocked:
        try:
            send_telegram_message(
                f"Flatten blocked for {len(blocked)} symbol(s) due to missing/invalid approvals."
            )
        except Exception:
            pass
    return actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--i-know-what-im-doing",
        action="store_true",
        help="Required for any non-dry-run execution.",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.i_know_what_im_doing:
        print("Refusing execution without --i-know-what-im-doing.")
        return

    if getattr(cfg, "KILL_SWITCH", False):
        print("KILL_SWITCH active; flatten only in live if you disable it.")

    mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    if mode != "LIVE":
        print(f"Execution mode {mode}; flatten is no-op outside LIVE.")
        return

    ok, reason = _runtime_mode_guard()
    if not ok:
        print(f"Refusing to run flatten: {reason}")
        return

    try:
        positions = _live_positions()
    except Exception as exc:
        raise SystemExit(f"Could not fetch positions: {exc}")

    net = positions.get("net", []) if isinstance(positions, dict) else []
    actions = _flatten(net, dry_run=args.dry_run)
    print("Flatten actions:")
    for act in actions:
        print(act)


if __name__ == "__main__":
    main()
