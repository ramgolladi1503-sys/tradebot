from __future__ import annotations

from typing import Any

from research.strategy_outcomes.contract import OutcomeCandidate


def candidate_from_orb_ledger_row(row: dict[str, Any]) -> OutcomeCandidate:
    return OutcomeCandidate(
        candidate_id=str(row.get("candidate_hash") or row.get("signal_identity") or row.get("candidate_id") or ""),
        session_key=str(row.get("session_key") or ""),
        symbol=str(row.get("symbol") or row.get("instrument") or ""),
        direction=str(row.get("direction") or ""),
        proposal_ready_at=str(row.get("proposal_ready_at") or row.get("signal_timestamp") or ""),
        source_hash=str(row.get("source_universe_hash") or row.get("source_hash") or ""),
        candidate_hash=str(row.get("candidate_hash") or ""),
        metadata={"strategy_id": "opening_range_retest_v1"},
    )
