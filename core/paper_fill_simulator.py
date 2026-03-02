from __future__ import annotations

import time
import uuid

from config import config as cfg
from core.events import append_event
from core.execution_quality import (
    adverse_selection,
    alpha_decay,
    classify_urgency,
    depth_weighted_impact,
    estimate_queue_position,
    execution_quality_score,
    implementation_shortfall,
    opportunity_cost,
)
from core.fill_realism import FillRealismEngine, FillRequest
from core.time_utils import normalize_epoch_seconds


class PaperFillSimulator:
    """
    Strict paper-fill simulator using sequential quote snapshots.

    Legacy mode:
    - BUY fills if limit >= ask at any snapshot before timeout
    - SELL fills if limit <= bid at any snapshot before timeout
    - Otherwise: no fill (timeout)

    Realism mode:
    - routes each quote through FillRealismEngine
    - emits canonical order/fill/reject/open events
    """

    def __init__(self, timeout_sec=3.0, poll_sec=0.25):
        self.timeout_sec = timeout_sec
        self.poll_sec = poll_sec
        self._fill_realism_engine: FillRealismEngine | None = None
        self._fill_realism_seed: int | None = None

    @staticmethod
    def _snapshot_reader(snapshot_stream):
        if callable(snapshot_stream):
            return snapshot_stream
        iterator = iter(snapshot_stream)

        def _next_snapshot():
            try:
                return next(iterator)
            except StopIteration:
                return None

        return _next_snapshot

    @staticmethod
    def _coerce_qty(trade) -> float:
        try:
            qty = float(getattr(trade, "qty", 1) or 1)
        except Exception:
            qty = 1.0
        return max(qty, 1.0)

    @staticmethod
    def _symbol(trade) -> str:
        return str(getattr(trade, "symbol", None) or getattr(trade, "instrument", None) or "UNKNOWN")

    @staticmethod
    def _mode() -> str:
        return str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper()

    def _fill_realism_enabled(self) -> bool:
        mode = self._mode()
        default_enabled = mode in {"SIM", "PAPER"}
        return bool(getattr(cfg, "FILL_REALISM_ENABLED", default_enabled))

    def _realism_engine(self) -> FillRealismEngine:
        seed = int(getattr(cfg, "FILL_REALISM_SEED", 20260227))
        if self._fill_realism_engine is None or self._fill_realism_seed != seed:
            self._fill_realism_engine = FillRealismEngine(cfg, rng_seed=seed)
            self._fill_realism_seed = seed
        return self._fill_realism_engine

    @staticmethod
    def _normalize_abort_reason(reason: str | None) -> str:
        if not reason:
            return "execution_aborted"
        mapping = {
            "STALE_QUOTE": "stale_quote",
            "SPREAD_TOO_WIDE": "spread_too_wide",
            "LIMIT_SLIPPED": "limit_slipped",
            "LIMIT_NOT_CROSSED": "timeout",
            "INSUFFICIENT_LIQUIDITY": "insufficient_liquidity",
            "NO_PRICE": "no_quote",
            "INVALID_LIMIT": "invalid_limit_price",
        }
        text = str(reason).strip().upper()
        return mapping.get(text, text.lower())

    def _emit_order_submitted(self, trade, order_id: str, limit_price: float | None) -> None:
        append_event(
            "order_submitted",
            {
                "order_id": str(order_id),
                "trade_id": str(getattr(trade, "trade_id", "") or ""),
                "symbol": self._symbol(trade),
                "side": str(getattr(trade, "side", "BUY") or "BUY").upper(),
                "qty": float(self._coerce_qty(trade)),
                "limit_price": float(limit_price) if limit_price is not None else None,
                "order_type": str(getattr(trade, "order_type", "LIMIT") or "LIMIT").upper(),
                "run_id": str(getattr(trade, "run_id", None) or getattr(cfg, "RUN_ID", "") or ""),
                "desk_id": str(getattr(cfg, "DESK_ID", "DEFAULT")),
                "mode": self._mode(),
            },
        )

    def _emit_fill_events(
        self,
        trade,
        order_id: str,
        result,
        requested_qty: float,
        mode: str,
        *,
        context: dict | None = None,
    ) -> None:
        partials = list(result.partial_fills or [])
        if not partials and result.filled_qty > 0 and result.avg_price is not None:
            partials = [{"fill_id": "fill-1", "qty": float(result.filled_qty), "price": float(result.avg_price)}]
        ctx = dict(context or {})
        for idx, fill in enumerate(partials, start=1):
            qty = float(fill.get("qty") or 0.0)
            px = float(fill.get("price") or result.avg_price or 0.0)
            if qty <= 0 or px <= 0:
                continue
            slippage = float(ctx.get("slippage") or 0.0)
            spread = ctx.get("spread")
            spread_bps = ctx.get("spread_bps")
            if spread_bps is None and spread is not None and px > 0:
                try:
                    spread_bps = float(spread) / float(px) * 10000.0
                except Exception:
                    spread_bps = None
            slippage_bp = ctx.get("slippage_bp")
            if slippage_bp is None and slippage is not None and px > 0:
                try:
                    slippage_bp = float(slippage) / float(px) * 10000.0
                except Exception:
                    slippage_bp = None
            append_event(
                "fill",
                {
                    "order_id": str(order_id),
                    "fill_id": str(fill.get("fill_id") or f"fill-{idx}"),
                    "trade_id": str(getattr(trade, "trade_id", "") or ""),
                    "symbol": self._symbol(trade),
                    "side": str(getattr(trade, "side", "BUY") or "BUY").upper(),
                    "qty": qty,
                    "price": px,
                    "run_id": str(getattr(trade, "run_id", None) or getattr(cfg, "RUN_ID", "") or ""),
                    "desk_id": str(getattr(cfg, "DESK_ID", "DEFAULT")),
                    "mode": str(mode),
                    "order_type": str(getattr(trade, "order_type", "LIMIT") or "LIMIT").upper(),
                    "strategy": str(getattr(trade, "strategy", "") or ""),
                    "spread": spread,
                    "spread_bps": spread_bps,
                    "slippage": slippage,
                    "slippage_bp": slippage_bp,
                    "latency_ms": ctx.get("latency_ms"),
                    "quote_age_ms": ctx.get("quote_age_ms"),
                },
            )

        remaining_qty = max(float(requested_qty) - float(result.filled_qty or 0.0), 0.0)
        if remaining_qty > 0:
            append_event(
                "order_open",
                {
                    "order_id": str(order_id),
                    "trade_id": str(getattr(trade, "trade_id", "") or ""),
                    "symbol": self._symbol(trade),
                    "side": str(getattr(trade, "side", "BUY") or "BUY").upper(),
                    "filled_qty": float(result.filled_qty or 0.0),
                    "remaining_qty": float(remaining_qty),
                    "reason": str(result.reject_reason or "partial_fill"),
                    "run_id": str(getattr(trade, "run_id", None) or getattr(cfg, "RUN_ID", "") or ""),
                    "desk_id": str(getattr(cfg, "DESK_ID", "DEFAULT")),
                    "mode": str(mode),
                    "strategy": str(getattr(trade, "strategy", "") or ""),
                },
            )

    def _emit_order_rejected(self, trade, order_id: str, reason: str | None) -> None:
        append_event(
            "order_rejected",
            {
                "order_id": str(order_id),
                "trade_id": str(getattr(trade, "trade_id", "") or ""),
                "symbol": self._symbol(trade),
                "side": str(getattr(trade, "side", "BUY") or "BUY").upper(),
                "qty": float(self._coerce_qty(trade)),
                "reason": str(reason or "execution_aborted"),
                "run_id": str(getattr(trade, "run_id", None) or getattr(cfg, "RUN_ID", "") or ""),
                "desk_id": str(getattr(cfg, "DESK_ID", "DEFAULT")),
                "mode": self._mode(),
            },
        )

    def _simulate_with_realism(
        self,
        trade,
        limit_price,
        snapshot_stream,
        max_replaces=2,
        reprice_pct=0.002,
        max_chase_pct=0.002,
        max_quote_age_sec=None,
        max_spread_pct=None,
        spread_widen_pct=None,
    ):
        if snapshot_stream is None:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
            }

        next_snapshot = self._snapshot_reader(snapshot_stream)
        engine = self._realism_engine()
        requested_qty = float(self._coerce_qty(trade))
        mode = self._mode()
        order_id = str(getattr(trade, "order_id", None) or f"paper-{uuid.uuid4().hex[:12]}")
        self._emit_order_submitted(trade, order_id, limit_price)

        start = time.time()
        first_bid = None
        first_ask = None
        decision_mid = None
        decision_spread = None
        last_mid = None
        first_depth = None
        attempts = []
        current_limit = limit_price
        replaces = 0
        last_open_reason = "timeout"

        while time.time() - start <= self.timeout_sec:
            snap = next_snapshot()
            if not snap:
                time.sleep(self.poll_sec)
                continue

            bid = snap.get("bid")
            ask = snap.get("ask")
            ltp = snap.get("ltp")
            ts_value = snap.get("ts")
            ts_epoch = normalize_epoch_seconds(ts_value)
            now_ts = time.time()
            if ts_epoch is None:
                ts_epoch = now_ts
            spread = None
            try:
                bid_f = float(bid) if bid is not None else None
                ask_f = float(ask) if ask is not None else None
                if bid_f is not None and ask_f is not None:
                    spread = max(ask_f - bid_f, 0.0)
            except Exception:
                bid_f = None
                ask_f = None

            if first_bid is None and bid_f is not None and ask_f is not None:
                first_bid = bid_f
                first_ask = ask_f
                decision_mid = (first_bid + first_ask) / 2.0
                decision_spread = max(first_ask - first_bid, 0.0)
                first_depth = snap.get("depth")

            if bid_f is not None and ask_f is not None:
                last_mid = (bid_f + ask_f) / 2.0

            attempts.append(
                {
                    "ts": ts_epoch,
                    "bid": bid_f,
                    "ask": ask_f,
                    "spread": round(float(spread or 0.0), 6),
                }
            )

            if max_quote_age_sec is not None and (now_ts - ts_epoch) > max_quote_age_sec:
                reason = "stale_quote"
                self._emit_order_rejected(trade, order_id, reason)
                return False, None, {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": reason,
                    "attempts": attempts,
                    "fill_status": "REJECTED",
                    "fill_qty": 0,
                    "requested_qty": requested_qty,
                }

            if max_spread_pct is not None and decision_mid and spread is not None:
                if decision_mid > 0 and (spread / decision_mid) > max_spread_pct:
                    reason = "spread_too_wide"
                    self._emit_order_rejected(trade, order_id, reason)
                    return False, None, {
                        "decision_mid": round(decision_mid, 2),
                        "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                        "fill_price": None,
                        "slippage": None,
                        "reason_if_aborted": reason,
                        "attempts": attempts,
                        "fill_status": "REJECTED",
                        "fill_qty": 0,
                        "requested_qty": requested_qty,
                    }

            if spread_widen_pct and decision_spread is not None and spread is not None:
                if spread > decision_spread * (1 + spread_widen_pct):
                    reason = "spread_widened"
                    self._emit_order_rejected(trade, order_id, reason)
                    return False, None, {
                        "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                        "decision_spread": round(decision_spread, 4),
                        "fill_price": None,
                        "slippage": None,
                        "reason_if_aborted": reason,
                        "attempts": attempts,
                        "fill_status": "REJECTED",
                        "fill_qty": 0,
                        "requested_qty": requested_qty,
                    }

            if reprice_pct and replaces < max_replaces and decision_mid and bid_f and ask_f:
                side = str(getattr(trade, "side", "BUY") or "BUY").upper()
                if side == "BUY" and ask_f > current_limit and ask_f <= decision_mid * (1 + max_chase_pct):
                    current_limit = ask_f * (1 + reprice_pct)
                    replaces += 1
                elif side == "SELL" and bid_f < current_limit and bid_f >= decision_mid * (1 - max_chase_pct):
                    current_limit = bid_f * (1 - reprice_pct)
                    replaces += 1

            req = FillRequest(
                symbol=self._symbol(trade),
                side=str(getattr(trade, "side", "BUY") or "BUY").upper(),
                qty=requested_qty,
                order_type=str(getattr(trade, "order_type", "LIMIT") or "LIMIT").upper(),
                limit_price=float(current_limit) if current_limit is not None else None,
                ts=ts_epoch,
                ltp=float(ltp) if ltp is not None else (last_mid if last_mid is not None else None),
                bid=bid_f,
                ask=ask_f,
                spread=spread,
                depth=snap.get("depth") if isinstance(snap.get("depth"), dict) else first_depth,
                volatility=snap.get("volatility", snap.get("vol_z")),
                latency_ms=int(getattr(cfg, "LATENCY_MS", 120)),
            )
            result = engine.simulate_fill(req)

            if result.status in {"FILLED", "PARTIAL"} and result.filled_qty > 0:
                time_to_fill = round(max(time.time() - start, 0.0), 4)
                self._emit_fill_events(
                    trade,
                    order_id,
                    result,
                    requested_qty=requested_qty,
                    mode=mode,
                    context={
                        "spread": req.spread,
                        "spread_bps": (float(req.spread or 0.0) / float(result.avg_price) * 10000.0)
                        if req.spread is not None and result.avg_price
                        else None,
                        "slippage": float(result.slippage or 0.0),
                        "slippage_bp": (
                            float(result.slippage or 0.0) / float(result.avg_price) * 10000.0
                            if result.avg_price
                            else None
                        ),
                        "latency_ms": req.latency_ms,
                        "quote_age_ms": (result.debug or {}).get("quote_age_ms"),
                    },
                )
                slippage = float(result.slippage or 0.0)
                mid_for_bp = decision_mid if decision_mid and decision_mid > 0 else (last_mid or 0.0)
                slippage_bp = (slippage / mid_for_bp * 10000.0) if mid_for_bp and mid_for_bp > 0 else 0.0
                report = {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": round(float(result.avg_price or 0.0), 2),
                    "slippage": round(slippage, 6),
                    "time_to_fill": time_to_fill,
                    "reason_if_aborted": None,
                    "attempts": attempts,
                    "queue_position": None,
                    "queue_priority": None,
                    "urgency": None,
                    "urgency_score": None,
                    "impact_estimate": None,
                    "vwap": round(last_mid, 4) if last_mid is not None else None,
                    "participation_rate": None,
                    "alpha_decay": None,
                    "adverse_selection": None,
                    "implementation_shortfall": None,
                    "opportunity_cost": None,
                    "execution_quality_score": None,
                    "fill_status": result.status,
                    "fill_qty": float(result.filled_qty),
                    "requested_qty": float(requested_qty),
                    "latency_ms": int(req.latency_ms or 0),
                    "slippage_bp": round(float(slippage_bp), 4),
                    "partial_fills": result.partial_fills,
                    "reject_reason": result.reject_reason,
                    "slippage_components": (result.debug or {}).get("slippage_components"),
                }
                report["execution_quality_score"] = execution_quality_score(report)
                return True, round(float(result.avg_price or 0.0), 2), report

            if result.status == "REJECTED":
                reason = self._normalize_abort_reason(result.reject_reason)
                self._emit_order_rejected(trade, order_id, reason)
                report = {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": reason,
                    "attempts": attempts,
                    "fill_status": "REJECTED",
                    "fill_qty": 0,
                    "requested_qty": float(requested_qty),
                    "latency_ms": int(req.latency_ms or 0),
                    "reject_reason": result.reject_reason,
                    "slippage_components": (result.debug or {}).get("slippage_components"),
                }
                return False, None, report

            if result.status == "OPEN":
                last_open_reason = self._normalize_abort_reason(result.reject_reason)

            time.sleep(self.poll_sec)

        self._emit_order_rejected(trade, order_id, last_open_reason or "timeout")
        if first_bid is None or first_ask is None:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
                "attempts": attempts,
                "fill_status": "REJECTED",
                "fill_qty": 0,
                "requested_qty": float(requested_qty),
            }
        return False, None, {
            "decision_mid": round((first_bid + first_ask) / 2.0, 2),
            "decision_spread": round(max(first_ask - first_bid, 0.0), 4),
            "fill_price": None,
            "slippage": None,
            "reason_if_aborted": last_open_reason or "timeout",
            "attempts": attempts,
            "fill_status": "REJECTED",
            "fill_qty": 0,
            "requested_qty": float(requested_qty),
        }

    def _simulate_legacy(
        self,
        trade,
        limit_price,
        snapshot_stream,
        max_replaces=2,
        reprice_pct=0.002,
        max_chase_pct=0.002,
        max_quote_age_sec=None,
        max_spread_pct=None,
        spread_widen_pct=None,
    ):
        if snapshot_stream is None:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
            }

        _next_snapshot = self._snapshot_reader(snapshot_stream)
        start = time.time()
        first_bid = None
        first_ask = None
        first_depth = None
        decision_mid = None
        decision_spread = None
        mid_at_fill = None
        mid_after = None
        last_mid = None
        vwap_sum = 0.0
        vwap_n = 0
        replaces = 0
        current_limit = limit_price
        attempts = []

        while time.time() - start <= self.timeout_sec:
            snap = _next_snapshot()
            if not snap:
                time.sleep(self.poll_sec)
                continue

            bid = snap.get("bid") or 0
            ask = snap.get("ask") or 0
            ts = snap.get("ts")
            if ts is None:
                ts = time.time()
            if bid <= 0 or ask <= 0:
                time.sleep(self.poll_sec)
                continue
            depth = snap.get("depth")
            if first_depth is None:
                first_depth = depth

            if first_bid is None:
                first_bid = bid
                first_ask = ask
                decision_mid = (first_bid + first_ask) / 2.0
                decision_spread = max(first_ask - first_bid, 0.0)

            mid = (bid + ask) / 2.0
            last_mid = mid
            vwap_sum += mid
            vwap_n += 1
            spread = max(ask - bid, 0.0)
            attempts.append(
                {
                    "ts": ts,
                    "bid": bid,
                    "ask": ask,
                    "spread": round(spread, 6),
                }
            )
            if ts is None:
                return False, None, {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "missing_quote_ts",
                    "attempts": attempts,
                }
            if max_quote_age_sec is not None and (time.time() - ts) > max_quote_age_sec:
                return False, None, {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "stale_quote",
                    "attempts": attempts,
                }
            if max_spread_pct is not None and decision_mid and (spread / decision_mid) > max_spread_pct:
                return False, None, {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "spread_too_wide",
                    "attempts": attempts,
                }
            if spread_widen_pct and decision_spread is not None and spread > decision_spread * (1 + spread_widen_pct):
                return False, None, {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "spread_widened",
                    "attempts": attempts,
                }

            if reprice_pct and replaces < max_replaces:
                if trade.side == "BUY" and ask > current_limit and ask <= decision_mid * (1 + max_chase_pct):
                    current_limit = ask * (1 + reprice_pct)
                    replaces += 1
                elif trade.side == "SELL" and bid < current_limit and bid >= decision_mid * (1 - max_chase_pct):
                    current_limit = bid * (1 - reprice_pct)
                    replaces += 1

            if trade.side == "BUY" and current_limit >= ask:
                mid_at_fill = mid
                fill_price = ask
                time_to_fill = time.time() - start
                urgency, urgency_score = classify_urgency(
                    getattr(trade, "confidence", None),
                    getattr(trade, "time_to_expiry_hrs", None),
                    (decision_spread / decision_mid) if decision_mid else None,
                )
                qty = getattr(trade, "qty", 1)
                queue = estimate_queue_position(first_depth, trade.side, current_limit, qty)
                impact = depth_weighted_impact(depth, trade.side, getattr(trade, "qty", 1), decision_spread)
                participation = None
                try:
                    if depth:
                        book = depth.get("sell") if trade.side == "BUY" else depth.get("buy")
                        total = 0.0
                        for level in (book or [])[:3]:
                            total += float(level.get("quantity", 0) or 0)
                        total = max(total, 1.0)
                        participation = round(qty / total, 4)
                except Exception:
                    participation = None
                report = {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": round(fill_price, 2),
                    "slippage": round(fill_price - decision_mid, 4) if decision_mid is not None else None,
                    "time_to_fill": round(time_to_fill, 4),
                    "reason_if_aborted": None,
                    "attempts": attempts,
                    "queue_position": queue.get("queue_position"),
                    "queue_priority": queue.get("queue_priority"),
                    "urgency": urgency,
                    "urgency_score": urgency_score,
                    "impact_estimate": impact,
                    "vwap": round(vwap_sum / max(vwap_n, 1), 4),
                    "participation_rate": participation,
                }
                mid_after = last_mid
                report["alpha_decay"] = alpha_decay(decision_mid, mid_at_fill, trade.side)
                report["adverse_selection"] = adverse_selection(mid_at_fill, mid_after, trade.side)
                report["implementation_shortfall"] = implementation_shortfall(decision_mid, fill_price, trade.side)
                report["opportunity_cost"] = opportunity_cost(decision_mid, mid_after, trade.side)
                report["execution_quality_score"] = execution_quality_score(report)
                return True, round(fill_price, 2), report

            if trade.side == "SELL" and current_limit <= bid:
                mid_at_fill = mid
                fill_price = bid
                time_to_fill = time.time() - start
                urgency, urgency_score = classify_urgency(
                    getattr(trade, "confidence", None),
                    getattr(trade, "time_to_expiry_hrs", None),
                    (decision_spread / decision_mid) if decision_mid else None,
                )
                qty = getattr(trade, "qty", 1)
                queue = estimate_queue_position(first_depth, trade.side, current_limit, qty)
                impact = depth_weighted_impact(depth, trade.side, getattr(trade, "qty", 1), decision_spread)
                participation = None
                try:
                    if depth:
                        book = depth.get("sell") if trade.side == "BUY" else depth.get("buy")
                        total = 0.0
                        for level in (book or [])[:3]:
                            total += float(level.get("quantity", 0) or 0)
                        total = max(total, 1.0)
                        participation = round(qty / total, 4)
                except Exception:
                    participation = None
                report = {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": round(fill_price, 2),
                    "slippage": round(decision_mid - fill_price, 4) if decision_mid is not None else None,
                    "time_to_fill": round(time_to_fill, 4),
                    "reason_if_aborted": None,
                    "attempts": attempts,
                    "queue_position": queue.get("queue_position"),
                    "queue_priority": queue.get("queue_priority"),
                    "urgency": urgency,
                    "urgency_score": urgency_score,
                    "impact_estimate": impact,
                    "vwap": round(vwap_sum / max(vwap_n, 1), 4),
                    "participation_rate": participation,
                }
                mid_after = last_mid
                report["alpha_decay"] = alpha_decay(decision_mid, mid_at_fill, trade.side)
                report["adverse_selection"] = adverse_selection(mid_at_fill, mid_after, trade.side)
                report["implementation_shortfall"] = implementation_shortfall(decision_mid, fill_price, trade.side)
                report["opportunity_cost"] = opportunity_cost(decision_mid, mid_after, trade.side)
                report["execution_quality_score"] = execution_quality_score(report)
                return True, round(fill_price, 2), report

            time.sleep(self.poll_sec)

        if first_bid is None or first_ask is None:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
            }

        decision_mid = (first_bid + first_ask) / 2.0
        decision_spread = max(first_ask - first_bid, 0.0)
        qty = getattr(trade, "qty", 1)
        queue = estimate_queue_position(first_depth, trade.side, current_limit, qty)
        urgency, urgency_score = classify_urgency(
            getattr(trade, "confidence", None),
            getattr(trade, "time_to_expiry_hrs", None),
            (decision_spread / decision_mid) if decision_mid else None,
        )
        report = {
            "decision_mid": round(decision_mid, 2),
            "decision_spread": round(decision_spread, 4),
            "fill_price": None,
            "slippage": None,
            "reason_if_aborted": "timeout",
            "attempts": attempts,
            "queue_position": queue.get("queue_position"),
            "queue_priority": queue.get("queue_priority"),
            "urgency": urgency,
            "urgency_score": urgency_score,
            "impact_estimate": None,
            "vwap": round(vwap_sum / max(vwap_n, 1), 4),
        }
        if last_mid is not None:
            report["opportunity_cost"] = opportunity_cost(decision_mid, last_mid, trade.side)
        report["execution_quality_score"] = execution_quality_score(report)
        return False, None, report

    def simulate(
        self,
        trade,
        limit_price,
        snapshot_stream,
        max_replaces=2,
        reprice_pct=0.002,
        max_chase_pct=0.002,
        max_quote_age_sec=None,
        max_spread_pct=None,
        spread_widen_pct=None,
    ):
        if self._fill_realism_enabled():
            return self._simulate_with_realism(
                trade,
                limit_price,
                snapshot_stream,
                max_replaces=max_replaces,
                reprice_pct=reprice_pct,
                max_chase_pct=max_chase_pct,
                max_quote_age_sec=max_quote_age_sec,
                max_spread_pct=max_spread_pct,
                spread_widen_pct=spread_widen_pct,
            )
        return self._simulate_legacy(
            trade,
            limit_price,
            snapshot_stream,
            max_replaces=max_replaces,
            reprice_pct=reprice_pct,
            max_chase_pct=max_chase_pct,
            max_quote_age_sec=max_quote_age_sec,
            max_spread_pct=max_spread_pct,
            spread_widen_pct=spread_widen_pct,
        )
