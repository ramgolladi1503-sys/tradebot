from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from core.stock_option_subsystem import StockOptionCandidate


@dataclass(frozen=True)
class StockOptionControlConfig:
    max_executable_candidates: int = 2
    max_candidates_per_symbol: int = 1
    min_candidate_score: float = 0.62
    min_execution_score: float = 0.60
    min_liquidity_score: float = 0.60
    allowed_statuses: tuple[str, ...] = ("executable",)
    block_duplicate_symbol: bool = True


@dataclass(frozen=True)
class StockOptionControlDecision:
    candidate: StockOptionCandidate
    accepted: bool
    reason: str


@dataclass(frozen=True)
class StockOptionControlResult:
    accepted: tuple[StockOptionCandidate, ...]
    rejected: tuple[StockOptionControlDecision, ...]


class StockOptionControlEngine:
    def __init__(self, config: StockOptionControlConfig | None = None):
        self.config = config or StockOptionControlConfig()

    def apply(self, candidates: Iterable[StockOptionCandidate]) -> StockOptionControlResult:
        cfg = self.config
        accepted: list[StockOptionCandidate] = []
        rejected: list[StockOptionControlDecision] = []
        symbol_counts: dict[str, int] = {}

        ordered = sorted(
            list(candidates or []),
            key=lambda row: (-float(row.score), -float(row.execution_score), -float(row.liquidity_score)),
        )

        for candidate in ordered:
            reason = self._reject_reason(candidate, accepted, symbol_counts)
            if reason is None:
                accepted.append(candidate)
                symbol_counts[candidate.symbol] = symbol_counts.get(candidate.symbol, 0) + 1
            else:
                rejected.append(
                    StockOptionControlDecision(
                        candidate=candidate,
                        accepted=False,
                        reason=reason,
                    )
                )

        if len(accepted) > cfg.max_executable_candidates:
            overflow = accepted[cfg.max_executable_candidates :]
            accepted = accepted[: cfg.max_executable_candidates]
            for candidate in overflow:
                rejected.append(
                    StockOptionControlDecision(
                        candidate=candidate,
                        accepted=False,
                        reason="portfolio_candidate_limit",
                    )
                )

        return StockOptionControlResult(
            accepted=tuple(accepted),
            rejected=tuple(rejected),
        )

    def _reject_reason(
        self,
        candidate: StockOptionCandidate,
        accepted: list[StockOptionCandidate],
        symbol_counts: dict[str, int],
    ) -> str | None:
        cfg = self.config
        if str(candidate.candidate_status).lower() not in {str(x).lower() for x in cfg.allowed_statuses}:
            return "candidate_status_not_allowed"
        if float(candidate.score) < float(cfg.min_candidate_score):
            return "candidate_score_below_min"
        if float(candidate.execution_score) < float(cfg.min_execution_score):
            return "execution_score_below_min"
        if float(candidate.liquidity_score) < float(cfg.min_liquidity_score):
            return "liquidity_score_below_min"
        if cfg.block_duplicate_symbol and symbol_counts.get(candidate.symbol, 0) >= cfg.max_candidates_per_symbol:
            return "duplicate_symbol_block"
        if len(accepted) >= cfg.max_executable_candidates:
            return "portfolio_candidate_limit"
        return None
