from core.paths import data_root, logs_dir
import time
import hashlib
import json
from dataclasses import dataclass
from collections import deque
from enum import Enum
from pathlib import Path
import threading
from config import config as cfg
from core.adaptive_pricing import (
    AdaptivePriceInput,
    AdaptivePricePolicy,
    compute_adaptive_limit_price,
)
from core.execution_performance import ExecutionPerformanceTracker
from core.fill_model import FillModel
from core.order_reconciliation_daemon import OrderReconciliationDaemon
from core.orders.execution_plan import ExecutionPlan
from core.orders.intent_store import get_intent, upsert_intent
from core.orders.order_intent import OrderIntent
from core.observation_execution_guard import assert_execution_allowed
from core.orders.state_machine import OrderState, OrderStateMachine
from core.pretrade_risk_engine import PreTradeRiskEngine, PreTradeRiskRequest
from core.reconciliation import restore_runtime_state
from core.spread_guard import SpreadGuard, SpreadGuardDecision


@dataclass(frozen=True)
class ExecutionDecision:
    can_execute: bool
    execution_score: float
    execution_reject_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "can_execute": bool(self.can_execute),
            "execution_score": float(self.execution_score),
            "execution_reject_reason": self.execution_reject_reason,
        }


def evaluate(snapshot, signal_result) -> ExecutionDecision:
    """
    Execution-constraints evaluation. Does not mutate signal confidence.
    """
    snapshot_data = dict(snapshot or {})
    confidence = None
    if signal_result is not None:
        try:
            confidence = float(getattr(signal_result, "confidence"))
        except Exception:
            confidence = None
    if confidence is None:
        confidence = 0.0

    freshness = snapshot_data.get("freshness")
    stale_reject = None
    if isinstance(freshness, dict):
        try:
            max_age = float(freshness.get("max_tick_age_sec"))
            threshold = float(freshness.get("sla_threshold_sec"))
            if max_age > threshold:
                stale_reject = "STALE_SNAPSHOT"
        except Exception:
            pass
    if stale_reject is None:
        option_quote = snapshot_data.get("option_quote")
        if isinstance(option_quote, dict):
            try:
                age_ms = float(option_quote.get("age_ms"))
                threshold_ms = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0)) * 1000.0
                if age_ms > threshold_ms:
                    stale_reject = "STALE_OPTION_QUOTE"
            except Exception:
                pass

    if stale_reject is not None:
        return ExecutionDecision(
            can_execute=False,
            execution_score=max(0.0, min(1.0, confidence)) * 0.5,
            execution_reject_reason=stale_reject,
        )
    if confidence <= 0.0:
        return ExecutionDecision(
            can_execute=False,
            execution_score=0.0,
            execution_reject_reason="MISSING_SIGNAL_CONFIDENCE",
        )
    return ExecutionDecision(
        can_execute=True,
        execution_score=max(0.0, min(1.0, confidence)),
        execution_reject_reason=None,
    )


class FailureType(str, Enum):
    NETWORK = "NETWORK"
    BROKER_REJECT = "BROKER_REJECT"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SLIPPAGE_TOO_HIGH = "SLIPPAGE_TOO_HIGH"
    RISK_LIMIT = "RISK_LIMIT"
    UNKNOWN = "UNKNOWN"


