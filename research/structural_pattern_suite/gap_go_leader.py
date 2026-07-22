from __future__ import annotations

from .contracts import Bar, Candidate, FEATURE_CONTRACT_HASH, SUITE_VERSION, PreviousSession, Side, StrategyId, canonical_hash
from .features import directed_leader_spread_bps, gap_normalized, opening_return_bps, sign


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
    gap_direction = sign(session_open - previous.close)
    if gap_direction == 0:
        return None
    gap = gap_normalized(session_open, previous)
    candidate_opening_bps = opening_return_bps(session_open, decision_bar.close)
    peer_opening_bps = opening_return_bps(peer_session_open, peer_decision_bar.close)
    leader = directed_leader_spread_bps(gap_direction, candidate_opening_bps, peer_opening_bps)
    if gap < 0.33:
        return None
    if sign(candidate_opening_bps) != gap_direction:
        return None
    if abs(candidate_opening_bps) < 5.0:
        return None
    if leader < 20.0:
        return None
    side = Side.LONG if gap_direction > 0 else Side.SHORT
    payload = {
        "strategy_id": StrategyId.GAP_GO_LEADER.value,
        "symbol": symbol,
        "peer_symbol": peer_symbol,
        "session": session,
        "side": side.value,
        "decision_timestamp": decision_bar.timestamp,
        "entry_timestamp": entry_bar.timestamp,
        "gap_normalized": gap,
        "opening_return_bps": candidate_opening_bps,
        "leader_spread_bps": leader,
        "source_manifest_hash": source_manifest_hash,
        "feature_contract_hash": FEATURE_CONTRACT_HASH,
    }
    return Candidate(
        strategy_id=StrategyId.GAP_GO_LEADER,
        strategy_version=SUITE_VERSION,
        symbol=symbol,
        side=side,
        session=session,
        decision_timestamp=decision_bar.timestamp,
        entry_timestamp=entry_bar.timestamp,
        source_manifest_hash=source_manifest_hash,
        feature_contract_hash=FEATURE_CONTRACT_HASH,
        candidate_bundle_hash=canonical_hash(payload),
        gap_normalized=gap,
        opening_return_bps=candidate_opening_bps,
        leader_spread_bps=leader,
    )

