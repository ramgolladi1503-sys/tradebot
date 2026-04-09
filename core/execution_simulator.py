from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class ExecutionSimulatorConfig:
    max_spread_pct_for_market_fill: float = 0.80
    base_impact_bps: float = 4.0
    slippage_bps_floor: float = 2.0
    adverse_selection_bps: float = 3.0
    partial_fill_threshold_ratio: float = 0.35
    reject_fill_threshold_ratio: float = 1.10
    confidence_weight: float = 0.20
    liquidity_weight: float = 0.45
    spread_weight: float = 0.25
    depth_weight: float = 0.10


@dataclass(frozen=True)
class ExecutionRequest:
    symbol: str
    side: str
    quantity: int
    ltp: float
    best_bid: float
    best_ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    spread_pct: float = 0.0
    liquidity_score: float = 0.0
    execution_score: float = 0.0
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionEstimate:
    symbol: str
    side: str
    quantity: int
    fill_price: float | None
    fill_probability: float
    expected_filled_quantity: int
    status: str
    slippage_bps: float
    slippage_value: float
    market_impact_bps: float
    adverse_selection_bps: float
    queue_ahead_ratio: float
    notes: tuple[str, ...] = field(default_factory=tuple)


class ExecutionSimulator:
    def __init__(self, config: ExecutionSimulatorConfig | None = None):
        self.config = config or ExecutionSimulatorConfig()

    def estimate(self, request: ExecutionRequest) -> ExecutionEstimate:
        cfg = self.config
        side = str(request.side or "BUY").upper()
        qty = max(0, int(request.quantity or 0))
        bid = max(0.0, float(request.best_bid or 0.0))
        ask = max(0.0, float(request.best_ask or 0.0))
        ltp = max(0.0, float(request.ltp or 0.0))
        spread_pct = float(request.spread_pct or self._spread_pct(bid, ask))
        top_size = float(request.ask_size if side == "BUY" else request.bid_size or 0.0)
        queue_ratio = self._queue_ratio(qty, top_size)
        fill_probability = self._fill_probability(request, queue_ratio, spread_pct)
        market_impact_bps = self._market_impact_bps(qty, top_size)
        adverse_bps = float(cfg.adverse_selection_bps)
        slippage_bps = float(cfg.slippage_bps_floor) + market_impact_bps + adverse_bps
        status = "filled"
        expected_qty = qty
        notes: list[str] = []

        if queue_ratio >= float(cfg.reject_fill_threshold_ratio):
            status = "rejected"
            fill_probability = min(fill_probability, 0.10)
            expected_qty = 0
            notes.append("book_too_thin")
        elif queue_ratio >= float(cfg.partial_fill_threshold_ratio):
            status = "partial_fill"
            expected_qty = max(1, int(round(qty * fill_probability)))
            notes.append("partial_fill_expected")

        if spread_pct > float(cfg.max_spread_pct_for_market_fill):
            status = "rejected"
            fill_probability = min(fill_probability, 0.05)
            expected_qty = 0
            notes.append("spread_too_wide")

        mid = self._mid_price(bid, ask, ltp)
        fill_price = None
        slippage_value = 0.0
        if status != "rejected":
            reference = ask if side == "BUY" and ask > 0 else bid if side == "SELL" and bid > 0 else mid
            fill_price = self._apply_slippage(reference, side, slippage_bps)
            slippage_value = abs(float(fill_price) - float(reference)) * max(1, expected_qty)
            if queue_ratio >= float(cfg.partial_fill_threshold_ratio):
                notes.append("depth_pressure")
            if market_impact_bps > 10.0:
                notes.append("high_market_impact")
        else:
            notes.append("execution_blocked")

        return ExecutionEstimate(
            symbol=request.symbol,
            side=side,
            quantity=qty,
            fill_price=round(float(fill_price), 4) if fill_price is not None else None,
            fill_probability=round(max(0.0, min(1.0, fill_probability)), 4),
            expected_filled_quantity=int(expected_qty),
            status=status,
            slippage_bps=round(slippage_bps, 4),
            slippage_value=round(float(slippage_value), 4),
            market_impact_bps=round(market_impact_bps, 4),
            adverse_selection_bps=round(adverse_bps, 4),
            queue_ahead_ratio=round(queue_ratio, 4),
            notes=tuple(notes),
        )

    def batch_estimate(self, requests: Iterable[ExecutionRequest]) -> tuple[ExecutionEstimate, ...]:
        return tuple(self.estimate(row) for row in list(requests or []))

    def _fill_probability(self, request: ExecutionRequest, queue_ratio: float, spread_pct: float) -> float:
        cfg = self.config
        liquidity = max(0.0, min(1.0, float(request.liquidity_score or 0.0)))
        execution = max(0.0, min(1.0, float(request.execution_score or 0.0)))
        confidence = max(0.0, min(1.0, float(request.confidence or 0.0)))
        spread_penalty = min(1.0, max(0.0, spread_pct / max(cfg.max_spread_pct_for_market_fill, 1e-6)))
        depth_score = max(0.0, min(1.0, 1.0 - queue_ratio))
        probability = (
            (float(cfg.liquidity_weight) * liquidity)
            + (float(cfg.confidence_weight) * confidence)
            + (float(cfg.depth_weight) * depth_score)
            + (float(cfg.spread_weight) * max(0.0, 1.0 - spread_penalty))
            + (0.10 * execution)
        )
        return max(0.0, min(1.0, probability))

    def _market_impact_bps(self, quantity: int, top_size: float) -> float:
        cfg = self.config
        if quantity <= 0:
            return 0.0
        ratio = self._queue_ratio(quantity, top_size)
        return float(cfg.base_impact_bps) * (1.0 + max(0.0, ratio))

    @staticmethod
    def _queue_ratio(quantity: int, top_size: float) -> float:
        if quantity <= 0:
            return 0.0
        if top_size <= 0:
            return 99.0
        return float(quantity) / max(float(top_size), 1.0)

    @staticmethod
    def _spread_pct(bid: float, ask: float) -> float:
        if bid <= 0 or ask <= 0 or ask < bid:
            return 999.0
        mid = (bid + ask) / 2.0
        if mid <= 0:
            return 999.0
        return ((ask - bid) / mid) * 100.0

    @staticmethod
    def _mid_price(bid: float, ask: float, ltp: float) -> float:
        if bid > 0 and ask > 0 and ask >= bid:
            return (bid + ask) / 2.0
        if ltp > 0:
            return ltp
        return max(bid, ask, 0.0)

    @staticmethod
    def _apply_slippage(price: float, side: str, slippage_bps: float) -> float:
        multiplier = 1.0 + (slippage_bps / 10000.0) if str(side).upper() == "BUY" else 1.0 - (slippage_bps / 10000.0)
        return max(0.01, float(price) * multiplier)


def build_execution_request_from_candidate(candidate: Any, quantity: int = 1) -> ExecutionRequest:
    source = candidate.to_trade_dict() if hasattr(candidate, "to_trade_dict") else dict(candidate or {})
    return ExecutionRequest(
        symbol=str(source.get("symbol") or source.get("underlying") or "UNKNOWN"),
        side=str(source.get("side") or "BUY"),
        quantity=max(1, int(quantity or source.get("qty") or 1)),
        ltp=float(source.get("opt_ltp") or source.get("signal_price") or source.get("entry_price") or 0.0),
        best_bid=float(source.get("opt_bid") or source.get("best_bid") or 0.0),
        best_ask=float(source.get("opt_ask") or source.get("best_ask") or source.get("entry_price") or 0.0),
        bid_size=float(source.get("bid_size") or 0.0),
        ask_size=float(source.get("ask_size") or 0.0),
        spread_pct=float(source.get("spread_pct") or 0.0),
        liquidity_score=float(source.get("liquidity_score") or 0.0),
        execution_score=float(source.get("execution_score") or 0.0),
        confidence=float(source.get("confidence") or source.get("final_score") or 0.0),
        metadata={"source": source},
    )
