from __future__ import annotations

from collections.abc import Sequence

from .contracts import Bar, Candidate, FEATURE_CONTRACT_HASH, SUITE_VERSION, PreviousSession, Side, StrategyId, canonical_hash
from .features import close_location, directional_displacement_normalized


def evaluate(
    *,
    symbol: str,
    session: str,
    session_open: float,
    previous: PreviousSession,
    bars_from_open_to_decision: Sequence[Bar],
    decision_bar: Bar,
    entry_bar: Bar,
    source_manifest_hash: str,
) -> Candidate | None:
    displacement = directional_displacement_normalized(session_open, decision_bar.close, previous)
    location = close_location(bars_from_open_to_decision, decision_bar.close)
    if displacement < 0.50:
        return None
    if decision_bar.close > session_open and location >= 0.80:
        side = Side.LONG
    elif decision_bar.close < session_open and location <= 0.20:
        side = Side.SHORT
    else:
        return None
    payload = {
        "strategy_id": StrategyId.LATE_DAY_PERSISTENCE.value,
        "symbol": symbol,
        "session": session,
        "side": side.value,
        "decision_timestamp": decision_bar.timestamp,
        "entry_timestamp": entry_bar.timestamp,
        "late_displacement": displacement,
        "close_location": location,
        "source_manifest_hash": source_manifest_hash,
        "feature_contract_hash": FEATURE_CONTRACT_HASH,
    }
    return Candidate(
        strategy_id=StrategyId.LATE_DAY_PERSISTENCE,
        strategy_version=SUITE_VERSION,
        symbol=symbol,
        side=side,
        session=session,
        decision_timestamp=decision_bar.timestamp,
        entry_timestamp=entry_bar.timestamp,
        source_manifest_hash=source_manifest_hash,
        feature_contract_hash=FEATURE_CONTRACT_HASH,
        candidate_bundle_hash=canonical_hash(payload),
        late_displacement=displacement,
        close_location=location,
    )

