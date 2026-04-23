from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.paper_risk_sizing import PaperRiskSizingEngine, PaperRiskDecision
from core.regime_strategy_allocator import RegimeAwareStrategyAllocator


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


@dataclass(frozen=True)
class PortfolioOptimizationRow:
    trade_id: str
    symbol: str
    strategy_family: str
    regime: str
    allowed: bool
    allocated_qty: int
    allocation_score: float
    reason: str
    risk_reason: str
    optimizer_rank: int
    metadata: dict[str, Any]


class PaperPortfolioOptimizer:
    def __init__(self) -> None:
        self.risk_engine = PaperRiskSizingEngine()
        self.strategy_allocator = RegimeAwareStrategyAllocator()

    def optimize(
        self,
        candidates: list[dict[str, Any]],
        *,
        portfolio_snapshot: dict[str, Any] | None = None,
        max_selected: int = 3,
        per_strategy_cap: int = 1,
    ) -> list[PortfolioOptimizationRow]:
        portfolio_snapshot = dict(portfolio_snapshot or {})
        rows: list[tuple[dict[str, Any], PaperRiskDecision, Any, float]] = []

        for candidate in list(candidates or []):
            risk_decision = self.risk_engine.evaluate_candidate(candidate, portfolio_snapshot=portfolio_snapshot)
            strategy_family = str(candidate.get("strategy_family") or "unknown")
            regime = str(candidate.get("regime") or "NEUTRAL")
            execution_quality = _safe_float((candidate.get("source_flags") or {}).get("execution_quality_score"), _safe_float(candidate.get("execution_score"), 0.5))
            strategy_decision = self.strategy_allocator.decide(
                strategy_family=strategy_family,
                regime=regime,
                candidate_score=_safe_float(candidate.get("rank_score"), _safe_float(candidate.get("confidence"), 0.0)),
                execution_quality=execution_quality,
            )
            allocation_score = (
                0.50 * _safe_float(candidate.get("rank_score"), _safe_float(candidate.get("confidence"), 0.0))
                + 0.30 * _safe_float(strategy_decision.final_score, 0.0)
                + 0.20 * min(1.0, _safe_float(risk_decision.qty, 0.0) / max(1.0, _safe_float((risk_decision.metadata or {}).get("base_qty"), 1.0)))
            )
            rows.append((candidate, risk_decision, strategy_decision, round(allocation_score, 4)))

        rows.sort(key=lambda item: item[3], reverse=True)

        selected: list[PortfolioOptimizationRow] = []
        selected_count = 0
        strategy_counts: dict[str, int] = {}
        for rank, (candidate, risk_decision, strategy_decision, allocation_score) in enumerate(rows, start=1):
            strategy_family = str(candidate.get("strategy_family") or "unknown")
            trade_id = str(candidate.get("trade_id") or candidate.get("tradingsymbol") or f"{candidate.get('symbol','UNKNOWN')}-{rank}")
            allowed = bool(risk_decision.allowed and strategy_decision.allowed)
            reason = "selected"
            allocated_qty = 0

            if not risk_decision.allowed:
                allowed = False
                reason = f"risk_block:{risk_decision.reason}"
            elif not strategy_decision.allowed:
                allowed = False
                reason = f"strategy_block:{strategy_decision.reason}"
            elif selected_count >= max_selected:
                allowed = False
                reason = "portfolio_slot_cap"
            elif strategy_counts.get(strategy_family, 0) >= per_strategy_cap:
                allowed = False
                reason = "strategy_slot_cap"

            if allowed:
                allocated_qty = max(1, int(round(int(risk_decision.qty) * float(strategy_decision.allocation_multiplier))))
                if allocated_qty <= 0:
                    allowed = False
                    reason = "allocation_zero_qty"
                else:
                    selected_count += 1
                    strategy_counts[strategy_family] = strategy_counts.get(strategy_family, 0) + 1
            selected.append(
                PortfolioOptimizationRow(
                    trade_id=trade_id,
                    symbol=str(candidate.get("symbol") or candidate.get("underlying") or "UNKNOWN"),
                    strategy_family=strategy_family,
                    regime=str(candidate.get("regime") or "NEUTRAL"),
                    allowed=allowed,
                    allocated_qty=int(allocated_qty),
                    allocation_score=float(allocation_score),
                    reason=reason,
                    risk_reason=str(risk_decision.reason),
                    optimizer_rank=int(rank),
                    metadata={
                        "risk": risk_decision.metadata,
                        "strategy": strategy_decision.details,
                        "strategy_state": strategy_decision.state,
                        "strategy_multiplier": strategy_decision.allocation_multiplier,
                        "candidate_rank_score": candidate.get("rank_score"),
                    },
                )
            )
        return selected
