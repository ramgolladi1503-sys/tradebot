from __future__ import annotations

from collections.abc import Sequence

from research.strategy_outcomes.contract import OutcomeBar, OutcomeCandidate
from research.strategy_outcomes.forward_returns import legal_entry_index


def mfe_mae(candidate: OutcomeCandidate, bars: Sequence[OutcomeBar], *, horizon: int) -> dict[str, float | int | None]:
    entry_index = legal_entry_index(bars, candidate.proposal_ready_at)
    if entry_index is None:
        return {"mfe": None, "mae": None, "time_to_mfe": None, "time_to_mae": None}
    end = min(len(bars), entry_index + int(horizon) + 1)
    entry = bars[entry_index].open
    best = None
    worst = None
    best_t = None
    worst_t = None
    for offset, bar in enumerate(bars[entry_index:end]):
        high_ret = candidate.side_multiplier * ((bar.high - entry) / entry)
        low_ret = candidate.side_multiplier * ((bar.low - entry) / entry)
        bar_best = max(high_ret, low_ret)
        bar_worst = min(high_ret, low_ret)
        if best is None or bar_best > best:
            best = bar_best
            best_t = offset
        if worst is None or bar_worst < worst:
            worst = bar_worst
            worst_t = offset
    return {"mfe": best, "mae": worst, "time_to_mfe": best_t, "time_to_mae": worst_t}