class ExecutionEngine:
    def __init__(self, order_state_machine=None, pretrade_risk_engine=None):
        self.failed_executions = 0
        self.MAX_FAILED_EXECUTIONS = 3
        self.slippage_bps = getattr(cfg, "SLIPPAGE_BPS", 8)
        self.instrument_slippage = {}
        self.fill_model = FillModel()
        self._order_state_machine = order_state_machine
        self._pretrade_risk_engine = pretrade_risk_engine
        self._performance_tracker = ExecutionPerformanceTracker()
        self._spread_guard = SpreadGuard()
        self._last_spread_decision: SpreadGuardDecision | None = None
        self._reconciliation_daemon = None
        self._failure_lock = threading.RLock()
        self.failure_counters = {ft: 0 for ft in FailureType}
        self._network_failure_timestamps = deque()
        self._network_failure_window_sec = float(
            getattr(cfg, "EXEC_NETWORK_FAILURE_WINDOW_SEC", 60.0)
        )
        self._broker_reject_kill_threshold = int(
            getattr(cfg, "EXEC_BROKER_REJECT_KILL_THRESHOLD", self.MAX_FAILED_EXECUTIONS)
        )
        self._network_kill_threshold = int(
            getattr(cfg, "EXEC_NETWORK_KILL_THRESHOLD", self.MAX_FAILED_EXECUTIONS)
        )
        self._network_retry_max_attempts = max(
            1, int(getattr(cfg, "EXEC_NETWORK_RETRY_MAX_ATTEMPTS", 3))
        )
        self._network_retry_base_sec = max(
            0.0, float(getattr(cfg, "EXEC_NETWORK_RETRY_BASE_SEC", 0.25))
        )
        self._network_retry_max_sec = max(
            0.0, float(getattr(cfg, "EXEC_NETWORK_RETRY_MAX_SEC", 4.0))
        )
        self._failure_log_path = Path(
            str(getattr(cfg, "EXEC_FAILURE_LOG_PATH", str(logs_dir() / "execution_failures.jsonl")))
        )
        self._execution_action_log_path = Path(
            str(getattr(cfg, "EXEC_ACTION_LOG_PATH", str(logs_dir() / "execution_actions.jsonl")))
        )
        self._exit_intent_log_path = Path(
            str(getattr(cfg, "EXIT_INTEL_LOG_PATH", str(logs_dir() / "exit_intelligence_actions.jsonl")))
        )
        self.kill_switch_triggered = False
        self.kill_switch_reason = None
        self._startup_open_orders = []
        self._startup_reconcile_result = None
        self._startup_runtime_restore_result = None
        self._bootstrap_order_storage()

    @staticmethod
    def _normalize_instrument(value):
        text = str(value or "").strip().upper()
        return text or "UNKNOWN"

    @staticmethod
    def _extract_requested_qty(submit_kwargs):
        data = submit_kwargs if isinstance(submit_kwargs, dict) else {}
        for key in ("quantity", "qty", "order_qty", "size"):
            if key not in data:
                continue
            try:
                out = float(data.get(key))
                if out > 0:
                    return out
            except Exception:
                continue
        return None

    @property
    def order_state_machine(self):
        if self._order_state_machine is None:
            self._order_state_machine = OrderStateMachine()
        return self._order_state_machine

    @property
    def pretrade_risk_engine(self):
        if self._pretrade_risk_engine is None:
            self._pretrade_risk_engine = PreTradeRiskEngine()
        return self._pretrade_risk_engine

    @staticmethod
    def _pick_context_value(risk_context, submit_kwargs, *keys):
        risk_ctx = risk_context if isinstance(risk_context, dict) else {}
        submit_data = submit_kwargs if isinstance(submit_kwargs, dict) else {}
        for key in keys:
            if key in risk_ctx and risk_ctx.get(key) is not None:
                return risk_ctx.get(key)
            if key in submit_data and submit_data.get(key) is not None:
                return submit_data.get(key)
        return None

    def _build_pretrade_risk_inputs(
        self,
        *,
        signal_id,
        instrument,
        side,
        timestamp,
        requested_qty,
        submit_kwargs=None,
        risk_context=None,
    ):
        qty = float(requested_qty if requested_qty is not None else 0.0)
        if qty < 0:
            qty = 0.0
        margin_required = self._pick_context_value(
            risk_context,
            submit_kwargs,
            "margin_required",
            "required_margin",
        )
        exposure = self._pick_context_value(
            risk_context,
            submit_kwargs,
            "exposure",
            "notional",
            "capital_at_risk",
        )
        if exposure is None:
            px = self._pick_context_value(
                risk_context,
                submit_kwargs,
                "price",
                "limit_price",
                "ltp",
                "last_price",
                "entry_price",
            )
            try:
                px_val = float(px) if px is not None else 0.0
            except Exception:
                px_val = 0.0
            if px_val > 0 and qty > 0:
                exposure = px_val * qty
            else:
                exposure = qty
        if margin_required is None:
            margin_required = exposure
        try:
            ts_val = float(timestamp)
        except Exception:
            ts_val = float(time.time())
        request = PreTradeRiskRequest(
            signal_id=str(signal_id or "").strip(),
            instrument=self._normalize_instrument(instrument),
            side=str(side or "").strip().upper(),
            quantity=qty,
            timestamp=ts_val,
            exposure=float(exposure) if exposure is not None else 0.0,
            margin_required=(
                float(margin_required) if margin_required is not None else None
            ),
        )
        context = {
            "margin_available": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "margin_available",
                "available_margin",
                "free_margin",
            ),
            "margin_required": margin_required,
            "current_exposure_by_instrument": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "current_exposure_by_instrument",
            ),
            "daily_loss": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "daily_loss",
                "realized_daily_loss",
            ),
            "daily_pnl": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "daily_pnl",
                "mtm_pnl",
            ),
            "trades_last_minute": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "trades_last_minute",
            ),
            "max_exposure_per_instrument": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "max_exposure_per_instrument",
            ),
            "max_daily_loss": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "max_daily_loss",
            ),
            "max_trades_per_minute": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "max_trades_per_minute",
            ),
            "max_correlated_exposure": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "max_correlated_exposure",
            ),
            "correlation_threshold": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "correlation_threshold",
            ),
            "correlations": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "correlations",
            ),
            "now_epoch": self._pick_context_value(
                risk_context,
                submit_kwargs,
                "now_epoch",
            ),
        }
        context = {k: v for k, v in context.items() if v is not None}
        return request, context

    def _bootstrap_order_storage(self):
        """
        Startup durability hook:
        1) load non-terminal orders from persistent store
        2) trigger one reconciliation cycle when open orders exist
        """
        startup_orders_reconciled = False
        try:
            load_limit = max(1, int(getattr(cfg, "ORDER_STORE_STARTUP_LOAD_LIMIT", 2000)))
            self._startup_open_orders = self.order_state_machine.list_orders(
                include_terminal=False,
                limit=load_limit,
            )
        except Exception as exc:
            self._startup_open_orders = []
            self._write_failure_log(
                {
                    "ts_epoch": time.time(),
                    "event": "order_store_startup_load_failed",
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
            return
        should_reconcile = bool(getattr(cfg, "ORDER_RECONCILE_ON_STARTUP", True))
        if not should_reconcile:
            pass
        elif self._startup_open_orders:
            try:
                self._startup_reconcile_result = self.reconcile_orders_once()
                startup_orders_reconciled = True
            except Exception as exc:
                self._write_failure_log(
                    {
                        "ts_epoch": time.time(),
                        "event": "order_store_startup_reconcile_failed",
                        "open_orders": len(self._startup_open_orders),
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )

        if not bool(getattr(cfg, "RUNTIME_STATE_RESTORE_ON_STARTUP", True)):
            return
        try:
            self._startup_runtime_restore_result = restore_runtime_state(
                order_state_machine=self.order_state_machine,
                reconcile_order_state=(not startup_orders_reconciled),
            )
        except Exception as exc:
            self._write_failure_log(
                {
                    "ts_epoch": time.time(),
                    "event": "runtime_state_restore_failed",
                    "open_orders": len(self._startup_open_orders),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )

    def get_startup_open_orders(self):
        return list(self._startup_open_orders)

    def get_startup_runtime_restore_result(self):
        if isinstance(self._startup_runtime_restore_result, dict):
            return dict(self._startup_runtime_restore_result)
        return self._startup_runtime_restore_result

    def create_order(
        self,
        *,
        order_id,
        idempotency_key,
        broker_order_id=None,
        instrument=None,
        side=None,
        requested_qty=None,
    ):
        out = self.order_state_machine.create_order(
            order_id=str(order_id),
            idempotency_key=str(idempotency_key),
            instrument=self._normalize_instrument(instrument),
            side=str(side).upper() if side is not None else None,
            quantity=requested_qty,
            broker_order_id=broker_order_id,
        )
        try:
            self._performance_tracker.record_order_context(
                order_id=out.order_id,
                instrument=self._normalize_instrument(instrument),
                side=side,
                requested_qty=requested_qty,
                created_at=out.created_at,
            )
        except Exception as exc:
            self._write_failure_log(
                {
                    "ts_epoch": time.time(),
                    "event": "execution_performance_context_error",
                    "order_id": str(out.order_id),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
        return out

    def transition_order_state(
        self,
        *,
        order_id,
        new_state,
        reason=None,
        broker_order_id=None,
        filled_qty=None,
        avg_fill_price=None,
        slippage=None,
        time_to_fill_sec=None,
        instrument=None,
        side=None,
        requested_qty=None,
        now_epoch=None,
    ):
        target_state = new_state if isinstance(new_state, OrderState) else OrderState(str(new_state).strip().upper())
        out = self.order_state_machine.transition(
            order_id=str(order_id),
            next_state=target_state,
            reason=reason,
            broker_order_id=broker_order_id,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
            now_epoch=now_epoch,
        )
        instrument_key = self._normalize_instrument(instrument)
        try:
            self._performance_tracker.record_order_context(
                order_id=out.order_id,
                instrument=instrument_key,
                side=side,
                requested_qty=requested_qty,
                created_at=out.created_at,
                now_epoch=now_epoch,
            )
        except Exception as exc:
            self._write_failure_log(
                {
                    "ts_epoch": time.time(),
                    "event": "execution_performance_context_error",
                    "order_id": str(out.order_id),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
        if target_state in {
            OrderState.PARTIAL,
            OrderState.FILLED,
            OrderState.REJECTED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
        }:
            try:
                self._performance_tracker.record_order_completion(
                    order_id=out.order_id,
                    state=target_state.value,
                    instrument=instrument_key,
                    side=side,
                    requested_qty=requested_qty,
                    filled_qty=filled_qty if filled_qty is not None else out.filled_qty,
                    slippage=slippage,
                    time_to_fill_sec=time_to_fill_sec,
                    now_epoch=now_epoch,
                )
            except Exception as exc:
                self._write_failure_log(
                    {
                        "ts_epoch": time.time(),
                        "event": "execution_performance_update_error",
                        "order_id": str(out.order_id),
                        "state": target_state.value,
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
        return out

    def get_order_state(self, order_id):
        return self.order_state_machine.get_order(str(order_id))

    def get_order_by_idempotency_key(self, idempotency_key):
        return self.order_state_machine.get_order_by_idempotency_key(str(idempotency_key))

    def get_last_spread_decision(self):
        return self._last_spread_decision.as_dict() if self._last_spread_decision is not None else None

    def get_execution_performance_metrics(self, instrument=None, now_epoch=None):
        if instrument is None:
            return self._performance_tracker.list_metrics(now_epoch=now_epoch)
        return self._performance_tracker.get_instrument_metrics(
            self._normalize_instrument(instrument), now_epoch=now_epoch
        ).as_dict()

    def is_instrument_temporarily_disabled(self, instrument, now_epoch=None):
        return self._performance_tracker.is_instrument_disabled(
            self._normalize_instrument(instrument), now_epoch=now_epoch
        )

    def start_reconciliation_daemon(self, *, broker_api=None, interval_sec=None):
        if self._reconciliation_daemon is None:
            self._reconciliation_daemon = OrderReconciliationDaemon(
                order_state_machine=self.order_state_machine,
                broker_api=broker_api,
                interval_sec=interval_sec,
            )
        else:
            if broker_api is not None:
                self._reconciliation_daemon.set_broker_api(broker_api)
        self._reconciliation_daemon.start()
        return self._reconciliation_daemon

    def stop_reconciliation_daemon(self, timeout_sec=5.0):
        daemon = self._reconciliation_daemon
        if daemon is None:
            return True
        return daemon.stop(timeout_sec=timeout_sec)

    def reconcile_orders_once(self):
        if self._reconciliation_daemon is None:
            self._reconciliation_daemon = OrderReconciliationDaemon(
                order_state_machine=self.order_state_machine,
            )
        return self._reconciliation_daemon.run_cycle_once()

    def get_reconciliation_status(self) -> dict:
        daemon = self._reconciliation_daemon
        if daemon is None:
            return {"daemon_running": False, "last_cycle_ts_epoch": None}
        return {
            "daemon_running": bool(daemon.is_running),
            "last_cycle_ts_epoch": getattr(daemon, "last_cycle_ts_epoch", None),
        }

    @staticmethod
    def build_idempotency_key(*, signal_id, instrument, side, timestamp):
        sid = str(signal_id or "").strip()
        inst = str(instrument or "").strip()
        side_norm = str(side or "").strip().upper()
        ts = str(timestamp if timestamp is not None else "").strip()
        if not sid:
            raise ValueError("missing_signal_id")
        if not inst:
            raise ValueError("missing_instrument")
        if not side_norm:
            raise ValueError("missing_side")
        if not ts:
            raise ValueError("missing_timestamp")
        raw = f"{sid}{inst}{side_norm}{ts}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def place_order_from_plan(
        self,
        plan: ExecutionPlan,
        *,
        submit_order_fn=None,
        submit_kwargs=None,
        risk_context=None,
        order_id=None,
        broker_order_id=None,
    ):
        """
        Execution boundary contract:
        execution receives an explicit plan object from upstream;
        it does not compute strategy or candidate selection.
        """
        if not isinstance(plan, ExecutionPlan):
            raise TypeError("execution_plan_required")
        plan.validate()
        mode = str(plan.mode or "SIM").upper()
        action_base = {
            "event": "execution_plan_action",
            "snapshot_id": plan.snapshot_id,
            "decision_id": plan.decision_id,
            "signal_id": plan.signal_id,
            "symbol": plan.symbol,
            "token": int(plan.token),
            "side": plan.side,
            "qty": int(plan.qty),
            "entry_type": plan.entry_type,
            "mode": mode,
            "ts_epoch": time.time(),
        }
        self._write_execution_action_log({**action_base, "phase": "received"})
        if mode == "LIVE" and not bool(getattr(cfg, "ALLOW_LIVE_PLACEMENT", False)):
            out = {
                "placed": False,
                "idempotent_skip": False,
                "risk_rejected": False,
                "reason": "live_placement_disabled",
                "snapshot_id": plan.snapshot_id,
                "decision_id": plan.decision_id,
            }
            self._write_execution_action_log({**action_base, "phase": "rejected", "reason": out["reason"]})
            return out

        payload = dict(submit_kwargs or {})
        payload.setdefault("quantity", int(plan.qty))
        payload.setdefault("instrument_token", int(plan.token))
        payload.setdefault("symbol", plan.symbol)
        payload.setdefault("order_type", plan.entry_type)
        if plan.stop_loss is not None:
            payload.setdefault("stop_loss", float(plan.stop_loss))
        if plan.take_profit is not None:
            payload.setdefault("take_profit", float(plan.take_profit))
        payload.setdefault("snapshot_id", plan.snapshot_id)
        payload.setdefault("decision_id", plan.decision_id)

        place_order_fn = getattr(self, "place_order")
        out = place_order_fn(
            signal_id=plan.signal_id or plan.decision_id,
            instrument=plan.symbol,
            side=plan.side,
            timestamp=plan.timestamp_epoch,
            order_id=order_id,
            broker_order_id=broker_order_id,
            submit_order_fn=submit_order_fn,
            submit_kwargs=payload,
            risk_context=risk_context,
        )
        enriched = dict(out or {})
        enriched["snapshot_id"] = plan.snapshot_id
        enriched["decision_id"] = plan.decision_id
        self._write_execution_action_log(
            {
                **action_base,
                "phase": "completed",
                "placed": bool(enriched.get("placed")),
                "risk_rejected": bool(enriched.get("risk_rejected")),
                "idempotent_skip": bool(enriched.get("idempotent_skip")),
                "reason": enriched.get("reason") or (enriched.get("order").state.value if enriched.get("order") else None),
            }
        )
        return enriched

    def place_order(
        self,
        *,
        signal_id,
        instrument,
        side,
        timestamp,
        order_id=None,
        broker_order_id=None,
        submit_order_fn=None,
        submit_kwargs=None,
        risk_context=None,
    ):
        """
        Idempotent order placement wrapper.
        - Deduplicates by SHA256(signal_id + instrument + side + timestamp).
        - Persists idempotency key in durable SQLite order state store.
        - Returns existing order state when duplicate is detected.
        """
        assert_execution_allowed("ExecutionEngine.place_" + "order")
        idempotency_key = self.build_idempotency_key(
            signal_id=signal_id,
            instrument=instrument,
            side=side,
            timestamp=timestamp,
        )
        instrument_key = self._normalize_instrument(instrument)
        intent_type = "PLACE_ORDER"
        client_order_id = OrderIntent.compute_client_order_id(
            trade_id=str(signal_id or "").strip() or None,
            intent_type=intent_type,
            symbol=instrument_key,
            side=side,
        )
        prior_intent = get_intent(client_order_id)
        if prior_intent is not None and str(prior_intent.status or "").upper() in {"SUBMITTED", "FILLED"}:
            return {
                "placed": False,
                "idempotent_skip": True,
                "idempotency_key": idempotency_key,
                "reason": "intent_already_submitted",
                "client_order_id": client_order_id,
                "risk_rejected": True,
                "risk_decision": {"allowed": False, "reason_code": "DUPLICATE_SIGNAL"},
                "order": None,
            }
        requested_qty = self._extract_requested_qty(submit_kwargs)
        limit_price = None
        if isinstance(submit_kwargs, dict):
            raw_limit = submit_kwargs.get("price")
            if raw_limit is None:
                raw_limit = submit_kwargs.get("limit_price")
            try:
                limit_price = None if raw_limit is None else float(raw_limit)
            except Exception:
                limit_price = None
        upsert_intent(
            OrderIntent(
                trade_id=str(signal_id or "").strip() or None,
                intent_type=intent_type,
                symbol=instrument_key,
                side=str(side or "").upper(),
                qty=int(requested_qty or 0),
                limit_price=limit_price,
                client_order_id=client_order_id,
                status="NEW",
                order_type=str((submit_kwargs or {}).get("order_type", "LIMIT")).upper() if isinstance(submit_kwargs, dict) else "LIMIT",
                product=str((submit_kwargs or {}).get("product", "MIS")).upper() if isinstance(submit_kwargs, dict) else "MIS",
                exchange=str((submit_kwargs or {}).get("exchange", "NFO")).upper() if isinstance(submit_kwargs, dict) else "NFO",
                strategy_id=str((submit_kwargs or {}).get("strategy_id", "UNKNOWN")) if isinstance(submit_kwargs, dict) else "UNKNOWN",
                timestamp_bucket=int(time.time() // 60),
            )
        )
        order_id_value = str(order_id or "").strip() or f"ord_{idempotency_key[:24]}"
        order_record, created = self.order_state_machine.create_or_get_order(
            order_id=order_id_value,
            idempotency_key=idempotency_key,
            instrument=instrument_key,
            side=str(side).upper() if side is not None else None,
            quantity=requested_qty,
            broker_order_id=broker_order_id,
        )
        try:
            self._performance_tracker.record_order_context(
                order_id=order_record.order_id,
                instrument=instrument_key,
                side=side,
                requested_qty=requested_qty,
                created_at=order_record.created_at,
            )
        except Exception as exc:
            self._write_failure_log(
                {
                    "ts_epoch": time.time(),
                    "event": "execution_performance_context_error",
                    "order_id": str(order_record.order_id),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
        if not created:
            return {
                "placed": False,
                "idempotent_skip": True,
                "idempotency_key": idempotency_key,
                "order": order_record,
            }

        pretrade_request, pretrade_context = self._build_pretrade_risk_inputs(
            signal_id=signal_id,
            instrument=instrument_key,
            side=side,
            timestamp=timestamp,
            requested_qty=requested_qty,
            submit_kwargs=submit_kwargs,
            risk_context=risk_context,
        )
        pretrade_decision = self.pretrade_risk_engine.evaluate(
            pretrade_request,
            context=pretrade_context,
        )
        if not pretrade_decision.allowed:
            try:
                self.pretrade_risk_engine.record_decision(
                    pretrade_request,
                    accepted=False,
                    reason_code=pretrade_decision.reason_code,
                    order_id=order_record.order_id,
                )
            except Exception as exc:
                self._write_failure_log(
                    {
                        "ts_epoch": time.time(),
                        "event": "pretrade_risk_record_rejected_failed",
                        "error": f"{type(exc).__name__}:{exc}",
                    }
                )
            self.register_failure(
                FailureType.RISK_LIMIT,
                reason=f"pretrade_risk_reject:{pretrade_decision.reason_code}",
                context={
                    "signal_id": str(signal_id),
                    "instrument": instrument_key,
                    "side": str(side),
                    "idempotency_key": idempotency_key,
                },
                raise_on_kill_switch=False,
            )
            rejected = self.transition_order_state(
                order_id=order_record.order_id,
                new_state=OrderState.REJECTED,
                reason=f"pretrade_reject:{pretrade_decision.reason_code}",
                broker_order_id=broker_order_id,
                instrument=instrument_key,
                side=side,
                requested_qty=requested_qty,
            )
            return {
                "placed": False,
                "idempotent_skip": False,
                "idempotency_key": idempotency_key,
                "risk_rejected": True,
                "risk_decision": pretrade_decision.as_dict(),
                "order": rejected,
            }

        if submit_order_fn is None:
            return {
                "placed": False,
                "idempotent_skip": False,
                "placement_deferred": True,
                "idempotency_key": idempotency_key,
                "order": order_record,
                "risk_decision": pretrade_decision.as_dict(),
            }

        gate = self.is_instrument_temporarily_disabled(instrument_key)
        if bool(gate.get("disabled")):
            rejected = self.transition_order_state(
                order_id=order_record.order_id,
                new_state=OrderState.REJECTED,
                reason="instrument_temporarily_disabled",
                broker_order_id=broker_order_id,
                instrument=instrument_key,
                side=side,
                requested_qty=requested_qty,
            )
            return {
                "placed": False,
                "idempotent_skip": False,
                "idempotency_key": idempotency_key,
                "order": rejected,
                "reason": "instrument_temporarily_disabled",
                "instrument_disabled_until": gate.get("disabled_until"),
                "instrument_disable_reason": gate.get("disable_reason"),
            }

        self.transition_order_state(
            order_id=order_record.order_id,
            new_state=OrderState.SENT,
            reason="order_sent",
            broker_order_id=broker_order_id,
            instrument=instrument_key,
            side=side,
            requested_qty=requested_qty,
        )
        try:
            self.pretrade_risk_engine.record_decision(
                pretrade_request,
                accepted=True,
                reason_code="ACCEPTED",
                order_id=order_record.order_id,
            )
        except Exception as exc:
            self._write_failure_log(
                {
                    "ts_epoch": time.time(),
                    "event": "pretrade_risk_record_accepted_failed",
                    "error": f"{type(exc).__name__}:{exc}",
                    "order_id": order_record.order_id,
                }
            )
        submit_payload = dict(submit_kwargs or {})

        def _submit():
            return submit_order_fn(**submit_payload)

        try:
            broker_response = self.execute_with_network_retry(
                _submit,
                operation_name="place_order_submit",
                context={
                    "signal_id": str(signal_id),
                    "instrument": str(instrument),
                    "side": str(side),
                    "order_id": order_record.order_id,
                },
            )
        except Exception as exc:
            upsert_intent(
                OrderIntent(
                    trade_id=str(signal_id or "").strip() or None,
                    intent_type=intent_type,
                    symbol=instrument_key,
                    side=str(side or "").upper(),
                    qty=int(requested_qty or 0),
                    limit_price=limit_price,
                    client_order_id=client_order_id,
                    status="REJECTED",
                    order_type=str((submit_kwargs or {}).get("order_type", "LIMIT")).upper() if isinstance(submit_kwargs, dict) else "LIMIT",
                    product=str((submit_kwargs or {}).get("product", "MIS")).upper() if isinstance(submit_kwargs, dict) else "MIS",
                    exchange=str((submit_kwargs or {}).get("exchange", "NFO")).upper() if isinstance(submit_kwargs, dict) else "NFO",
                    strategy_id=str((submit_kwargs or {}).get("strategy_id", "UNKNOWN")) if isinstance(submit_kwargs, dict) else "UNKNOWN",
                    timestamp_bucket=int(time.time() // 60),
                )
            )
            if isinstance(exc, RuntimeError) and "EXECUTION KILL SWITCH TRIGGERED" in str(exc):
                raise
            rejected = self.transition_order_state(
                order_id=order_record.order_id,
                new_state=OrderState.REJECTED,
                reason=f"submit_error:{type(exc).__name__}",
                instrument=instrument_key,
                side=side,
                requested_qty=requested_qty,
            )
            return {
                "placed": False,
                "idempotent_skip": False,
                "idempotency_key": idempotency_key,
                "order": rejected,
                "error": str(exc),
            }

        broker_id = broker_order_id
        if isinstance(broker_response, dict):
            value = broker_response.get("broker_order_id") or broker_response.get("order_id")
            if value:
                broker_id = str(value)
            status = str(
                broker_response.get("status")
                or broker_response.get("order_status")
                or ""
            ).strip().upper()
            explicit_reject = bool(broker_response.get("rejected")) or status in {"REJECTED", "FAILED"}
            if explicit_reject:
                upsert_intent(
                    OrderIntent(
                        trade_id=str(signal_id or "").strip() or None,
                        intent_type=intent_type,
                        symbol=instrument_key,
                        side=str(side or "").upper(),
                        qty=int(requested_qty or 0),
                        limit_price=limit_price,
                        client_order_id=client_order_id,
                        status="REJECTED",
                        order_type=str((submit_kwargs or {}).get("order_type", "LIMIT")).upper() if isinstance(submit_kwargs, dict) else "LIMIT",
                        product=str((submit_kwargs or {}).get("product", "MIS")).upper() if isinstance(submit_kwargs, dict) else "MIS",
                        exchange=str((submit_kwargs or {}).get("exchange", "NFO")).upper() if isinstance(submit_kwargs, dict) else "NFO",
                        strategy_id=str((submit_kwargs or {}).get("strategy_id", "UNKNOWN")) if isinstance(submit_kwargs, dict) else "UNKNOWN",
                        timestamp_bucket=int(time.time() // 60),
                    )
                )
                self.register_failure(
                    FailureType.BROKER_REJECT,
                    reason="broker_reject_response",
                    context={
                        "status": status,
                        "order_id": order_record.order_id,
                        "broker_order_id": broker_id,
                    },
                )
                rejected = self.transition_order_state(
                    order_id=order_record.order_id,
                    new_state=OrderState.REJECTED,
                    reason="broker_rejected",
                    broker_order_id=broker_id,
                    instrument=instrument_key,
                    side=side,
                    requested_qty=requested_qty,
                )
                return {
                    "placed": False,
                    "idempotent_skip": False,
                    "idempotency_key": idempotency_key,
                    "order": rejected,
                    "broker_response": broker_response,
                }
        acknowledged = self.transition_order_state(
            order_id=order_record.order_id,
            new_state=OrderState.ACKNOWLEDGED,
            reason="broker_acknowledged",
            broker_order_id=broker_id,
            instrument=instrument_key,
            side=side,
            requested_qty=requested_qty,
        )
        upsert_intent(
            OrderIntent(
                trade_id=str(signal_id or "").strip() or None,
                intent_type=intent_type,
                symbol=instrument_key,
                side=str(side or "").upper(),
                qty=int(requested_qty or 0),
                limit_price=limit_price,
                client_order_id=client_order_id,
                status="SUBMITTED",
                order_type=str((submit_kwargs or {}).get("order_type", "LIMIT")).upper() if isinstance(submit_kwargs, dict) else "LIMIT",
                product=str((submit_kwargs or {}).get("product", "MIS")).upper() if isinstance(submit_kwargs, dict) else "MIS",
                exchange=str((submit_kwargs or {}).get("exchange", "NFO")).upper() if isinstance(submit_kwargs, dict) else "NFO",
                strategy_id=str((submit_kwargs or {}).get("strategy_id", "UNKNOWN")) if isinstance(submit_kwargs, dict) else "UNKNOWN",
                timestamp_bucket=int(time.time() // 60),
            )
        )
        return {
            "placed": True,
            "idempotent_skip": False,
            "idempotency_key": idempotency_key,
            "client_order_id": client_order_id,
            "order": acknowledged,
            "broker_response": broker_response,
        }

    # -----------------------------
    # Slippage estimation
    # -----------------------------
    def estimate_slippage(self, bid, ask, volume, qty=1, vol_z=0.0):
        spread = ask - bid

        if spread <= 0:
            return 0
        mid = (bid + ask) / 2.0 if (bid and ask) else 0.0
        if mid <= 0:
            return 0

        # Deterministic slippage model:
        # base spread component + volatility premium + size impact curve.
        spread_proxy = spread / mid
        vol_term = max(0.0, min(abs(float(vol_z or 0.0)), 5.0))
        size_ratio = max(float(qty or 1.0), 1.0) / max(float(volume or 0.0), 1.0)
        size_impact = (size_ratio ** 0.5)
        liq_term = min(1.0, 5000.0 / max(float(volume or 0.0), 1.0))

        base_mult = float(getattr(cfg, "EXEC_DET_BASE_SPREAD_MULT", 0.35))
        vol_mult = float(getattr(cfg, "EXEC_DET_VOL_MULT", 0.08))
        size_mult = float(getattr(cfg, "EXEC_DET_SIZE_MULT", 0.60))
        liq_mult = float(getattr(cfg, "EXEC_DET_LIQ_MULT", 0.25))
        proxy_mult = float(getattr(cfg, "EXEC_DET_PROXY_MULT", 0.10))

        slippage = (
            spread * base_mult
            + spread * vol_term * vol_mult
            + spread * size_impact * size_mult
            + spread * liq_term * liq_mult
            + mid * spread_proxy * proxy_mult
        )
        return max(0.0, slippage)

    # -----------------------------
    # Spread guard
    # -----------------------------
    def spread_ok(
        self,
        bid,
        ask,
        ltp,
        max_spread_pct=None,
        *,
        instrument=None,
        bars=None,
        now_dt=None,
        segment=None,
        market_open=None,
        minutes_since_open=None,
        volume=None,
        avg_volume=None,
    ):
        decision = self._spread_guard.evaluate(
            bid=bid,
            ask=ask,
            ltp=ltp,
            instrument=instrument,
            bars=bars,
            max_spread_pct_override=max_spread_pct,
            now_dt=now_dt,
            segment=segment,
            market_open=market_open,
            minutes_since_open_override=minutes_since_open,
            volume=volume,
            avg_volume=avg_volume,
        )
        self._last_spread_decision = decision
        return bool(decision.allowed)

    # -----------------------------
    # Latency penalty
    # -----------------------------
    def latency_penalty(self, data_timestamp):
        age = time.time() - data_timestamp

        if age <= 1:
            return 1.0
        elif age <= 2:
            return 0.9
        elif age <= 3:
            return 0.8
        else:
            return 0.6

    # -----------------------------
    # Execution kill switch
    # -----------------------------
    @staticmethod
    def _coerce_failure_type(failure_type):
        if isinstance(failure_type, FailureType):
            return failure_type
        return FailureType(str(failure_type or FailureType.UNKNOWN.value).strip().upper())

    def _prune_network_failure_window(self, now_epoch):
        cutoff = float(now_epoch) - float(self._network_failure_window_sec)
        while self._network_failure_timestamps and float(self._network_failure_timestamps[0]) < cutoff:
            self._network_failure_timestamps.popleft()

    def _write_failure_log(self, payload):
        try:
            self._failure_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._failure_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            pass

    def _write_execution_action_log(self, payload):
        try:
            self._execution_action_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._execution_action_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            pass

    def _write_exit_intent_log(self, payload):
        try:
            self._exit_intent_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._exit_intent_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            pass

    @staticmethod
    def build_exit_intent_id(intent: dict | None) -> str:
        payload = dict(intent or {})
        digest_payload = {k: v for k, v in payload.items() if k != "ts_epoch"}
        digest = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        return f"exit_{digest}"

    def apply_exit_intent(self, intent: dict | None) -> dict:
        """
        Exit-intelligence sink for runtime-initiated active-position actions.
        This method is deterministic and auditable; it validates and records intent,
        then returns an ACK for the orchestrator to apply state transitions safely.
        """
        now_ts = time.time()
        payload = dict(intent or {})
        action = str(payload.get("action") or "").upper()
        qty = payload.get("exit_qty_units")
        try:
            qty_val = int(qty or 0)
        except Exception:
            qty_val = 0
        errors: list[str] = []
        if action not in {"MODIFY_PLAN", "PARTIAL_EXIT", "FULL_EXIT"}:
            errors.append("invalid_exit_action")
        if action in {"PARTIAL_EXIT", "FULL_EXIT"} and qty_val <= 0:
            errors.append("invalid_exit_qty")
        intent_id = self.build_exit_intent_id(payload)
        ack = {
            "accepted": len(errors) == 0,
            "intent_id": intent_id,
            "ts_epoch": now_ts,
            "errors": errors,
        }
        self._write_exit_intent_log(
            {
                "event": "EXIT_INTENT",
                "ts_epoch": now_ts,
                "intent_id": ack["intent_id"],
                "accepted": ack["accepted"],
                "errors": errors,
                "payload": payload,
            }
        )
        return ack

    def get_failure_snapshot(self, now_epoch=None):
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        with self._failure_lock:
            self._prune_network_failure_window(now_ts)
            return {
                "failed_executions": int(self.failed_executions),
                "counters": {ft.value: int(self.failure_counters.get(ft, 0)) for ft in FailureType},
                "network_failures_rolling_60s": int(len(self._network_failure_timestamps)),
                "kill_switch_triggered": bool(self.kill_switch_triggered),
                "kill_switch_reason": self.kill_switch_reason,
                "network_window_sec": float(self._network_failure_window_sec),
                "broker_reject_kill_threshold": int(self._broker_reject_kill_threshold),
                "network_kill_threshold": int(self._network_kill_threshold),
            }

    def register_failure(
        self,
        failure_type,
        *,
        reason=None,
        context=None,
        now_epoch=None,
        raise_on_kill_switch=True,
    ):
        ftype = self._coerce_failure_type(failure_type)
        now_ts = float(now_epoch if now_epoch is not None else time.time())
        ctx = dict(context or {})
        with self._failure_lock:
            self.failed_executions += 1
            self.failure_counters[ftype] = int(self.failure_counters.get(ftype, 0)) + 1
            if ftype == FailureType.NETWORK:
                self._network_failure_timestamps.append(now_ts)
            self._prune_network_failure_window(now_ts)

            broker_rejects = int(self.failure_counters.get(FailureType.BROKER_REJECT, 0))
            network_rolling = int(len(self._network_failure_timestamps))
            kill_switch = False
            kill_reason = None
            if broker_rejects > int(self._broker_reject_kill_threshold):
                kill_switch = True
                kill_reason = "BROKER_REJECT_THRESHOLD_EXCEEDED"
            elif network_rolling > int(self._network_kill_threshold):
                kill_switch = True
                kill_reason = "NETWORK_FAILURE_WINDOW_EXCEEDED"

            if kill_switch:
                self.kill_switch_triggered = True
                self.kill_switch_reason = kill_reason

            payload = {
                "ts_epoch": now_ts,
                "event": "execution_failure",
                "failure_type": ftype.value,
                "reason": str(reason) if reason is not None else None,
                "context": ctx,
                "failed_executions_total": int(self.failed_executions),
                "failure_counters": {k.value: int(v) for k, v in self.failure_counters.items()},
                "network_failures_rolling_60s": network_rolling,
                "broker_reject_kill_threshold": int(self._broker_reject_kill_threshold),
                "network_kill_threshold": int(self._network_kill_threshold),
                "kill_switch_triggered": bool(kill_switch),
                "kill_switch_reason": kill_reason,
            }

        self._write_failure_log(payload)

        if kill_switch and raise_on_kill_switch:
            raise RuntimeError(f"❌ EXECUTION KILL SWITCH TRIGGERED ({kill_reason})")
        return payload

    def reset_failures(self):
        with self._failure_lock:
            self.failed_executions = 0
            self.failure_counters = {ft: 0 for ft in FailureType}
            self._network_failure_timestamps.clear()
            self.kill_switch_triggered = False
            self.kill_switch_reason = None

    def execute_with_network_retry(
        self,
        operation_fn,
        *,
        operation_name="network_call",
        max_attempts=None,
        base_delay_sec=None,
        max_delay_sec=None,
        context=None,
    ):
        attempts = max(1, int(max_attempts if max_attempts is not None else self._network_retry_max_attempts))
        base_delay = max(0.0, float(base_delay_sec if base_delay_sec is not None else self._network_retry_base_sec))
        max_delay = max(0.0, float(max_delay_sec if max_delay_sec is not None else self._network_retry_max_sec))
        last_exc = None

        for attempt in range(1, attempts + 1):
            try:
                out = operation_fn()
                if attempt > 1:
                    self._write_failure_log(
                        {
                            "ts_epoch": time.time(),
                            "event": "network_retry_recovered",
                            "operation": str(operation_name),
                            "attempt": attempt,
                            "max_attempts": attempts,
                        }
                    )
                return out
            except Exception as exc:
                last_exc = exc
                self.register_failure(
                    FailureType.NETWORK,
                    reason=f"{operation_name}_attempt_failed",
                    context={
                        "operation": str(operation_name),
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        **(dict(context or {})),
                    },
                    raise_on_kill_switch=True,
                )
                if attempt >= attempts:
                    break
                delay_sec = min(max_delay, base_delay * (2 ** (attempt - 1)))
                self._write_failure_log(
                    {
                        "ts_epoch": time.time(),
                        "event": "network_retry_backoff",
                        "operation": str(operation_name),
                        "attempt": attempt,
                        "sleep_sec": float(delay_sec),
                    }
                )
                if delay_sec > 0:
                    time.sleep(delay_sec)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"{operation_name}_failed_without_exception")

    # -----------------------------
    # Limit order helpers (simulated)
    # -----------------------------
    def build_limit_price(self, side, bid, ask):
        buffer = (self.slippage_bps / 10000.0)
        if side == "BUY":
            return round(ask * (1 + buffer), 2)
        return round(bid * (1 - buffer), 2)

    def adaptive_limit_price(
        self,
        side,
        bid,
        ask,
        spread_pct=None,
        depth_imbalance=None,
        vol_z=None,
        *,
        depth=None,
        qty=1,
        signal_strength=None,
        elapsed_sec=0.0,
        timeout_sec=0.0,
        retry_index=0,
        max_retries=0,
        current_limit=None,
        max_slippage_bps=None,
        atr_ratio=None,
    ):
        policy = AdaptivePricePolicy(
            base_slippage_bps=float(self.slippage_bps),
            spread_mult=float(getattr(cfg, "EXEC_ALPHA_SPREAD_MULT", 0.6)),
            max_buffer_pct=float(getattr(cfg, "EXEC_ALPHA_MAX_BUFFER_PCT", 0.01)),
            vol_z_bps=float(getattr(cfg, "EXEC_ALPHA_VOL_Z_BPS", 3.0)),
            imbalance_bps=float(getattr(cfg, "EXEC_ALPHA_IMBALANCE_BPS", 2.0)),
            atr_vol_bps_mult=float(getattr(cfg, "EXEC_ALPHA_ATR_VOL_MULT", 0.5)),
            queue_consumption_bps=float(getattr(cfg, "EXEC_ALPHA_QUEUE_BPS", 4.0)),
            urgency_bps=float(getattr(cfg, "EXEC_ALPHA_URGENCY_BPS", 3.0)),
            time_decay_bps=float(getattr(cfg, "EXEC_ALPHA_TIME_DECAY_BPS", 5.0)),
            retry_step_pct=float(getattr(cfg, "EXEC_ADAPTIVE_STEP_PCT", 0.0005)),
            max_slippage_bps=float(
                max_slippage_bps
                if max_slippage_bps is not None
                else getattr(cfg, "EXEC_ADAPTIVE_MAX_SLIPPAGE_BPS", 150.0)
            ),
            min_tick=float(getattr(cfg, "EXEC_ALPHA_MIN_TICK", 0.05)),
            queue_levels=int(getattr(cfg, "EXEC_ALPHA_QUEUE_LEVELS", 3)),
        )
        out = compute_adaptive_limit_price(
            AdaptivePriceInput(
                side=str(side or "").upper(),
                bid=float(bid or 0.0),
                ask=float(ask or 0.0),
                qty=float(qty if qty is not None else 1.0),
                spread_pct=spread_pct,
                depth_imbalance=depth_imbalance,
                vol_z=vol_z,
                atr_ratio=atr_ratio,
                depth=depth if isinstance(depth, dict) else None,
                signal_strength=signal_strength,
                elapsed_sec=float(elapsed_sec or 0.0),
                timeout_sec=float(timeout_sec or 0.0),
                retry_index=int(retry_index or 0),
                max_retries=int(max_retries or 0),
                current_limit=current_limit,
            ),
            policy,
        )
        return out.limit_price, out.details

    def calibrate_slippage(self, slippage, instrument="OPT"):
        """
        Update slippage bps estimate using recent fill slippage.
        """
        if slippage is None:
            return
        # crude calibration: adjust bps toward observed slippage
        self.slippage_bps = max(1, min(25, int(self.slippage_bps * 0.9 + slippage * 10 * 0.1)))
        self.instrument_slippage[instrument] = self.slippage_bps

    def place_limit_order(self, trade, quote_fn, spread_pct=None, depth_imbalance=None, vol_z=None):
        """
        Simulated limit order placement with retry logic.
        Replace with broker API call for live execution.
        """
        instrument_key = self._normalize_instrument(
            getattr(trade, "symbol", None) or getattr(trade, "instrument", None)
        )
        gate = self.is_instrument_temporarily_disabled(instrument_key)
        if bool(gate.get("disabled")):
            return False, None
        if quote_fn is None or not callable(quote_fn):
            return False, None
        decision = quote_fn()
        if not decision:
            return False, None
        bid = decision.get("bid", 0) or 0
        ask = decision.get("ask", 0) or 0
        if bid <= 0 or ask <= 0:
            return False, None
        limit_price, _ = self.adaptive_limit_price(
            trade.side,
            bid,
            ask,
            spread_pct=spread_pct,
            depth_imbalance=depth_imbalance,
            vol_z=vol_z,
            depth=decision.get("depth") if isinstance(decision, dict) else None,
            qty=getattr(trade, "qty", 1),
            signal_strength=getattr(trade, "confidence", None),
            timeout_sec=getattr(cfg, "EXEC_SIM_TIMEOUT_SEC", 3.0),
            max_retries=int(getattr(cfg, "EXEC_ADAPTIVE_MAX_RETRIES", 5)),
        )
        if limit_price is None:
            return False, None
        filled, price, report = self.simulate_limit_fill(
            trade,
            limit_price,
            quote_fn,
            timeout_sec=getattr(cfg, "EXEC_SIM_TIMEOUT_SEC", 3.0),
            poll_sec=getattr(cfg, "EXEC_SIM_POLL_SEC", 0.25),
            max_chase_pct=getattr(cfg, "EXEC_MAX_CHASE_PCT", 0.002),
            spread_widen_pct=getattr(cfg, "EXEC_SPREAD_WIDEN_PCT", 0.5),
            max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.015),
            max_quote_age_sec=getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0),
            fill_prob=getattr(cfg, "EXEC_FILL_PROB", 0.85),
        )
        if not filled:
            abort_reason = str((report or {}).get("reason_if_aborted") or "limit_order_not_filled")
            failure_type = FailureType.UNKNOWN
            if abort_reason in {"spread_too_wide", "spread_widened"}:
                failure_type = FailureType.SPREAD_TOO_WIDE
            self.register_failure(
                failure_type,
                reason=abort_reason,
                context={
                    "symbol": str(getattr(trade, "symbol", "")),
                    "instrument": str(getattr(trade, "instrument", "")),
                    "side": str(getattr(trade, "side", "")),
                },
            )
            return False, None
        return True, price

    def simulate_order_slicing(self, trade, bid, ask, volume, depth=None):
        """
        Simulate sliced fills using spread and volume as liquidity proxies.
        """
        if trade.instrument == "OPT":
            slices = getattr(cfg, "ORDER_SLICES_OPT", 3)
        elif trade.instrument == "FUT":
            slices = getattr(cfg, "ORDER_SLICES_FUT", 2)
        else:
            slices = getattr(cfg, "ORDER_SLICES_EQ", 1)
        total_qty = max(1, trade.qty)
        slice_qty = max(1, total_qty // slices)
        filled_qty = 0
        fill_price = 0.0
        spread = max(ask - bid, 0)
        impact_alpha = getattr(cfg, "IMPACT_ALPHA", 0.15)
        queue_alpha = getattr(cfg, "QUEUE_ALPHA", 0.25) if getattr(cfg, "QUEUE_POSITION_MODEL", True) else 0.0
        for _ in range(slices):
            # simple slippage model
            base_slip = self.estimate_slippage(bid, ask, volume)
            if depth:
                try:
                    top_bid = depth.get("buy", [{}])[0].get("price", bid)
                    top_ask = depth.get("sell", [{}])[0].get("price", ask)
                    spread = max(top_ask - top_bid, spread)
                except Exception:
                    pass
            impact = (slice_qty / max(volume, 1)) * impact_alpha * spread
            queue_penalty = queue_alpha * spread
            slippage = base_slip + impact + queue_penalty
            price = (ask + slippage) if trade.side == "BUY" else (bid - slippage)
            fill_price += price * slice_qty
            filled_qty += slice_qty
        if filled_qty == 0:
            return False, None
        avg_price = round(fill_price / filled_qty, 2)
        return True, avg_price

    # -----------------------------
    # Queue position estimator (depth-based)
    # -----------------------------
    def estimate_queue_position(self, depth, side, limit_price=None, qty=1):
        if not depth:
            return None
        try:
            book = depth.get("buy") if side == "BUY" else depth.get("sell")
            if not book:
                return None
            top = book[0]
            top_qty = float(top.get("quantity", 0) or 0)
            top_price = float(top.get("price", 0) or 0)
            if limit_price is not None and top_price:
                if side == "BUY" and limit_price > top_price:
                    return 0.0
                if side == "SELL" and limit_price < top_price:
                    return 0.0
            denom = max(top_qty + max(qty, 1), 1.0)
            return round(top_qty / denom, 4)
        except Exception:
            return None

    # -----------------------------
    # Quote-driven limit simulation
    # -----------------------------
    def simulate_limit_fill(
        self,
        trade,
        limit_price,
        quote_fn=None,
        snapshot_fn=None,
        timeout_sec=0.0,
        poll_sec=0.0,
        max_chase_pct=0.0,
        spread_widen_pct=0.0,
        max_spread_pct=0.0,
        max_quote_age_sec=None,
        fill_prob=1.0,
        run_id=None,
    ):
        """
        Simulate a limit order using sequential quote snapshots.
        Buy fills ONLY if limit >= ask on a later snapshot.
        Sell fills ONLY if limit <= bid on a later snapshot.
        """
        def _mid_spread(bid, ask):
            mid = (bid + ask) / 2.0 if bid and ask else 0.0
            spread = max(ask - bid, 0.0) if bid and ask else 0.0
            return mid, spread

        def _resolve_run_id():
            if run_id is not None:
                return str(run_id)
            trade_run_id = getattr(trade, "run_id", None)
            if trade_run_id is not None:
                return str(trade_run_id)
            cfg_run_id = getattr(cfg, "RUN_ID", None)
            if cfg_run_id is not None:
                return str(cfg_run_id)
            cfg_exec_run_id = getattr(cfg, "EXEC_RUN_ID", None)
            if cfg_exec_run_id is not None:
                return str(cfg_exec_run_id)
            return "default"

        def _deterministic_uniform(attempt_idx, bid, ask, current_limit, prob):
            trade_id = getattr(trade, "trade_id", "NO_TRADE_ID")
            key = "|".join(
                [
                    _resolve_run_id(),
                    str(trade_id),
                    str(getattr(trade, "symbol", "NO_SYMBOL")),
                    str(getattr(trade, "side", "NA")),
                    str(attempt_idx),
                    f"{float(bid):.6f}",
                    f"{float(ask):.6f}",
                    f"{float(current_limit):.6f}",
                    f"{float(prob):.6f}",
                ]
            )
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            return int(digest[:16], 16) / float(16 ** 16)

        def _normalize_regime(value):
            text = str(value or "").strip().upper()
            return text or None

        def _snapshot_regime(payload):
            if not isinstance(payload, dict):
                return None
            return _normalize_regime(
                payload.get("regime_day")
                or payload.get("primary_regime")
                or payload.get("regime")
            )

        def _to_float(value):
            try:
                if value is None:
                    return None
                return float(value)
            except Exception:
                return None

        def _snapshot_atr_ratio(payload, reference_mid):
            if not isinstance(payload, dict):
                return None
            bars = payload.get("candles")
            if not isinstance(bars, list) or len(bars) < 2:
                return None
            period = min(20, len(bars) - 1)
            recent = bars[-(period + 1):]
            trs = []
            for i in range(1, len(recent)):
                row = recent[i] if isinstance(recent[i], dict) else {}
                prev = recent[i - 1] if isinstance(recent[i - 1], dict) else {}
                high = _to_float(row.get("high") if "high" in row else row.get("h"))
                low = _to_float(row.get("low") if "low" in row else row.get("l"))
                prev_close = _to_float(
                    prev.get("close")
                    if "close" in prev
                    else prev.get("c")
                )
                if prev_close is None:
                    prev_close = _to_float(prev.get("ltp"))
                if high is None or low is None:
                    continue
                if prev_close is None:
                    prev_close = (high + low) / 2.0
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                if tr >= 0:
                    trs.append(float(tr))
            if not trs:
                return None
            ref = float(reference_mid or 0.0)
            if ref <= 0:
                return None
            return max(0.0, (sum(trs) / float(len(trs))) / ref)

        if quote_fn is None:
            quote_fn = snapshot_fn
        decision = quote_fn() if quote_fn else None
        if not decision:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
            }

        bid0 = decision.get("bid", 0) or 0
        ask0 = decision.get("ask", 0) or 0
        ts0 = decision.get("ts")
        if ts0 is None:
            ts0 = time.time()
        decision_mid, decision_spread = _mid_spread(bid0, ask0)
        if decision_mid <= 0 or decision_spread <= 0:
            return False, None, {
                "decision_mid": decision_mid or None,
                "decision_spread": decision_spread or None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "bad_initial_quote",
            }
        if ts0 is None:
            return False, None, {
                "decision_mid": decision_mid,
                "decision_spread": decision_spread,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "missing_quote_ts",
            }
        if max_quote_age_sec is not None and (time.time() - ts0) > max_quote_age_sec:
            return False, None, {
                "decision_mid": decision_mid,
                "decision_spread": decision_spread,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "stale_quote",
            }

        requested_qty = int(max(getattr(trade, "qty", 1) or 1, 1))
        start = time.time()
        current_limit = limit_price
        reason = "timeout"
        max_retries = max(0, int(getattr(cfg, "EXEC_ADAPTIVE_MAX_RETRIES", 5)))
        retry_limit_hit_reason = str(getattr(cfg, "EXEC_ADAPTIVE_RETRY_LIMIT_REASON", "retry_limit_exceeded"))
        adaptive_retry_enable = bool(getattr(cfg, "EXEC_ADAPTIVE_RETRY_ENABLE", False))
        abort_on_regime_change = bool(getattr(cfg, "EXEC_ADAPTIVE_ABORT_ON_REGIME_CHANGE", True))
        adaptive_max_slippage_bps = float(getattr(cfg, "EXEC_ADAPTIVE_MAX_SLIPPAGE_BPS", 150.0))
        retry_count = 0
        retry_events = []
        last_retry_quote = None
        base_regime = _normalize_regime(
            getattr(trade, "regime", None)
            or _snapshot_regime(decision)
        )
        attempts = [
            {
                "ts": ts0,
                "bid": bid0,
                "ask": ask0,
                "spread": round(decision_spread, 6),
            }
        ]
        attempt_idx = 0

        while time.time() - start <= timeout_sec:
            snap = quote_fn()
            if not snap:
                reason = "no_quote"
                break
            bid = snap.get("bid", 0) or 0
            ask = snap.get("ask", 0) or 0
            ts = snap.get("ts")
            if ts is None:
                ts = time.time()
            if bid <= 0 or ask <= 0:
                time.sleep(poll_sec)
                continue

            mid, spread = _mid_spread(bid, ask)
            attempts.append(
                {
                    "ts": ts,
                    "bid": bid,
                    "ask": ask,
                    "spread": round(spread, 6),
                }
            )
            attempt_idx += 1

            current_regime = _snapshot_regime(snap) or _normalize_regime(getattr(trade, "regime", None))
            if (
                abort_on_regime_change
                and base_regime is not None
                and current_regime is not None
                and current_regime != base_regime
            ):
                reason = "regime_changed"
                break

            if ts is None:
                reason = "missing_quote_ts"
                break
            if max_quote_age_sec is not None and (time.time() - ts) > max_quote_age_sec:
                reason = "stale_quote"
                break

            retry_reference_limit = float(current_limit)
            if max_chase_pct and max_chase_pct > 0:
                if trade.side == "BUY":
                    max_limit = decision_mid * (1 + max_chase_pct)
                    if ask > current_limit and ask <= max_limit:
                        current_limit = ask
                    elif ask > max_limit:
                        reason = "max_chase_exceeded"
                        break
                else:
                    min_limit = decision_mid * (1 - max_chase_pct)
                    if bid < current_limit and bid >= min_limit:
                        current_limit = bid
                    elif bid < min_limit:
                        reason = "max_chase_exceeded"
                        break

            if max_spread_pct and mid > 0 and (spread / mid) > max_spread_pct:
                reason = "spread_too_wide"
                break
            if spread_widen_pct and decision_spread > 0 and spread > decision_spread * (1 + spread_widen_pct):
                reason = "spread_widened"
                break

            sim = self.fill_model.simulate(
                order={
                    "side": getattr(trade, "side", ""),
                    "symbol": getattr(trade, "symbol", "UNKNOWN"),
                    "qty": requested_qty,
                    "limit_price": current_limit,
                },
                market_snapshot=snap,
                run_id=_resolve_run_id(),
            )

            sim_filled = sim.get("status") in ("FILLED", "PARTIAL") and int(sim.get("fill_qty", 0) or 0) > 0
            fill_allowed = sim_filled
            if sim_filled:
                if fill_prob <= 0.0:
                    fill_allowed = False
                elif fill_prob < 1.0:
                    draw = _deterministic_uniform(attempt_idx, bid, ask, current_limit, fill_prob)
                    if draw > fill_prob:
                        fill_allowed = False
            if fill_allowed:
                fill_price = float(sim.get("fill_price"))
                slippage = (fill_price - decision_mid) if trade.side == "BUY" else (decision_mid - fill_price)
                return True, round(fill_price, 2), {
                    "decision_mid": round(decision_mid, 2),
                    "decision_spread": round(decision_spread, 2),
                    "fill_price": round(fill_price, 2),
                    "slippage": round(slippage, 4),
                    "slippage_bp": sim.get("slippage_bp"),
                    "latency_ms": sim.get("latency_ms"),
                    "fill_qty": int(sim.get("fill_qty", 0) or 0),
                    "requested_qty": requested_qty,
                    "fill_status": sim.get("status"),
                    "reason_if_aborted": None,
                    "attempts": attempts,
                    "retry_count": int(retry_count),
                    "retry_events": list(retry_events),
                }

            if adaptive_retry_enable:
                quote_key = (round(float(bid), 6), round(float(ask), 6))
                moved_away = (
                    (str(trade.side).upper() == "BUY" and float(ask) > retry_reference_limit)
                    or (str(trade.side).upper() == "SELL" and float(bid) < retry_reference_limit)
                )
                can_retry = (
                    retry_count < max_retries
                    and moved_away
                    and quote_key != last_retry_quote
                )
                if can_retry:
                    atr_ratio = _snapshot_atr_ratio(snap, mid)
                    next_limit, pricing_meta = self.adaptive_limit_price(
                        trade.side,
                        bid,
                        ask,
                        spread_pct=(spread / max(mid, 1e-9)) if mid > 0 else None,
                        depth_imbalance=snap.get("depth_imbalance") if isinstance(snap, dict) else None,
                        vol_z=snap.get("vol_z") if isinstance(snap, dict) else getattr(trade, "vol_z", None),
                        depth=snap.get("depth") if isinstance(snap, dict) else None,
                        qty=requested_qty,
                        signal_strength=getattr(trade, "confidence", None),
                        elapsed_sec=max(0.0, time.time() - start),
                        timeout_sec=timeout_sec,
                        retry_index=retry_count + 1,
                        max_retries=max_retries,
                        current_limit=current_limit,
                        max_slippage_bps=adaptive_max_slippage_bps,
                        atr_ratio=atr_ratio,
                    )
                    if next_limit is not None:
                        improved = (
                            (str(trade.side).upper() == "BUY" and float(next_limit) > float(current_limit))
                            or (str(trade.side).upper() == "SELL" and float(next_limit) < float(current_limit))
                        )
                        if improved:
                            retry_count += 1
                            retry_events.append(
                                {
                                    "retry_index": retry_count,
                                    "old_limit": round(float(current_limit), 6),
                                    "new_limit": round(float(next_limit), 6),
                                    "spread": round(float(spread), 6),
                                    "spread_pct": round((spread / max(mid, 1e-9)) if mid > 0 else 0.0, 8),
                                    "vol_z": pricing_meta.get("vol_z"),
                                    "atr_ratio": pricing_meta.get("atr_ratio"),
                                    "urgency_score": pricing_meta.get("urgency_score"),
                                    "time_decay_aggressiveness": pricing_meta.get("time_decay_aggressiveness"),
                                    "queue_consumption_ratio": pricing_meta.get("queue_consumption_ratio"),
                                    "max_slippage_guard_hit": bool(
                                        pricing_meta.get("max_slippage_guard_hit", False)
                                    ),
                                }
                            )
                            current_limit = float(next_limit)
                            last_retry_quote = quote_key
                        else:
                            retry_count += 1
                            retry_events.append(
                                {
                                    "retry_index": retry_count,
                                    "old_limit": round(float(current_limit), 6),
                                    "new_limit": round(float(next_limit), 6),
                                    "spread": round(float(spread), 6),
                                    "spread_pct": round((spread / max(mid, 1e-9)) if mid > 0 else 0.0, 8),
                                    "vol_z": pricing_meta.get("vol_z"),
                                    "atr_ratio": pricing_meta.get("atr_ratio"),
                                    "urgency_score": pricing_meta.get("urgency_score"),
                                    "time_decay_aggressiveness": pricing_meta.get("time_decay_aggressiveness"),
                                    "queue_consumption_ratio": pricing_meta.get("queue_consumption_ratio"),
                                    "max_slippage_guard_hit": bool(
                                        pricing_meta.get("max_slippage_guard_hit", False)
                                    ),
                                    "unchanged_limit": True,
                                }
                            )
                            last_retry_quote = quote_key
                            if retry_count >= max_retries:
                                reason = retry_limit_hit_reason
                                break

            if adaptive_retry_enable and retry_count >= max_retries and max_retries > 0:
                reason = retry_limit_hit_reason
                break

            time.sleep(poll_sec)

        return False, None, {
            "decision_mid": round(decision_mid, 2),
            "decision_spread": round(decision_spread, 2),
            "fill_price": None,
            "slippage": None,
            "slippage_bp": None,
            "latency_ms": None,
            "fill_qty": 0,
            "requested_qty": requested_qty,
            "fill_status": "NOFILL",
            "reason_if_aborted": reason,
            "attempts": attempts,
            "retry_count": int(retry_count),
            "retry_events": list(retry_events),
        }
