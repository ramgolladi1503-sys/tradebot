from __future__ import annotations

from .contracts import Bar, Candidate, FEATURE_CONTRACT_HASH, SUITE_VERSION, PreviousSession, Side, StrategyId, canonical_hash
from .features import directed_leader_spread_bps, opening_return_bps


def evaluate(
    *,
    symbol: str,
    peer_symbol: str,
    session: str,
    session_open: float,
    peer_session_open: float,
    previous: PreviousSession,
    decision_bar: Bar,
    peer_decision_bar: Bar,
    entry_bar: Bar,
    source_manifest_hash: str,
) -> Candidate | None:
    if decision_bar.close > previous.high:
        direction = 1
        side = Side.LONG
        relation = "ABOVE_PREVIOUS_HIGH"
    elif decision_bar.close < previous.low:
        direction = -1
        side = Side.SHORT
        relation = "BELOW_PREVIOUS_LOW"
    else:
        return None
    candidate_opening_bps = opening_return_bps(session_open, decision_bar.close)
    peer_opening_bps = opening_return_bps(peer_session_open, peer_decision_bar.close)
    leader = directed_leader_spread_bps(direction, candidate_opening_bps, peer_opening_bps)
    if leader < 20.0:
        return None
    payload = {
        "strategy_id": StrategyId.PRIOR_RANGE_LEADER.value,
        "symbol": symbol,
        "peer_symbol": peer_symbol,
        "session": session,
        "side": side.value,
        "decision_timestamp": decision_bar.timestamp,
        "entry_timestamp": entry_bar.timestamp,
        "prior_boundary_relation": relation,
        "opening_return_bps": candidate_opening_bps,
        "leader_spread_bps": leader,
        "source_manifest_hash": source_manifest_hash,
        "feature_contract_hash": FEATURE_CONTRACT_HASH,
    }
    return Candidate(
        strategy_id=StrategyId.PRIOR_RANGE_LEADER,
        strategy_version=SUITE_VERSION,
        symbol=symbol,
        side=side,
        session=session,
        decision_timestamp=decision_bar.timestamp,
        entry_timestamp=entry_bar.timestamp,
        source_manifest_hash=source_manifest_hash,
        feature_contract_hash=FEATURE_CONTRACT_HASH,
        candidate_bundle_hash=canonical_hash(payload),
        opening_return_bps=candidate_opening_bps,
        leader_spread_bps=leader,
        prior_boundary_relation=relation,
    )

