from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.movement_contract import StrategyCandidate
from core.opening_range_retest_emission_store import (
    OpeningRangeRetestEmissionStore,
    OpeningRangeRetestProposal,
    PublicationResult,
)
from core.paths import runtime_dir

STRATEGY_ID = "opening_range_retest_v1"
TEMPORAL_CONTRACT_VERSION = "opening_range_retest_temporal_v1"
SOURCE_COMPONENT = "strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates"
OWNER_DB_FILENAME = "opening_range_retest_emission.sqlite"
ACCEPTED_PUBLICATION_RESULTS = {"ACCEPTED_FOR_PUBLICATION", "ALREADY_EMITTED"}


def default_owner_db_path() -> Path:
    return runtime_dir() / OWNER_DB_FILENAME


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _semantic_fingerprint(candidate: StrategyCandidate) -> dict[str, Any]:
    return {
        "strategy_id": str(candidate.strategy_id),
        "direction": str(candidate.direction),
        "status": str(candidate.status),
        "raw_score": round(float(candidate.raw_score), 6),
        "entry_trigger": str(candidate.entry_trigger),
        "invalid_if": str(candidate.invalid_if),
        "rank_reason": str(candidate.rank_reason),
    }


def _setup_identity(candidate: StrategyCandidate) -> dict[str, Any]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    setup_identity = evidence.get("setup_identity")
    if not isinstance(setup_identity, dict):
        raise ValueError("missing_required_setup_identity")

    required_keys = (
        "contract_version",
        "strategy_id",
        "symbol",
        "session_date",
        "direction",
        "boundary_type",
        "normalized_boundary_value",
        "breakout_timestamp",
        "proposal_ready_at_iso",
        "setup_id",
        "history_hash",
    )
    missing = tuple(sorted(key for key in required_keys if setup_identity.get(key) in (None, "", "None")))
    if missing:
        raise ValueError(f"missing_required_setup_identity_fields:{','.join(missing)}")
    return dict(setup_identity)


def build_opening_range_retest_proposal(candidate: StrategyCandidate) -> OpeningRangeRetestProposal:
    if str(candidate.strategy_id).strip() != STRATEGY_ID:
        raise ValueError("unsupported_strategy_id")
    if str(candidate.status).strip().upper() != "RAW_CANDIDATE":
        raise ValueError("candidate_status_must_be_raw")
    promotion_state = str((candidate.lineage or {}).get("promotion_state") or "").strip().upper()
    if promotion_state != "READY_FOR_PUBLICATION":
        raise ValueError("candidate_not_ready_for_publication")

    setup_identity = _setup_identity(candidate)
    semantic_fingerprint = _semantic_fingerprint(candidate)
    candidate_fingerprint = _canonical_json(semantic_fingerprint)
    candidate_payload = {
        "candidate_fingerprint": semantic_fingerprint,
        "candidate_score": float(candidate.raw_score),
        "entry_trigger": str(candidate.entry_trigger),
        "invalid_if": str(candidate.invalid_if),
        "movement_type": str(candidate.movement_type),
        "promotion_state": promotion_state,
        "rank_reason": str(candidate.rank_reason),
        "setup_identity": setup_identity,
        "source_component": SOURCE_COMPONENT,
        "strategy_id": STRATEGY_ID,
    }

    return OpeningRangeRetestProposal(
        setup_id=str(setup_identity["setup_id"]),
        strategy_id=STRATEGY_ID,
        contract_version=str(setup_identity["contract_version"]) or TEMPORAL_CONTRACT_VERSION,
        schema_version=1,
        source_component=SOURCE_COMPONENT,
        symbol=str(setup_identity["symbol"]),
        session_date=str(setup_identity["session_date"]),
        direction=str(setup_identity["direction"]),
        boundary_type=str(setup_identity["boundary_type"]),
        normalized_boundary_value=float(setup_identity["normalized_boundary_value"]),
        breakout_timestamp_iso=str(setup_identity["breakout_timestamp"]),
        history_hash=str(setup_identity["history_hash"]),
        candidate_fingerprint=candidate_fingerprint,
        candidate_payload_json=_canonical_json(candidate_payload),
        created_at_iso=str(setup_identity["proposal_ready_at_iso"]),
    )


def accept_opening_range_retest_candidate(
    candidate: StrategyCandidate,
    *,
    db_path: str | Path | None = None,
    store: OpeningRangeRetestEmissionStore | None = None,
) -> PublicationResult:
    proposal = build_opening_range_retest_proposal(candidate)
    owner_store = store or OpeningRangeRetestEmissionStore(
        db_path=db_path if db_path is not None else default_owner_db_path(),
    )
    return owner_store.accept_candidate_proposal(proposal)


__all__ = [
    "ACCEPTED_PUBLICATION_RESULTS",
    "SOURCE_COMPONENT",
    "STRATEGY_ID",
    "TEMPORAL_CONTRACT_VERSION",
    "accept_opening_range_retest_candidate",
    "build_opening_range_retest_proposal",
    "default_owner_db_path",
]
