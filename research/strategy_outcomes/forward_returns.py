from __future__ import annotations

from collections.abc import Sequence

from research.strategy_outcomes.contract import HORIZONS_MINUTES, OutcomeBar, OutcomeCandidate


def legal_entry_index(bars: Sequence[OutcomeBar], proposal_ready_at: str) -> int | None:
    for index, bar in enumerate(bars):
        if str(bar.timestamp) > str(proposal_ready_at):
            return index
    return None


def forward_returns(candidate: OutcomeCandidate, bars: Sequence[OutcomeBar], *, horizons: tuple[int, ...] = HORIZONS_MINUTES) -> dict[str, float | None]:
    entry_index = legal_entry_index(bars, candidate.proposal_ready_at)
    if entry_index is None:
        return {str(h): None for h in horizons}
    entry_price = bars[entry_index].open
    out: dict[str, float | None] = {}
    for horizon in horizons:
        target_index = entry_index + int(horizon)
        if target_index >= len(bars):
            out[str(horizon)] = None
            continue
        close = bars[target_index].close
        out[str(horizon)] = candidate.side_multiplier * ((close - entry_price) / entry_price)
    return out
