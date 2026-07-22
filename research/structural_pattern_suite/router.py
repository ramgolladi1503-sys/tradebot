from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .contracts import Candidate, StrategyId


PRIORITY = {
    StrategyId.GAP_GO_LEADER: 1,
    StrategyId.PRIOR_RANGE_LEADER: 2,
    StrategyId.LATE_DAY_PERSISTENCE: 3,
}


def route_candidates(candidates: Iterable[Candidate], *, one_trade_per_symbol_day: bool = True) -> tuple[list[Candidate], dict[str, int]]:
    grouped: dict[tuple[str, str, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate.session, candidate.symbol, candidate.decision_timestamp)].append(candidate)

    accepted: list[Candidate] = []
    rejected = {"contradictory_side": 0, "lower_priority_same_side": 0, "one_trade_per_day": 0}
    used_symbol_day: set[tuple[str, str]] = set()
    for key in sorted(grouped):
        group = grouped[key]
        sides = {item.side for item in group}
        if len(sides) > 1:
            rejected["contradictory_side"] += len(group)
            continue
        winner = sorted(group, key=lambda item: PRIORITY[item.strategy_id])[0]
        rejected["lower_priority_same_side"] += len(group) - 1
        day_key = (winner.session, winner.symbol)
        if one_trade_per_symbol_day and day_key in used_symbol_day:
            rejected["one_trade_per_day"] += 1
            continue
        used_symbol_day.add(day_key)
        accepted.append(winner)
    return accepted, rejected

