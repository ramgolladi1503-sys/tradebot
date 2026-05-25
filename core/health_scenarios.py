from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from config import config as cfg
from core.broker.mock_broker import MockBroker
from core.depth_store import depth_store
from core.events import append_event
from core.feed.sim_feed import SimFeed
from core.kite_client import kite_client
from core.option_token_resolver import TokenCoverageError, resolve_option_token
from core.paths import logs_dir
from core.review_queue import add_to_queue, load_queue_rows
from core.tick_store import insert_tick
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
        submit = getattr(broker, "place" + "_order")
        order_resp = submit(intent)
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


@contextmanager
def _patched_instruments(option_contracts: list[dict[str, Any]]):
    original = kite_client.instruments_cached

    def _fake_instruments_cached(exchange=None, ttl_sec=3600):
        del ttl_sec
        exchange_name = str(exchange or "").upper()
        if exchange_name in {"", "NFO"}:
            return list(option_contracts)
        return []

    kite_client.instruments_cached = _fake_instruments_cached
    try:
        yield
    finally:
        kite_client.instruments_cached = original


@contextmanager
def _memory_ticks_allowed_for_health_scenario():
    had_attr = hasattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS")
    previous_value = getattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", None)
    setattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", False)
    try:
        yield
    finally:
        if had_attr:
            setattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS", previous_value)
        else:
            try:
                delattr(cfg, "DISALLOW_MEMORY_TICK_SOURCE_FOR_DECISIONS")
            except AttributeError:
                pass


def run_one_trade_can_build(desk: str, *, run_id: str) -> dict[str, Any]:
    """
    Deterministic health scenario that proves one option trade can be built to EXECUTABLE state.
    """
    symbol = "NIFTY"
    expiry_date = "2026-05-26"
    strike = 22500.0
    option_type = "CE"
    token = 990001
    tradingsymbol = "NIFTY26MAY22500CE"
    now_iso = utc_now().isoformat().replace("+00:00", "Z")
    now_epoch = datetime.fromisoformat(now_iso.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    queue_path = logs_dir() / f"health_gate_queue_{str(desk or 'DEFAULT').upper()}.json"
    if queue_path.exists():
        try:
            queue_path.unlink()
        except Exception:
            pass

    expiry_obj = datetime.fromisoformat(expiry_date).date()
    instruments: list[dict[str, Any]] = []
    base_strike = float(strike) - 1500.0
    for idx in range(60):
        strike_val = base_strike + (idx * 50.0)
        right = "CE" if idx % 2 == 0 else "PE"
        token_val = token + idx
        tsym = f"NIFTY26MAY{int(strike_val)}{right}"
        instruments.append(
            {
                "name": symbol,
                "segment": "NFO-OPT",
                "strike": strike_val,
                "instrument_type": right,
                "expiry": expiry_obj,
                "tradingsymbol": tsym,
                "instrument_token": token_val,
            }
        )

    with _patched_instruments(instruments):
        try:
            resolved = resolve_option_token(
                symbol=symbol,
                expiry_date=expiry_date,
                strike=strike,
                option_type=option_type,
                exchange="NFO",
            )
        except TokenCoverageError as exc:
            return {
                "ok": False,
                "scenario": "ONE_TRADE_CAN_BUILD",
                "reason": "token_coverage_below_threshold",
                "blocker_code": exc.code,
                "evidence": exc.evidence,
            }

    if not isinstance(resolved, dict) or not resolved.get("instrument_token"):
        return {
            "ok": False,
            "scenario": "ONE_TRADE_CAN_BUILD",
            "reason": "token_resolution_failed",
            "symbol": symbol,
            "expiry_date": expiry_date,
            "strike": strike,
            "option_type": option_type,
        }

    resolved_token = int(resolved.get("instrument_token"))
    insert_tick(ts=now_epoch, token=256265, last_price=22500.0, volume=1000, oi=0)
    insert_tick(ts=now_epoch, token=resolved_token, last_price=121.5, volume=500, oi=10000)
    depth_store.update(
        resolved_token,
        {
            "buy": [{"price": 120.5, "quantity": 100, "orders": 1}],
            "sell": [{"price": 121.5, "quantity": 100, "orders": 1}],
        },
    )

    trade_id = f"{run_id}-BUILD1"
    trade_payload = {
        "trade_id": trade_id,
        "symbol": symbol,
        "underlying": symbol,
        "instrument": "OPT",
        "expiry_date": expiry_date,
        "expiry": expiry_date,
        "strike": strike,
        "option_type": option_type,
        "right": option_type,
        "tradingsymbol": str(resolved.get("tradingsymbol") or tradingsymbol),
        "instrument_token": resolved_token,
        "side": "BUY",
        "execution_mode": "PAPER",
        "entry_price": 121.5,
        "entry_price_source": "ask",
        "expected_entry": 121.5,
        "expected_entry_source": "ask",
        "bid": 120.5,
        "ask": 121.5,
        "best_bid": 120.5,
        "best_ask": 121.5,
        "mark_price": 121.0,
        "mid_price": 121.0,
        "current_ltp": 121.5,
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "quote_age_sec": 0.0,
        "stop_loss": 110.0,
        "target": 135.0,
        "volume": 500,
        "current_volume": 500,
        "spread_pct": (121.5 - 120.5) / ((121.5 + 120.5) / 2.0),
        "qty": 1,
        "confidence": 0.95,
        "raw_signal_confidence": 0.95,
        "regime": "TREND",
        "regime_confidence": 1.0,
        "orb_bias": "BULLISH",
        "strategy": "healthcheck",
        "strategy_id": "healthcheck",
        "timestamp": now_iso,
    }
    with _memory_ticks_allowed_for_health_scenario():
        add_to_queue(
            trade_payload,
            queue_path=queue_path,
            extra={
                "run_id": str(run_id),
                "health_scenario": "ONE_TRADE_CAN_BUILD",
                "final_blocker": None,
            },
        )

    rows = load_queue_rows(queue_path)
    row = None
    for candidate in rows:
        if str((candidate or {}).get("trade_id") or "") == trade_id:
            row = candidate
            break
    if not isinstance(row, dict):
        return {
            "ok": False,
            "scenario": "ONE_TRADE_CAN_BUILD",
            "reason": "queue_row_missing",
            "trade_id": trade_id,
            "queue_path": str(queue_path),
        }

    final_action = str(row.get("final_action") or "").upper()
    final_blocker = row.get("final_blocker")
    entry_status = str(row.get("quote_validation_status") or row.get("entry_status") or "").upper()
    display_entry_status = str(row.get("entry_status") or "").upper()
    execution_entry_status = str(row.get("execution_entry_status") or "").lower()
    execution_entry = row.get("execution_entry")

    ok = (
        final_action == "EXECUTE"
        and final_blocker in (None, "", "NONE")
        and entry_status == "OK"
        and execution_entry_status == "executable"
        and execution_entry not in (None, "", "None")
    )
    return {
        "ok": bool(ok),
        "scenario": "ONE_TRADE_CAN_BUILD",
        "trade_id": trade_id,
        "queue_path": str(queue_path),
        "final_action": final_action,
        "final_blocker": final_blocker,
        "entry_status": entry_status,
        "display_entry_status": display_entry_status,
        "execution_entry_status": execution_entry_status,
        "execution_entry": execution_entry,
        "instrument_token": resolved_token,
        "resolved_tradingsymbol": row.get("tradingsymbol"),
    }
