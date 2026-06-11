"""Migration note:
Background reconciliation daemon that compares broker order/position snapshots
against internal order-state records and repairs deterministic mismatches.
"""

from __future__ import annotations

from core.paths import logs_dir
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import threading
import time
import weakref
from typing import Any

from config import config as cfg
from core.kite_client import kite_client
from core.orders.state_machine import (
    OrderRecord,
    OrderState,
    OrderStateMachine,
    OrderStateTransitionError,
)
from core.runtime_lifecycle import lifecycle


_OPEN_STATUSES = {
    "OPEN",
    "TRIGGER PENDING",
    "PUT ORDER REQ RECEIVED",
    "VALIDATION PENDING",
    "MODIFY VALIDATION PENDING",
    "MODIFY PENDING",
    "AMO REQ RECEIVED",
    "AMO REQ PROCESSING",
    "AMO MOD VALIDATION PENDING",
    "AMO MOD PENDING",
}

_TERMINAL_STATES = {
    OrderState.FILLED,
    OrderState.REJECTED,
    OrderState.CANCELLED,
    OrderState.EXPIRED,
}

_DAEMON_REGISTRY_LOCK = threading.RLock()
_DAEMON_REGISTRY: weakref.WeakSet["OrderReconciliationDaemon"] = weakref.WeakSet()
_NONLIVE_BROKER_AUTH_SKIP_MODES = {"SIM", "DRY_RUN", "PAPER", "PAPER_TRADING", "BACKTEST", "TEST"}
_LIVE_MODES = {"LIVE"}


@dataclass(frozen=True)
class ReconciliationCycleResult:
    scanned_orders: int
    corrections: int
    errors: int
    broker_open_orders: int
    broker_positions: int
    started_at: float
    ended_at: float


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _status_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _env_flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _runtime_mode_values() -> set[str]:
    values = {
        str(os.getenv("EXECUTION_MODE") or getattr(cfg, "EXECUTION_MODE", "") or "").strip().upper(),
        str(os.getenv("TRADING_MODE") or getattr(cfg, "TRADING_MODE", "") or "").strip().upper(),
    }
    return {value for value in values if value}


def _skip_broker_auth_resolution() -> bool:
    dry_run_enabled = bool(getattr(cfg, "DRY_RUN", False) or _env_flag_enabled("DRY_RUN"))
    if dry_run_enabled:
        return True
    modes = _runtime_mode_values() or {"SIM"}
    if modes & _LIVE_MODES:
        return False
    return bool(modes & _NONLIVE_BROKER_AUTH_SKIP_MODES)


def _broker_order_id(order_row: dict[str, Any]) -> str:
    for key in ("order_id", "broker_order_id", "id"):
        raw = str(order_row.get(key) or "").strip()
        if raw:
            return raw
    return ""


def _broker_filled_qty(order_row: dict[str, Any]) -> float:
    for key in ("filled_quantity", "filled_qty", "filled", "executed_quantity"):
        if key in order_row:
            return max(0.0, _as_float(order_row.get(key), 0.0))
    status = _status_text(order_row.get("status"))
    if status in {"COMPLETE", "FILLED"}:
        return max(0.0, _as_float(order_row.get("quantity"), 0.0))
    return 0.0


def _broker_pending_qty(order_row: dict[str, Any]) -> float:
    for key in ("pending_quantity", "pending_qty", "pending"):
        if key in order_row:
            return max(0.0, _as_float(order_row.get(key), 0.0))
    return 0.0


def _target_state_from_broker(order_row: dict[str, Any]) -> OrderState | None:
    status = _status_text(order_row.get("status"))
    filled_qty = _broker_filled_qty(order_row)
    pending_qty = _broker_pending_qty(order_row)

    if filled_qty > 0 and pending_qty > 0:
        return OrderState.PARTIAL
    if status in {"COMPLETE", "FILLED"}:
        return OrderState.FILLED
    if status == "REJECTED":
        return OrderState.REJECTED
    if status in {"CANCELLED", "CANCELED"}:
        return OrderState.CANCELLED
    if status in {"LAPSED", "EXPIRED"}:
        return OrderState.EXPIRED
    if status in _OPEN_STATUSES:
        return OrderState.ACKNOWLEDGED
    return None


