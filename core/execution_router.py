from core.paths import data_root, logs_dir
import time
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from config import config as cfg
from core.execution.chokepoint import ApprovalMissingOrInvalid, require_approval_or_abort
from core.execution.execution_audit import append_execution_audit_event
from core.execution.execution_guard import evaluate_execution_guard
from core.execution_engine import ExecutionEngine
from core.paper_fill_simulator import PaperFillSimulator
from core.paper_outcome_journal import record_paper_outcome
from core.paper_runtime_setup_identity import attach_runtime_setup_identity
from core.trade_store import insert_execution_stat
from core.fill_quality import log_fill_quality
from core.execution_quality import execution_quality_score
from core.orders.execution_plan import ExecutionPlan
from core.orders.order_intent import OrderIntent
from core.orders.state_machine import OrderState
from core.readiness_gate import run_readiness_check
from core.freshness_sla import get_freshness_status
from core.market_data_monitor import get_feed_health_monitor
from core.feed.gate import check_execution_allowed
from core.runtime_authority_cutover import preflight_execution_authority


logger = logging.getLogger(__name__)


def _safe_float(value):
    try:
        if value in (None, "", "None"):
            return None
        number = float(value)
    except Exception:
        return None
    return number if number == number else None


class ExecutionRouter:
    """
    Routes trades to SIM/PAPER/LIVE modes.
    LIVE mode is a stub until order placement is enabled.
    """
    def __init__(self, *, feed_health=None):
        self.engine = ExecutionEngine()
        self.paper_sim = PaperFillSimulator(
            timeout_sec=getattr(cfg, "EXEC_SIM_TIMEOUT_SEC", 3.0),
            poll_sec=getattr(cfg, "EXEC_SIM_POLL_SEC", 0.25),
        )
        self.feed_health = feed_health or get_feed_health_monitor()
        self._use_legacy_feed_gate = feed_health is not None
        self._intent_log_write_warned = False
        self._paper_outcome_write_warned = False

    def execute(self, trade, bid, ask, volume, depth=None, snapshot_fn=None, spread_pct=None, depth_imbalance=None, vol_z=None):
        mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
        authority = preflight_execution_authority(trade, mode=mode)
        if authority is not None and not bool(authority.get("allowed")):
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": f"runtime_authority_blocked:{authority.get('reason')}",
                "runtime_authority": authority,
            }
        try:
            execution_plan = ExecutionPlan.from_trade(trade, mode=mode)
        except Exception as exc:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": f"execution_plan_invalid:{type(exc).__name__}",
            }
        order_intent = OrderIntent.from_trade(
            trade,
            mode=mode,
            default_exchange=str(getattr(trade, "exchange", "NFO") or "NFO"),
            default_product=str(getattr(trade, "product", "MIS") or "MIS"),
        )
        payload_hash = order_intent.order_intent_hash()
        try:
            order_record = self._open_order_record(trade, order_intent)
        except Exception as exc:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": f"order_state_store_error:{type(exc).__name__}",
            }

        current_order = order_record
        instrument_key = str(getattr(trade, "symbol", None) or getattr(trade, "instrument", None) or "UNKNOWN")
        requested_qty = getattr(trade, "qty", None)

        def _report(payload):
            body = dict(payload or {})
            if current_order is not None:
                body["order_id"] = current_order.order_id
                body["idempotency_key"] = current_order.idempotency_key
                body["order_state"] = current_order.state.value
                body["broker_order_id"] = current_order.broker_order_id
                body["created_at"] = current_order.created_at
                body["updated_at"] = current_order.updated_at
            body["snapshot_id"] = execution_plan.snapshot_id
            body["decision_id"] = execution_plan.decision_id
            return body

        def _transition(
            new_state,
            reason=None,
            broker_order_id=None,
            filled_qty=None,
            slippage=None,
            time_to_fill_sec=None,
        ):
            nonlocal current_order
            current_order = self.engine.transition_order_state(
                order_id=current_order.order_id,
                new_state=new_state,
                reason=reason,
                broker_order_id=broker_order_id,
                filled_qty=filled_qty,
                slippage=slippage,
                time_to_fill_sec=time_to_fill_sec,
                instrument=instrument_key,
                side=getattr(trade, "side", None),
                requested_qty=requested_qty,
            )
            return current_order

        def _abort(reason, *, extra=None, note=None):
            if note:
                self._record_intent(
                    trade,
                    bid,
                    ask,
                    volume,
                    depth=depth,
                    note=note,
                    execution_plan=execution_plan,
                )
            terminal_state = self._terminal_state_for_reason(reason)
            _transition(terminal_state, reason=reason)
            payload = {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": reason,
            }
            if extra:
                payload.update(extra)
            if mode == "PAPER":
                self._record_paper_execution_outcome(
                    trade=trade,
                    order=current_order,
                    terminal_state=terminal_state,
                    reason=reason,
                    report=payload,
                    fill_price=None,
                    slippage=payload.get("slippage"),
                )
            append_execution_audit_event(
                trade=trade,
                order_action="abort",
                guard_result=(extra if isinstance(extra, dict) and "execution_allowed" in extra else None),
                broker_response=payload,
                reason=reason,
            )
            return False, None, _report(payload)

        if getattr(trade, "tradable", True) is False:
            reasons = list(getattr(trade, "tradable_reasons_blocking", []) or [])
            reason = "non_tradable" if not reasons else f"non_tradable:{'|'.join(reasons)}"
            return _abort(reason, note=reason)

        readiness_enabled = bool(
            getattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", getattr(cfg, "READINESS_ENFORCE_ON_EXEC", False))
        )
        enforce_readiness = readiness_enabled and (
            mode == "LIVE" or (mode == "PAPER" and bool(getattr(cfg, "READINESS_ENFORCE_PAPER", False)))
        )
        if enforce_readiness:
            readiness = run_readiness_check(write_log=False)
            can_trade = bool(readiness.get("can_trade", readiness.get("ready", False)))
            if not can_trade:
                blockers = list(readiness.get("blockers") or readiness.get("reasons") or [])
                state = str(readiness.get("state", "BLOCKED"))
                reason = f"readiness_gate_fail:{state}"
                if blockers:
                    reason = f"{reason}:{'|'.join(blockers)}"
                return _abort(
                    reason,
                    note=reason,
                    extra={
                        "readiness_state": state,
                        "readiness_blockers": blockers,
                    },
                )
            freshness = get_freshness_status(force=False)
            if bool(freshness.get("market_open")) and not bool(freshness.get("ok")):
                reasons = list(freshness.get("reasons") or [])
                reason = "freshness_sla_failed" if not reasons else f"freshness_sla_failed:{'|'.join(reasons)}"
                return _abort(
                    reason,
                    note=reason,
                    extra={
                        "freshness_state": freshness.get("state"),
                        "freshness_reasons": reasons,
                    },
                )

        if mode in {"SIM", "PAPER"}:
            perf_gate = self.engine.is_instrument_temporarily_disabled(instrument_key)
            if bool(perf_gate.get("disabled")):
                return _abort(
                    "instrument_temporarily_disabled",
                    note="execution_performance_cooldown",
                    extra={
                        "instrument_disabled_until": perf_gate.get("disabled_until"),
                        "instrument_disable_reason": perf_gate.get("disable_reason"),
                    },
                )

        if mode in {"SIM", "PAPER"}:
            self._record_intent(
                trade,
                bid,
                ask,
                volume,
                depth=depth,
                note=f"{mode.lower()} intent",
                execution_plan=execution_plan,
            )
            if snapshot_fn is None or not callable(snapshot_fn):
                return _abort("no_quote_fn")
            first = snapshot_fn()
            if not first:
                return _abort("no_quote")
            bid = first.get("bid", bid)
            ask = first.get("ask", ask)
            guard = evaluate_execution_guard(
                side=getattr(trade, "side", None),
                bid=bid,
                ask=ask,
                snapshot=first,
                evaluated_at_epoch=time.time(),
                max_quote_age_sec=getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0),
                max_spread_pct=getattr(cfg, "EXEC_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.015)),
                reference_price=getattr(trade, "entry_price", None),
            )
            if not guard.execution_allowed:
                return _abort(
                    guard.reasons[0] if guard.reasons else "execution_guard_failed",
                    extra=guard.as_dict(),
                )
            limit_price = trade.entry_price
            if limit_price is None:
                limit_price, _ = self.engine.adaptive_limit_price(
                    trade.side, bid, ask, spread_pct=spread_pct, depth_imbalance=depth_imbalance, vol_z=vol_z
                )
            if limit_price is None:
                return _abort("invalid_limit_price")

            _transition(OrderState.SENT, reason="order_sent")
            try:
                require_approval_or_abort(
                    order_intent,
                    mode=mode,
                    now=time.time(),
                    approver=getattr(trade, "approved_by", None),
                    ttl=int(getattr(cfg, "ORDER_APPROVAL_TTL_SEC", getattr(cfg, "APPROVAL_TTL_SEC", 600))),
                )
            except ApprovalMissingOrInvalid as exc:
                return _abort(
                    exc.reason,
                    note=f"manual_approval_blocked:{exc.reason}",
                    extra={"approval_payload_hash": payload_hash},
                )
            _transition(OrderState.ACKNOWLEDGED, reason="approval_consumed")

            start_ts = time.time()
            if mode == "SIM":
                filled, price, report = self._simulate_limit(
                    trade, bid, ask, limit_price, snapshot_fn=snapshot_fn
                )
            else:
                filled, price, report = self.paper_sim.simulate(
                    trade,
                    limit_price,
                    snapshot_fn,
                    max_replaces=getattr(cfg, "EXEC_MAX_REPLACE", 2),
                    reprice_pct=getattr(cfg, "EXEC_REPRICE_PCT", 0.002),
                    max_chase_pct=getattr(cfg, "EXEC_MAX_CHASE_PCT", 0.002),
                    max_quote_age_sec=getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0),
                    max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.015),
                    spread_widen_pct=getattr(cfg, "EXEC_SPREAD_WIDEN_PCT", 0.5),
                )

            fill_ratio = 1.0 if filled else 0.0
            if report:
                req = report.get("requested_qty") or getattr(trade, "qty", 1)
                got = report.get("fill_qty")
                if req and got is not None:
                    fill_ratio = max(0.0, min(float(got) / max(float(req), 1.0), 1.0))
            try:
                insert_execution_stat({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "instrument": trade.instrument,
                    "slippage_bps": self.engine.slippage_bps,
                    "latency_ms": 0,
                    "fill_ratio": fill_ratio,
                })
            except Exception as exc:
                logger.warning("execution_stat_error err=%s", exc)
            self._record_fill_quality(trade, bid, ask, limit_price, start_ts, filled, price, report)
            if filled and report:
                self.engine.calibrate_slippage(report.get("slippage"), instrument=getattr(trade, "instrument", "OPT"))

            if filled:
                requested_qty = report.get("requested_qty") if isinstance(report, dict) else None
                fill_qty = report.get("fill_qty") if isinstance(report, dict) else None
                next_state = OrderState.FILLED
                try:
                    if requested_qty and fill_qty is not None and float(fill_qty) < float(requested_qty):
                        next_state = OrderState.PARTIAL
                except Exception:
                    next_state = OrderState.FILLED
                _transition(
                    next_state,
                    reason="fill_confirmed",
                    filled_qty=fill_qty,
                    slippage=(report or {}).get("slippage"),
                    time_to_fill_sec=round(max(time.time() - start_ts, 0.0), 6),
                )
                if mode == "PAPER" and next_state == OrderState.FILLED:
                    self._record_paper_execution_outcome(
                        trade=trade,
                        order=current_order,
                        terminal_state=next_state,
                        reason="fill_confirmed",
                        report=report or {},
                        fill_price=price,
                        slippage=(report or {}).get("slippage"),
                    )
                try:
                    from core.reconciliation import emit_execution_fill_event

                    qty_value = fill_qty if fill_qty is not None else getattr(trade, "qty", None)
                    emit_execution_fill_event(
                        order_id=current_order.order_id if current_order is not None else getattr(trade, "order_id", None),
                        broker_order_id=current_order.broker_order_id if current_order is not None else getattr(trade, "broker_order_id", None),
                        trade_id=getattr(trade, "trade_id", None),
                        symbol=getattr(trade, "symbol", None) or getattr(trade, "instrument", None),
                        side=getattr(trade, "side", None),
                        qty=qty_value,
                        price=price,
                        ts_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        run_id=getattr(trade, "run_id", None) or getattr(cfg, "RUN_ID", None) or getattr(cfg, "EXEC_RUN_ID", None),
                        desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
                        mode=mode,
                    )
                except Exception as exc:
                    logger.warning("execution_fill_event_warn err=%s", exc)
                append_execution_audit_event(
                    trade=trade,
                    order_action=next_state.value,
                    guard_result=guard.as_dict() if 'guard' in locals() and guard is not None else None,
                    broker_response=report or {},
                    reason="fill_confirmed",
                )
                return filled, price, _report(report or {})

            abort_reason = "execution_aborted"
            if isinstance(report, dict):
                abort_reason = str(report.get("reason_if_aborted") or abort_reason)
            return _abort(abort_reason, extra=report or {})

        if mode == "LIVE":
            if not getattr(cfg, "ALLOW_LIVE_PLACEMENT", False):
                return _abort("live_placement_disabled", note="live placement disabled")
            _transition(OrderState.SENT, reason="order_sent")
            try:
                require_approval_or_abort(
                    order_intent,
                    mode=mode,
                    now=time.time(),
                    approver=getattr(trade, "approved_by", None),
                    ttl=int(getattr(cfg, "ORDER_APPROVAL_TTL_SEC", getattr(cfg, "APPROVAL_TTL_SEC", 600))),
                )
            except ApprovalMissingOrInvalid as exc:
                return _abort(
                    exc.reason,
                    note=f"manual_approval_blocked:{exc.reason}",
                    extra={"approval_payload_hash": payload_hash},
                )
            _transition(OrderState.ACKNOWLEDGED, reason="approval_consumed")
            if self._use_legacy_feed_gate and hasattr(self.feed_health, "gate_live_entries"):
                try:
                    allowed, _legacy_reason, feed_snapshot = self.feed_health.gate_live_entries(
                        advisory_only=False
                    )
                    state_text = str(
                        getattr(getattr(feed_snapshot, "state", None), "value", "UNKNOWN")
                    ).upper()
                    gate_reason = (
                        f"feed_state_{state_text}"
                        if state_text in {"DEGRADED", "DOWN"}
                        else "ok"
                    )
                    gate_details = {
                        "reason": str(getattr(feed_snapshot, "reason", "") or _legacy_reason),
                        "group_key": "LEGACY_MONITOR",
                    }
                except Exception:
                    allowed, gate_reason, state_text, gate_details = (
                        False,
                        "feed_state_UNKNOWN",
                        "DOWN",
                        {"reason": "feed_gate_error"},
                    )
            else:
                try:
                    allowed, gate_reason, state_text, gate_details = check_execution_allowed(
                        getattr(trade, "symbol", None) or getattr(trade, "instrument", None)
                    )
                except Exception:
                    allowed, gate_reason, state_text, gate_details = (
                        False,
                        "feed_state_UNKNOWN",
                        "DOWN",
                        {"reason": "feed_gate_error"},
                    )
            if not allowed:
                feed_reason = str(gate_details.get("reason") or gate_reason)
                if state_text == "DOWN":
                    try:
                        self.feed_health.maybe_trigger_reconnect(reason_prefix="execution_router_live_block")
                    except Exception:
                        pass
                return _abort(
                    gate_reason,
                    note=f"{gate_reason}:{feed_reason}",
                    extra={
                        "feed_state": state_text,
                        "feed_reason": feed_reason,
                        "feed_group": gate_details.get("group_key"),
                    },
                )
            live_snapshot = None
            if snapshot_fn is not None and callable(snapshot_fn):
                try:
                    live_snapshot = snapshot_fn()
                except Exception:
                    live_snapshot = None
            effective_bid = bid if bid is not None else (live_snapshot or {}).get("bid")
            effective_ask = ask if ask is not None else (live_snapshot or {}).get("ask")
            guard = evaluate_execution_guard(
                side=getattr(trade, "side", None),
                bid=effective_bid,
                ask=effective_ask,
                snapshot=live_snapshot,
                evaluated_at_epoch=time.time(),
                max_quote_age_sec=getattr(cfg, "LIVE_MAX_QUOTE_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0)),
                max_spread_pct=getattr(cfg, "EXEC_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.015)),
                reference_price=getattr(trade, "entry_price", None),
            )
            if not guard.execution_allowed:
                return _abort(
                    guard.reasons[0] if guard.reasons else "execution_guard_failed",
                    extra=guard.as_dict(),
                )
            self._record_intent(
                trade,
                bid,
                ask,
                volume,
                depth=depth,
                note="live placement requested",
                execution_plan=execution_plan,
            )
            return _abort("live_not_implemented")

        return _abort("unknown_execution_mode")

    def _open_order_record(self, trade, order_intent):
        requested_order_id = str(getattr(trade, "order_id", "") or "").strip()
        order_id = requested_order_id or f"ord_{uuid.uuid4().hex}"
        requested_idem = str(getattr(trade, "idempotency_key", "") or "").strip()
        idempotency_key = requested_idem or f"{order_intent.order_intent_hash()}:{order_id}"
        broker_order_id = str(getattr(trade, "broker_order_id", "") or "").strip() or None
        instrument_key = str(getattr(trade, "symbol", None) or getattr(trade, "instrument", None) or "UNKNOWN")
        return self.engine.create_order(
            order_id=order_id,
            idempotency_key=idempotency_key,
            broker_order_id=broker_order_id,
            instrument=instrument_key,
            side=getattr(trade, "side", None),
            requested_qty=getattr(trade, "qty", None),
        )

    @staticmethod
    def _terminal_state_for_reason(reason):
        text = str(reason or "").strip()
        if text.startswith("manual_approval_required"):
            return OrderState.REJECTED
        if text.startswith("readiness_gate_fail"):
            return OrderState.REJECTED
        if text.startswith("freshness_sla_failed"):
            return OrderState.REJECTED
        if text.startswith("non_tradable"):
            return OrderState.REJECTED
        if text in {"timeout", "stale_quote", "no_quote", "missing_quote_ts"}:
            return OrderState.EXPIRED
        if text in {"spread_widened", "spread_too_wide", "max_chase_exceeded"}:
            return OrderState.CANCELLED
        return OrderState.REJECTED

    def _record_paper_execution_outcome(
        self,
        *,
        trade,
        order,
        terminal_state,
        reason,
        report=None,
        fill_price=None,
        slippage=None,
    ):
        state_text = getattr(terminal_state, "value", terminal_state)
        terminal_status = {
            "FILLED": "executed",
            "REJECTED": "rejected-saved-loss",
            "CANCELLED": "timed-exit",
            "EXPIRED": "expired-no-move",
        }.get(str(state_text).upper())
        if terminal_status is None:
            return None
        payload = {
            "candidate_id": getattr(trade, "trade_id", None) or getattr(order, "order_id", None),
            "paper_intent_id": getattr(order, "order_id", None),
            "strategy_family": getattr(trade, "strategy_family", None) or getattr(trade, "strategy", None),
            "regime": getattr(trade, "regime", None),
            "direction_family": getattr(trade, "direction_family", None) or getattr(trade, "direction", None) or getattr(trade, "side", None),
            "terminal_status": terminal_status,
            "candidate_class": getattr(trade, "candidate_type", None) or getattr(trade, "candidate_status", None),
            "selector_outcome": getattr(trade, "selector_outcome", None),
            "signal_score": getattr(trade, "signal_score", None),
            "execution_score": getattr(trade, "execution_score", None),
            "priority_score": getattr(trade, "priority_score", None),
            "final_score": getattr(trade, "final_score", None) or getattr(trade, "opportunity_score", None) or getattr(trade, "trade_score", None),
            "simulation_status": str(state_text).upper(),
            "fill_status": (report or {}).get("fill_status") if isinstance(report, dict) else None,
            "simulated_pnl": (report or {}).get("simulated_pnl") if isinstance(report, dict) else None,
            "slippage_cost": abs(_safe_float(slippage) or 0.0),
            "slippage_adjusted_pnl": (report or {}).get("slippage_adjusted_pnl") if isinstance(report, dict) else None,
            "exit_reason": str(reason or terminal_status),
            "realized_r_multiple": (report or {}).get("realized_r_multiple") if isinstance(report, dict) else None,
            "source": "execution_router_paper_runtime",
            "reason": str(reason or terminal_status),
            "mode": "PAPER",
            "metadata": {
                "order_id": getattr(order, "order_id", None),
                "idempotency_key": getattr(order, "idempotency_key", None),
                "fill_price": fill_price,
                "runtime_terminal_state": str(state_text).upper(),
                "entry_order_outcome_only": True,
            },
        }
        payload = attach_runtime_setup_identity(payload, trade)
        try:
            return record_paper_outcome(payload)
        except Exception as exc:
            if not self._paper_outcome_write_warned:
                self._paper_outcome_write_warned = True
                logger.warning("paper_outcome_journal_write_failed err=%s", exc)
            return None

    def _simulate_limit(self, trade, bid, ask, limit_price, snapshot_fn=None):
        if snapshot_fn is None or not callable(snapshot_fn):
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote_fn",
            }
        return self.paper_sim.simulate(
            trade,
            limit_price,
            snapshot_fn,
            max_replaces=getattr(cfg, "EXEC_MAX_REPLACE", 2),
            reprice_pct=getattr(cfg, "EXEC_REPRICE_PCT", 0.002),
            max_chase_pct=getattr(cfg, "EXEC_MAX_CHASE_PCT", 0.002),
            max_quote_age_sec=getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0),
            max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.015),
            spread_widen_pct=getattr(cfg, "EXEC_SPREAD_WIDEN_PCT", 0.5),
        )

    def _record_fill_quality(self, trade, bid, ask, limit_price, start_ts, filled, fill_price, report):
        decision_mid = None
        decision_spread = None
        if bid and ask:
            decision_mid = round((bid + ask) / 2.0, 2)
            decision_spread = round(max(ask - bid, 0.0), 4)
        slippage_vs_mid = None
        if fill_price is not None and decision_mid is not None:
            if trade.side == "BUY":
                slippage_vs_mid = round(fill_price - decision_mid, 4)
            else:
                slippage_vs_mid = round(decision_mid - fill_price, 4)
        time_to_fill = None
        if start_ts:
            time_to_fill = round(time.time() - start_ts, 4)
        payload = {
            "ts": time.time(),
            "trade_id": getattr(trade, "trade_id", None),
            "symbol": getattr(trade, "symbol", None),
            "instrument": getattr(trade, "instrument", None),
            "side": getattr(trade, "side", None),
            "decision_bid": bid,
            "decision_ask": ask,
            "decision_mid": decision_mid,
            "decision_spread": decision_spread,
            "limit_price": limit_price,
            "fill_price": fill_price if filled else None,
            "not_filled_reason": report.get("reason_if_aborted") if report else None,
            "time_to_fill": time_to_fill if filled else None,
            "slippage_vs_mid": slippage_vs_mid if filled else None,
        }
        if report:
            payload.update({
                "queue_position": report.get("queue_position"),
                "queue_priority": report.get("queue_priority"),
                "urgency": report.get("urgency"),
                "urgency_score": report.get("urgency_score"),
                "impact_estimate": report.get("impact_estimate"),
                "vwap": report.get("vwap"),
                "alpha_decay": report.get("alpha_decay"),
                "adverse_selection": report.get("adverse_selection"),
                "implementation_shortfall": report.get("implementation_shortfall"),
                "opportunity_cost": report.get("opportunity_cost"),
                "execution_quality_score": report.get("execution_quality_score"),
                "fill_status": report.get("fill_status"),
                "fill_qty": report.get("fill_qty"),
                "requested_qty": report.get("requested_qty"),
                "latency_ms": report.get("latency_ms"),
                "slippage_bp": report.get("slippage_bp"),
            })
        if payload.get("execution_quality_score") is None:
            payload["execution_quality_score"] = execution_quality_score(payload)
        log_fill_quality(payload)

    def _record_intent(self, trade, bid, ask, volume, depth=None, note="live placement disabled", execution_plan=None):
        try:
            path = Path(
                str(
                    getattr(cfg, "EXECUTION_INTENTS_LOG_PATH", str(logs_dir() / "execution_intents.jsonl"))
                    or str(logs_dir() / "execution_intents.jsonl")
                )
            )
            payload = {
                "ts": time.time(),
                "trade_id": getattr(trade, "trade_id", None),
                "symbol": getattr(trade, "symbol", None),
                "instrument": getattr(trade, "instrument", None),
                "side": getattr(trade, "side", None),
                "entry": getattr(trade, "entry_price", None),
                "qty": getattr(trade, "qty", None),
                "bid": bid,
                "ask": ask,
                "volume": volume,
                "depth_top": None,
                "note": note,
                "snapshot_id": getattr(execution_plan, "snapshot_id", None),
                "decision_id": getattr(execution_plan, "decision_id", None),
            }
            try:
                if depth and isinstance(depth, dict):
                    b = depth.get("buy", [{}])[0].get("price")
                    a = depth.get("sell", [{}])[0].get("price")
                    payload["depth_top"] = {"bid": b, "ask": a}
            except Exception:
                pass
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.touch()
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as exc:
            warn_once = bool(getattr(cfg, "EXECUTION_INTENTS_LOG_WARN_ONCE", False))
            if warn_once and (not self._intent_log_write_warned):
                self._intent_log_write_warned = True
                logger.warning("execution_intent_error err=%s", exc)
