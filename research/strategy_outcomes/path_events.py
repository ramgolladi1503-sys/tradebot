from __future__ import annotations

from collections.abc import Sequence

from research.strategy_outcomes.contract import OutcomeBar, OutcomeCandidate
from research.strategy_outcomes.forward_returns import legal_entry_index


def stop_target_event(candidate: OutcomeCandidate, bars: Sequence[OutcomeBar], *, stop_return: float, target_return: float, horizon: int) -> str:
    entry_index = legal_entry_index(bars, candidate.proposal_ready_at)
    if entry_index is None:
        return "NO_LEGAL_ENTRY"
    entry = bars[entry_index].open
    end = min(len(bars), entry_index + int(horizon) + 1)
    for bar in bars[entry_index:end]:
        high_ret = candidate.side_multiplier * ((bar.high - entry) / entry)
        low_ret = candidate.side_multiplier * ((bar.low - entry) / entry)
        hit_target = max(high_ret, low_ret) >= target_return
        hit_stop = min(high_ret, low_ret) <= -abs(stop_return)
        if hit_target and hit_stop:
            return "AMBIGUOUS_SAME_BAR"
        if hit_target:
            return "TARGET_FIRST"
        if hit_stop:
            return "STOP_FIRST"
    return "NEITHER"