class OrderReconciliationDaemon:
    """
    Async background daemon that reconciles broker state vs internal order state.
    """

    def __init__(
        self,
        *,
        order_state_machine: OrderStateMachine | None = None,
        broker_api: Any | None = None,
        interval_sec: float | None = None,
        log_path: str | Path | None = None,
        network_retries: int | None = None,
        retry_delay_sec: float | None = None,
    ):
        self._sm = order_state_machine or OrderStateMachine()
        self._broker_api = broker_api
        self._interval_sec = max(0.5, float(interval_sec if interval_sec is not None else getattr(cfg, "ORDER_RECON_INTERVAL_SEC", 5.0)))
        self._log_path = Path(str(log_path or getattr(cfg, "ORDER_RECON_LOG_PATH", str(logs_dir() / "order_reconciliation.jsonl"))))
        self._network_retries = max(1, int(network_retries if network_retries is not None else getattr(cfg, "ORDER_RECON_NETWORK_RETRIES", 3)))
        self._retry_delay_sec = max(0.0, float(retry_delay_sec if retry_delay_sec is not None else getattr(cfg, "ORDER_RECON_RETRY_DELAY_SEC", 0.75)))
        self._scan_limit = max(1, int(getattr(cfg, "ORDER_RECON_SCAN_LIMIT", 2000)))

        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_cycle_ts_epoch: float | None = None
        with _DAEMON_REGISTRY_LOCK:
            _DAEMON_REGISTRY.add(self)

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    @property
    def last_cycle_ts_epoch(self) -> float | None:
        with self._state_lock:
            return self._last_cycle_ts_epoch

    def set_broker_api(self, broker_api: Any) -> None:
        with self._state_lock:
            self._broker_api = broker_api

    def start(self) -> bool:
        thread: threading.Thread | None = None
        with self._state_lock:
            if self.is_running:
                return False
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._thread_main,
                name="order-reconciliation-daemon",
                daemon=True,
            )
            self._thread = thread
            self._thread.start()
        if thread is not None:
            lifecycle.register(
                f"order-reconciliation-daemon:{id(self)}",
                stop_fn=lambda: self.stop(timeout_sec=3.0),
                join_fn=lambda timeout_sec=3.0: self._join_thread(timeout_sec=timeout_sec),
            )
        self._write_log(
            "daemon_started",
            {
                "interval_sec": self._interval_sec,
                "network_retries": self._network_retries,
                "scan_limit": self._scan_limit,
            },
            level="INFO",
        )
        return True

    def stop(self, timeout_sec: float = 5.0) -> bool:
        thread: threading.Thread | None
        with self._state_lock:
            thread = self._thread
            if thread is None:
                return True
            self._write_log(
                "daemon_stopping",
                {"timeout_sec": float(timeout_sec)},
                level="INFO",
            )
            self._stop_event.set()
            loop = self._loop
            if loop and loop.is_running():
                loop.call_soon_threadsafe(lambda: None)
        if thread is not threading.current_thread():
            thread.join(max(0.1, float(timeout_sec)))
        clean = not thread.is_alive()
        with self._state_lock:
            if self._thread is thread:
                self._thread = None
                self._loop = None
        return clean

    def close(self, timeout_sec: float = 5.0) -> bool:
        return self.stop(timeout_sec=timeout_sec)

    def _join_thread(self, timeout_sec: float = 3.0) -> None:
        with self._state_lock:
            thread = self._thread
        if thread is None:
            return
        if thread is threading.current_thread():
            return
        thread.join(max(0.0, float(timeout_sec)))

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        with self._state_lock:
            self._loop = loop
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run_forever())
        except RuntimeError:
            if not self._stop_event.is_set():
                raise
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.close()
            with self._state_lock:
                self._loop = None

    async def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            started = time.time()
            try:
                self.run_cycle_once()
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self._write_log(
                    "reconcile_cycle_error",
                    {"error": f"{type(exc).__name__}:{exc}"},
                    level="ERROR",
                )
            elapsed = time.time() - started
            wait_sec = max(0.0, self._interval_sec - elapsed)
            if wait_sec > 0:
                # Avoid thread-pool scheduling during interpreter shutdown.
                sleep_step = min(0.25, wait_sec)
                remaining = wait_sec
                while remaining > 0 and not self._stop_event.is_set():
                    await asyncio.sleep(min(sleep_step, remaining))
                    remaining -= sleep_step

    def _resolve_broker_api(self) -> Any:
        if self._broker_api is not None:
            return self._broker_api
        if _skip_broker_auth_resolution():
            raise RuntimeError("broker_api_unavailable")
        try:
            kite_client.ensure()
        except Exception:
            pass
        api = getattr(kite_client, "kite", None)
        if api is None:
            raise RuntimeError("broker_api_unavailable")
        return api

    def _with_retry(self, fn, call_name: str):
        last_exc: Exception | None = None
        for attempt in range(1, self._network_retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                self._write_log(
                    "reconcile_network_retry",
                    {
                        "call": call_name,
                        "attempt": attempt,
                        "max_attempts": self._network_retries,
                        "error": f"{type(exc).__name__}:{exc}",
                    },
                    level="WARN",
                )
                if attempt < self._network_retries and self._retry_delay_sec > 0:
                    time.sleep(self._retry_delay_sec)
        raise RuntimeError(f"{call_name}_failed:{last_exc}")

    def _fetch_broker_orders(self, broker_api: Any) -> list[dict[str, Any]]:
        if hasattr(broker_api, "orders") and callable(broker_api.orders):
            raw = broker_api.orders()
        elif hasattr(broker_api, "open_orders") and callable(broker_api.open_orders):
            raw = broker_api.open_orders()
        else:
            raise RuntimeError("broker_orders_method_missing")
        if raw is None:
            return []
        if isinstance(raw, dict):
            for key in ("data", "orders", "result"):
                block = raw.get(key)
                if isinstance(block, list):
                    return [dict(x) for x in block if isinstance(x, dict)]
            return []
        if isinstance(raw, list):
            return [dict(x) for x in raw if isinstance(x, dict)]
        return []

    def _fetch_broker_positions(self, broker_api: Any) -> list[dict[str, Any]]:
        if not hasattr(broker_api, "positions") or not callable(broker_api.positions):
            return []
        raw = broker_api.positions()
        if raw is None:
            return []
        if isinstance(raw, list):
            return [dict(x) for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict):
            out: list[dict[str, Any]] = []
            for key in ("net", "day", "data", "positions"):
                block = raw.get(key)
                if isinstance(block, list):
                    out.extend(dict(x) for x in block if isinstance(x, dict))
            return out
        return []

    @staticmethod
    def _positions_open(positions: list[dict[str, Any]]) -> bool:
        for row in positions:
            qty = _as_float(
                row.get("quantity")
                if row.get("quantity") is not None
                else row.get("net_quantity"),
                0.0,
            )
            if abs(qty) > 1e-9:
                return True
        return False

    @staticmethod
    def _find_transition_path(current: OrderState, target: OrderState) -> list[OrderState]:
        if current == target:
            return []
        queue: list[tuple[OrderState, list[OrderState]]] = [(current, [])]
        visited = {current}
        while queue:
            node, path = queue.pop(0)
            for nxt in OrderStateMachine.valid_next_states(node):
                if nxt in visited:
                    continue
                next_path = path + [nxt]
                if nxt == target:
                    return next_path
                visited.add(nxt)
                queue.append((nxt, next_path))
        raise OrderStateTransitionError(current, target)

    def _move_to_state(
        self,
        record: OrderRecord,
        target_state: OrderState,
        *,
        reason: str,
        broker_order_id: str | None = None,
        filled_qty: float | None = None,
    ) -> OrderRecord:
        current = record
        if current.state == target_state:
            if filled_qty is not None and abs(float(current.filled_qty) - float(filled_qty)) > 1e-9:
                return self._sm.set_filled_quantity(
                    order_id=current.order_id,
                    filled_qty=float(filled_qty),
                    reason=f"{reason}:fill_qty_sync",
                )
            return current
        path = self._find_transition_path(current.state, target_state)
        for idx, step_state in enumerate(path):
            is_last = idx == (len(path) - 1)
            step_reason = reason if is_last else f"{reason}:bridge_{step_state.value.lower()}"
            current = self._sm.transition(
                order_id=current.order_id,
                next_state=step_state,
                reason=step_reason,
                broker_order_id=broker_order_id if is_last else None,
                filled_qty=filled_qty if is_last else None,
            )
        return current

    def run_cycle_once(self) -> ReconciliationCycleResult:
        started = time.time()
        corrections = 0
        errors = 0

        try:
            broker_api = self._resolve_broker_api()
            broker_orders = self._with_retry(lambda: self._fetch_broker_orders(broker_api), "broker_orders")
            broker_positions = self._with_retry(lambda: self._fetch_broker_positions(broker_api), "broker_positions")
        except Exception as exc:
            self._write_log(
                "reconcile_snapshot_failed",
                {"error": f"{type(exc).__name__}:{exc}"},
                level="ERROR",
            )
            ended = time.time()
            with self._state_lock:
                self._last_cycle_ts_epoch = ended
            return ReconciliationCycleResult(
                scanned_orders=0,
                corrections=0,
                errors=1,
                broker_open_orders=0,
                broker_positions=0,
                started_at=started,
                ended_at=ended,
            )

        broker_by_id: dict[str, dict[str, Any]] = {}
        open_count = 0
        for row in broker_orders:
            oid = _broker_order_id(row)
            if oid:
                broker_by_id[oid] = row
            if _status_text(row.get("status")) in _OPEN_STATUSES:
                open_count += 1

        internal_orders = self._sm.list_orders(include_terminal=False, limit=self._scan_limit)
        has_open_positions = self._positions_open(broker_positions)

        for internal in internal_orders:
            try:
                candidate_ids = []
                if internal.broker_order_id:
                    candidate_ids.append(str(internal.broker_order_id))
                candidate_ids.append(str(internal.order_id))
                broker_row = None
                for cid in candidate_ids:
                    if cid in broker_by_id:
                        broker_row = broker_by_id[cid]
                        break

                if broker_row is None:
                    if internal.state in {OrderState.ACKNOWLEDGED, OrderState.PARTIAL} and has_open_positions:
                        self._write_log(
                            "reconcile_mark_unknown",
                            {
                                "order_id": internal.order_id,
                                "broker_order_id": internal.broker_order_id,
                                "state": internal.state.value,
                                "reason": "missing_broker_order_with_open_positions",
                            },
                            level="WARN",
                        )
                        corrections += 1
                        continue
                    repaired = self._move_to_state(
                        internal,
                        OrderState.REJECTED,
                        reason="reconcile_missing_broker_order",
                    )
                    self._write_log(
                        "reconcile_mark_rejected",
                        {
                            "order_id": repaired.order_id,
                            "previous_state": internal.state.value,
                            "new_state": repaired.state.value,
                            "reason": "missing_broker_order",
                        },
                        level="WARN",
                    )
                    corrections += 1
                    continue

                target_state = _target_state_from_broker(broker_row)
                broker_fill_qty = _broker_filled_qty(broker_row)
                broker_order_id = _broker_order_id(broker_row) or internal.broker_order_id

                working = internal
                if target_state is not None:
                    prev_state = working.state
                    prev_filled_qty = working.filled_qty
                    working = self._move_to_state(
                        working,
                        target_state,
                        reason="reconcile_broker_status_sync",
                        broker_order_id=broker_order_id,
                        filled_qty=broker_fill_qty if target_state in {OrderState.PARTIAL, OrderState.FILLED} else None,
                    )
                    if working.state != prev_state or abs(float(working.filled_qty) - float(prev_filled_qty)) > 1e-9:
                        corrections += 1
                        self._write_log(
                            "reconcile_state_sync",
                            {
                                "order_id": working.order_id,
                                "broker_order_id": broker_order_id,
                                "previous_state": prev_state.value,
                                "new_state": working.state.value,
                                "previous_filled_qty": prev_filled_qty,
                                "new_filled_qty": working.filled_qty,
                                "broker_status": _status_text(broker_row.get("status")),
                            },
                            level="INFO",
                        )

                if broker_fill_qty >= 0 and abs(float(working.filled_qty) - float(broker_fill_qty)) > 1e-9:
                    updated = self._sm.set_filled_quantity(
                        order_id=working.order_id,
                        filled_qty=broker_fill_qty,
                        reason="reconcile_fill_qty_sync",
                    )
                    corrections += 1
                    self._write_log(
                        "reconcile_fill_qty_sync",
                        {
                            "order_id": updated.order_id,
                            "broker_order_id": broker_order_id,
                            "previous_filled_qty": working.filled_qty,
                            "new_filled_qty": updated.filled_qty,
                        },
                        level="INFO",
                    )
            except Exception as exc:
                errors += 1
                self._write_log(
                    "reconcile_order_error",
                    {
                        "order_id": internal.order_id,
                        "state": internal.state.value,
                        "error": f"{type(exc).__name__}:{exc}",
                    },
                    level="ERROR",
                )

        ended = time.time()
        summary = ReconciliationCycleResult(
            scanned_orders=len(internal_orders),
            corrections=corrections,
            errors=errors,
            broker_open_orders=open_count,
            broker_positions=len(broker_positions),
            started_at=started,
            ended_at=ended,
        )
        self._write_log(
            "reconcile_cycle_summary",
            {
                "scanned_orders": summary.scanned_orders,
                "corrections": summary.corrections,
                "errors": summary.errors,
                "broker_open_orders": summary.broker_open_orders,
                "broker_positions": summary.broker_positions,
                "duration_sec": round(summary.ended_at - summary.started_at, 6),
            },
            level="INFO" if errors == 0 else "WARN",
        )
        with self._state_lock:
            self._last_cycle_ts_epoch = summary.ended_at
        return summary

    def _write_log(self, event: str, payload: dict[str, Any], *, level: str) -> None:
        if self._stop_event.is_set():
            return
        record = {
            "ts_epoch": time.time(),
            "event": str(event),
            "level": str(level).upper(),
            "interval_sec": self._interval_sec,
        }
        record.update(payload or {})
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        except Exception:
            pass


def stop_reconciliation_daemon(timeout_sec: float = 5.0) -> bool:
    """
    Best-effort module-level stop for all instantiated reconciliation daemons.

    This is intentionally idempotent and safe to call during partial teardown.
    """
    timeout_value = max(0.0, float(timeout_sec))
    with _DAEMON_REGISTRY_LOCK:
        daemons = list(_DAEMON_REGISTRY)
    clean = True
    for daemon in daemons:
        try:
            clean = bool(daemon.stop(timeout_sec=timeout_value)) and clean
        except Exception:
            clean = False
    return clean
