from __future__ import annotations

from typing import Any

from core.broker.mock_broker import MockBroker
from core.events import append_event
from core.feed.sim_feed import SimFeed
from core.time_utils import utc_now


def run_golden_path(desk: str, *, run_id: str) -> dict[str, Any]:
    """
    Deterministic single-trade scenario using synthetic feed + mock broker.
    """
    feed = SimFeed()
    broker = MockBroker()

    option_symbol = "NIFTY26FEB22500CE"
    option_snapshot = feed.get_snapshot(option_symbol)

    trade_id = f"{run_id}-T1"
    intent = {
        "trade_id": trade_id,
        "symbol": option_symbol,
        "side": "BUY",
        "qty": 1.0,
        "bid": option_snapshot.get("bid"),
        "ask": option_snapshot.get("ask"),
        "ltp": option_snapshot.get("ltp"),
        "desk_id": str(desk or "DEFAULT"),
        "run_id": str(run_id),
        "mode": "PAPER",
        "ts": option_snapshot.get("ts") or utc_now().isoformat().replace("+00:00", "Z"),
    }

    append_event("trade_intent_created", intent)
    try:
        place_order = getattr(broker, "place_order")
        order_resp = place_order(intent)
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "run_id": run_id,
            "trade_id": trade_id,
        }

    fill = dict(order_resp.get("fill") or {})
    return {
        "ok": True,
        "run_id": run_id,
        "trade_id": trade_id,
        "order_id": order_resp.get("order_id"),
        "fill_price": fill.get("price"),
        "fill_qty": fill.get("qty"),
    }
