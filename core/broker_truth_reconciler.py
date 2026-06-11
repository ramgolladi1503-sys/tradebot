from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Iterable, Mapping

from config import config as cfg
from core import risk_halt
from core.events import append_event, events_path, read_events
from core.incidents import SEV2, create_incident
from core.kite_client import kite_client
from core.runtime_lifecycle import lifecycle as runtime_lifecycle


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 1_000_000_000_000:
            raw /= 1000.0
        return raw
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _side_sign(side: Any) -> float:
    return -1.0 if _upper(side) == "SELL" else 1.0


@dataclass(frozen=True)
class _ToleranceConfig:
    max_qty: float
    max_open_orders: int
    max_price_bps: float
    fill_stale_window_sec: float
    auto_flatten_on_drift: bool
    halt_entries_on_detect: bool


class BrokerTruthReconciler:
    def __init__(
        self,
        desk_id: str,
        broker: Any,
        tolerance_cfg: Mapping[str, Any] | None,
        lifecycle: Any | None,
    ):
        self.desk_id = _text(desk_id) or "DEFAULT"
        self.broker = broker
        self.lifecycle = lifecycle or runtime_lifecycle
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._interval_s = float(getattr(cfg, "BROKER_TRUTH_INTERVAL_S", 60.0))
        self._lock = threading.RLock()
        self._tolerance = self._resolve_tolerances(tolerance_cfg or {})

    def _resolve_tolerances(self, overrides: Mapping[str, Any]) -> _ToleranceConfig:
        max_qty = _to_float(overrides.get("max_qty"), _to_float(getattr(cfg, "DRIFT_MAX_QTY", 0.0), 0.0))
        max_open_orders = int(overrides.get("max_open_orders", int(getattr(cfg, "DRIFT_MAX_OPEN_ORDERS", 0))))
        max_price_bps = _to_float(overrides.get("max_price_bps"), _to_float(getattr(cfg, "DRIFT_MAX_PRICE_BPS", 25.0), 25.0))
        fill_stale_window_sec = _to_float(
            overrides.get("fill_stale_window_sec"),
            _to_float(getattr(cfg, "DRIFT_FILL_STALE_WINDOW_SEC", 30.0), 30.0),
        )
        auto_flatten_on_drift = bool(
            overrides.get(
                "auto_flatten_on_drift",
                bool(getattr(cfg, "AUTO_FLATTEN_ON_DRIFT", False)),
            )
        )
        halt_entries_on_detect = bool(
            overrides.get(
                "halt_entries_on_detect",
                bool(getattr(cfg, "DRIFT_HALT_ENTRIES_ON_DETECT", True)),
            )
        )
        return _ToleranceConfig(
            max_qty=max_qty,
            max_open_orders=max_open_orders,
            max_price_bps=max_price_bps,
            fill_stale_window_sec=fill_stale_window_sec,
            auto_flatten_on_drift=auto_flatten_on_drift,
            halt_entries_on_detect=halt_entries_on_detect,
        )

    def start(self, interval_s: float = 60) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._interval_s = max(1.0, float(interval_s))
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._run_loop,
                name=f"broker-truth-reconciler:{self.desk_id}",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            self.lifecycle.register(
                f"broker-truth-reconciler:{self.desk_id}",
                stop_fn=lambda: self.stop(),
                join_fn=lambda timeout_sec=3.0: self._join(timeout_sec),
                thread=thread,
            )
            return True

    def _join(self, timeout_sec: float) -> None:
        thread = self._thread
        if thread is None or thread is threading.current_thread():
            return
        thread.join(max(0.0, float(timeout_sec)))

    def stop(self) -> bool:
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        with self._lock:
            self._thread = None
        return True

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                append_event(
                    "broker_truth_reconcile_error",
                    {
                        "desk_id": self.desk_id,
                        "error": f"{type(exc).__name__}:{exc}",
                    },
                )
            self._stop_event.wait(max(1.0, float(self._interval_s)))

    def _call_broker_rows(self, method_names: Iterable[str]) -> list[dict[str, Any]]:
        for name in method_names:
            fn = getattr(self.broker, name, None)
            if not callable(fn):
                continue
            raw = fn()
            if isinstance(raw, list):
                return [dict(row) for row in raw if isinstance(row, dict)]
            if isinstance(raw, dict):
                for key in ("data", "orders", "positions", "trades", "result", "net"):
                    block = raw.get(key)
                    if isinstance(block, list):
                        return [dict(row) for row in block if isinstance(row, dict)]
        return []

    def _fetch_broker_truth(self) -> dict[str, Any]:
        open_orders = self._call_broker_rows(("open_orders", "orders"))
        positions = self._call_broker_rows(("positions",))
        fills = self._call_broker_rows(("recent_fills", "trades"))
        return {
            "open_orders": open_orders,
            "positions": positions,
            "recent_fills": fills,
        }

    def _internal_truth_from_events(self) -> dict[str, Any]:
        rows = read_events(path=events_path())
        order_state: dict[str, str] = {}
        order_payload: dict[str, dict[str, Any]] = {}
        positions: dict[str, dict[str, float]] = {}
        fills_by_id: dict[str, dict[str, Any]] = {}

        for row in rows:
            event_type = _text(row.get("type"))
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            order_id = _text(payload.get("order_id"))
            trade_id = _text(payload.get("trade_id"))
            fill_id = _text(payload.get("fill_id") or trade_id or payload.get("event_id"))

            if event_type in {"order_submitted", "order_open", "order_acknowledged"} and order_id:
                order_state[order_id] = "OPEN"
                order_payload[order_id] = payload
            if event_type in {"order_cancelled", "order_rejected", "order_expired"} and order_id:
                order_state[order_id] = "CLOSED"
            if event_type in {"fill", "order_filled"}:
                symbol = _upper(payload.get("symbol"))
                side = _upper(payload.get("side") or "BUY")
                qty = _to_float(payload.get("qty"), 0.0)
                price = _to_float(payload.get("price"), 0.0)
                if symbol and qty > 0:
                    slot = positions.setdefault(symbol, {"net_qty": 0.0, "signed_notional": 0.0})
                    signed_qty = _side_sign(side) * qty
                    slot["net_qty"] += signed_qty
                    slot["signed_notional"] += signed_qty * price
                if fill_id:
                    fills_by_id[fill_id] = {
                        "fill_id": fill_id,
                        "ts": row.get("ts"),
                    }
                if order_id:
                    pending_qty = _to_float(payload.get("pending_qty"), 0.0)
                    if pending_qty <= 0:
                        order_state[order_id] = "CLOSED"

        internal_positions: dict[str, dict[str, float]] = {}
        for symbol, agg in positions.items():
            net_qty = _to_float(agg.get("net_qty"), 0.0)
            signed_notional = _to_float(agg.get("signed_notional"), 0.0)
            avg_price = abs(signed_notional / net_qty) if abs(net_qty) > 0 else 0.0
            internal_positions[symbol] = {"net_qty": net_qty, "avg_price": avg_price}

        internal_open_orders = {
            oid: order_payload.get(oid, {"order_id": oid})
            for oid, state in order_state.items()
            if state == "OPEN"
        }
        return {
            "positions": internal_positions,
            "open_orders": internal_open_orders,
            "fills_by_id": fills_by_id,
        }

    def _aggregate_broker_positions(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for row in rows:
            symbol = _upper(row.get("symbol") or row.get("tradingsymbol"))
            if not symbol:
                continue
            qty = _to_float(row.get("quantity"), _to_float(row.get("net_quantity"), 0.0))
            if qty == 0 and row.get("quantity") is None and row.get("net_quantity") is None:
                buy_qty = _to_float(row.get("buy_quantity"), 0.0)
                sell_qty = _to_float(row.get("sell_quantity"), 0.0)
                qty = buy_qty - sell_qty
            avg_price = _to_float(
                row.get("average_price"),
                _to_float(row.get("avg_price"), _to_float(row.get("last_price"), 0.0)),
            )
            slot = out.setdefault(symbol, {"net_qty": 0.0, "weighted_notional": 0.0})
            slot["net_qty"] += qty
            slot["weighted_notional"] += qty * avg_price
        normalized: dict[str, dict[str, float]] = {}
        for symbol, agg in out.items():
            net_qty = _to_float(agg.get("net_qty"), 0.0)
            weighted_notional = _to_float(agg.get("weighted_notional"), 0.0)
            avg_price = abs(weighted_notional / net_qty) if abs(net_qty) > 0 else 0.0
            normalized[symbol] = {"net_qty": net_qty, "avg_price": avg_price}
        return normalized

    def _open_order_ids(self, rows: Iterable[dict[str, Any]]) -> set[str]:
        out: set[str] = set()
        for row in rows:
            oid = _text(row.get("order_id") or row.get("id") or row.get("broker_order_id"))
            if oid:
                out.add(oid)
        return out

    def _fill_id_set(self, rows: Iterable[dict[str, Any]], now_epoch: float) -> set[str]:
        out: set[str] = set()
        for row in rows:
            fill_id = _text(row.get("fill_id") or row.get("trade_id") or row.get("id"))
            if not fill_id:
                continue
            ts_epoch = _to_epoch(row.get("ts") or row.get("timestamp") or row.get("exchange_timestamp"))
            if ts_epoch is not None:
                age = max(0.0, now_epoch - ts_epoch)
                if age < self._tolerance.fill_stale_window_sec:
                    continue
            out.add(fill_id)
        return out

    def _compare_truth(self, broker_truth: Mapping[str, Any], internal_truth: Mapping[str, Any]) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        broker_positions = self._aggregate_broker_positions(
            [row for row in (broker_truth.get("positions") or []) if isinstance(row, dict)]
        )
        internal_positions = {
            _upper(symbol): dict(values)
            for symbol, values in dict(internal_truth.get("positions") or {}).items()
        }
        symbols = sorted(set(broker_positions.keys()) | set(internal_positions.keys()))
        for symbol in symbols:
            broker_slot = broker_positions.get(symbol, {"net_qty": 0.0, "avg_price": 0.0})
            internal_slot = internal_positions.get(symbol, {"net_qty": 0.0, "avg_price": 0.0})
            broker_qty = _to_float(broker_slot.get("net_qty"), 0.0)
            internal_qty = _to_float(internal_slot.get("net_qty"), 0.0)
            qty_diff = broker_qty - internal_qty
            if abs(qty_diff) > self._tolerance.max_qty:
                mismatches.append(
                    {
                        "code": "POSITION_QTY_MISMATCH",
                        "symbol": symbol,
                        "broker_qty": broker_qty,
                        "internal_qty": internal_qty,
                        "qty_diff": qty_diff,
                        "tolerance": self._tolerance.max_qty,
                    }
                )
            broker_price = _to_float(broker_slot.get("avg_price"), 0.0)
            internal_price = _to_float(internal_slot.get("avg_price"), 0.0)
            if broker_price > 0 and internal_price > 0:
                bps = abs((broker_price - internal_price) / internal_price) * 10_000.0
                if bps > self._tolerance.max_price_bps:
                    mismatches.append(
                        {
                            "code": "POSITION_PRICE_MISMATCH",
                            "symbol": symbol,
                            "broker_avg_price": broker_price,
                            "internal_avg_price": internal_price,
                            "price_diff_bps": bps,
                            "tolerance_bps": self._tolerance.max_price_bps,
                        }
                    )

        broker_open_orders = self._open_order_ids(
            [row for row in (broker_truth.get("open_orders") or []) if isinstance(row, dict)]
        )
        internal_open_orders = self._open_order_ids(
            list((internal_truth.get("open_orders") or {}).values())
        )
        missing_in_broker = sorted(internal_open_orders - broker_open_orders)
        extra_in_broker = sorted(broker_open_orders - internal_open_orders)
        if len(missing_in_broker) > self._tolerance.max_open_orders:
            mismatches.append(
                {
                    "code": "OPEN_ORDER_MISSING_IN_BROKER",
                    "count": len(missing_in_broker),
                    "order_ids": missing_in_broker,
                    "tolerance": self._tolerance.max_open_orders,
                }
            )
        if len(extra_in_broker) > self._tolerance.max_open_orders:
            mismatches.append(
                {
                    "code": "OPEN_ORDER_EXTRA_IN_BROKER",
                    "count": len(extra_in_broker),
                    "order_ids": extra_in_broker,
                    "tolerance": self._tolerance.max_open_orders,
                }
            )

        now_epoch = time.time()
        broker_fills = self._fill_id_set(
            [row for row in (broker_truth.get("recent_fills") or []) if isinstance(row, dict)],
            now_epoch=now_epoch,
        )
        internal_fills = set((internal_truth.get("fills_by_id") or {}).keys())
        missing_fills = sorted(broker_fills - internal_fills)
        if missing_fills:
            mismatches.append(
                {
                    "code": "FILL_MISSING_INTERNAL",
                    "count": len(missing_fills),
                    "fill_ids": missing_fills,
                    "stale_window_sec": self._tolerance.fill_stale_window_sec,
                }
            )
        return mismatches

    def _flatten_positions(self, broker_positions_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for row in broker_positions_rows:
            symbol = _upper(row.get("symbol") or row.get("tradingsymbol"))
            if not symbol:
                continue
            qty = _to_float(row.get("quantity"), _to_float(row.get("net_quantity"), 0.0))
            if qty == 0:
                buy_qty = _to_float(row.get("buy_quantity"), 0.0)
                sell_qty = _to_float(row.get("sell_quantity"), 0.0)
                qty = buy_qty - sell_qty
            if qty == 0:
                continue
            side = "SELL" if qty > 0 else "BUY"
            payload = {
                "symbol": symbol,
                "side": side,
                "qty": abs(qty),
                "order_type": "MARKET",
                "reason": "broker_drift_auto_flatten",
                "desk_id": self.desk_id,
            }
            append_event("flatten_requested", payload)
            result: dict[str, Any] = {"symbol": symbol, "side": side, "qty": abs(qty), "status": "ERROR"}
            try:
                place_order = getattr(self.broker, "place_order", None)
                if callable(place_order):
                    broker_resp = place_order(payload)
                else:
                    order_place = getattr(self.broker, "order_place", None)
                    if callable(order_place):
                        broker_resp = order_place(payload)
                    else:
                        raise RuntimeError("flatten_order_method_missing")
                result["status"] = "OK"
                result["broker_response"] = broker_resp
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}:{exc}"
            append_event("flatten_result", result)
            actions.append(result)
        return actions

    def run_once(self) -> dict[str, Any]:
        broker_truth = self._fetch_broker_truth()
        internal_truth = self._internal_truth_from_events()
        mismatches = self._compare_truth(broker_truth, internal_truth)
        actions: list[dict[str, Any]] = []
        status = "OK"

        if mismatches:
            status = "DRIFT"
            context = {
                "desk_id": self.desk_id,
                "mismatch_count": len(mismatches),
                "mismatches": mismatches,
            }
            append_event("drift_detected", context)
            incident_id = create_incident(SEV2, "BROKER_DRIFT", context)
            actions.append({"action": "incident", "incident_id": incident_id})

            if self._tolerance.halt_entries_on_detect:
                try:
                    risk_halt.set_halt("broker_drift", {"incident_id": incident_id, **context})
                    actions.append({"action": "halt_entries", "status": "OK"})
                except Exception as exc:
                    actions.append({"action": "halt_entries", "status": "ERROR", "error": str(exc)})

            if self._tolerance.auto_flatten_on_drift:
                flatten_actions = self._flatten_positions(
                    [row for row in (broker_truth.get("positions") or []) if isinstance(row, dict)]
                )
                actions.extend({"action": "flatten", **entry} for entry in flatten_actions)

        report = {
            "status": status,
            "desk_id": self.desk_id,
            "mismatches": mismatches,
            "actions": actions,
            "counts": {
                "broker_open_orders": len(broker_truth.get("open_orders") or []),
                "broker_positions": len(broker_truth.get("positions") or []),
                "broker_recent_fills": len(broker_truth.get("recent_fills") or []),
                "internal_open_orders": len(internal_truth.get("open_orders") or {}),
                "internal_positions": len(internal_truth.get("positions") or {}),
                "internal_fills": len(internal_truth.get("fills_by_id") or {}),
            },
        }
        append_event("broker_truth_reconcile", report)
        return report


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Broker truth reconciliation runner")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    parser.add_argument("--once", action="store_true", help="run single reconciliation cycle and exit")
    parser.add_argument("--interval", type=float, default=float(getattr(cfg, "BROKER_TRUTH_INTERVAL_S", 60.0)))
    args = parser.parse_args()

    kite_client.ensure()
    broker = getattr(kite_client, "kite", None)
    if broker is None:
        raise SystemExit("broker API unavailable")
    reconciler = BrokerTruthReconciler(
        desk_id=str(args.desk),
        broker=broker,
        tolerance_cfg={},
        lifecycle=runtime_lifecycle,
    )
    if args.once:
        report = reconciler.run_once()
        print(report)
        return 0
    reconciler.start(interval_s=float(args.interval))
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        reconciler.stop()
        return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
