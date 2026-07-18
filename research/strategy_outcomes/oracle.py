from __future__ import annotations

from collections.abc import Sequence

from research.strategy_outcomes.contract import OutcomeBar, OutcomeContractError


def validate_bar_sequence(bars: Sequence[OutcomeBar]) -> None:
    previous = None
    seen: set[str] = set()
    sessions = {bar.session_key for bar in bars if bar.session_key}
    if len(sessions) > 1:
        raise OutcomeContractError("mixed_session")
    for bar in bars:
        if bar.timestamp in seen:
            raise OutcomeContractError("duplicate_source_timestamp")
        if previous is not None and bar.timestamp <= previous:
            raise OutcomeContractError("non_monotonic_bars")
        seen.add(bar.timestamp)
        previous = bar.timestamp
