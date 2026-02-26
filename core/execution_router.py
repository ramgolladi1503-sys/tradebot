import time
import json
import uuid
from pathlib import Path
from config import config as cfg
from core.execution.chokepoint import ApprovalMissingOrInvalid, require_approval_or_abort
from core.execution_engine import ExecutionEngine
from core.paper_fill_simulator import PaperFillSimulator
from core.trade_store import insert_execution_stat
from core.fill_quality import log_fill_quality
from core.execution_quality import execution_quality_score
from core.orders.order_intent import OrderIntent
from core.orders.state_machine import OrderState
from core.readiness_gate import run_readiness_check
from core.freshness_sla import get_freshness_status

class ExecutionRouter:
    """
    Routes trades to SIM/PAPER/LIVE modes.
    LIVE mode is a stub until order placement is enabled.
    """
    def __init__(self):
        self.engine = ExecutionEngine()
        self.paper_sim = PaperFillSimulator(
            timeout_sec=getattr(cfg, "EXEC_SIM_TIMEOUT_SEC", 3.0),
            poll_sec=getattr(cfg, "EXEC_SIM_POLL_SEC", 0.25),
        )
        self._intent_log_write_warned = False

    def execute(self, trade, bid, ask, volume, depth=None, snapshot_fn=None, spread_pct=None, depth_imbalance=None, vol_z=None):
        mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
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
                self._record_intent(trade, bid, ask, volume, depth=depth, note=note)
            _transition(self._terminal_state_for_reason(reason), reason=reason)
            payload = {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": reason,
            }
            if extra:
                payload.update(extra)
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
            self._record_intent(trade, bid, ask, volume, depth=depth, note=f"{mode.lower()} intent")
            if snapshot_fn is None or not callable(snapshot_fn):
                return _abort("no_quote_fn")
            first = snapshot_fn()
            if not first:
                return _abort("no_quote")
            bid = first.get("bid", bid)
            ask = first.get("ask", ask)
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
                print(f"[EXECUTION_STAT_ERROR] {exc}")
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
            self._record_intent(trade, bid, ask, volume, depth=depth, note="live placement requested")
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

    def _record_intent(self, trade, bid, ask, volume, depth=None, note="live placement disabled"):
        try:
            path = Path(
                str(
                    getattr(cfg, "EXECUTION_INTENTS_LOG_PATH", "logs/execution_intents.jsonl")
                    or "logs/execution_intents.jsonl"
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
                print(f"[EXECUTION_INTENT_ERROR] {exc}")
