"""UI Adapter for Canonical Ranked Pipeline."""
from core.advisory_schema import AdvisorySchemaError
from core.top_opportunity_executable_truth import (
    CANONICAL_CANDIDATE_POOL_AUTHORITY,
    CANONICAL_RANKED_SNAPSHOT_SOURCE,
    CANONICAL_RANKING_AUTHORITY,
    annotate_top_opportunity_authority,
)

def adapt_candidate_rank_record_to_ui(record: dict) -> dict:
    """Convert a CandidateRankRecord to a safe UI row."""
    if not isinstance(record, dict):
        raise AdvisorySchemaError("record_not_dict")

    import time
    safety_flags = [str(flag) for flag in list(record.get("safety_flags") or []) if str(flag).strip()]
    fallback_state = "recovered_fallback" if any("fallback" in flag.lower() for flag in safety_flags) else "none"
    row = {
        "ranked_report_id": record.get("ranked_report_id"),
        "rank_id": record.get("rank_id") or f"{record.get('ranked_report_id', 'unknown')}-{record.get('candidate_id', 'unknown')}-{record.get('rank', 0)}",
        "candidate_id": record.get("candidate_id") or record.get("strategy_id"),
        "lineage_id": record.get("lineage_id") or record.get("strategy_id"),
        "canonical_snapshot_epoch": record.get("generated_epoch", time.time()),
        "rank": record.get("rank"),
        "strategy_id": record.get("strategy_id"),
        "symbol": record.get("symbol"),
        "direction": record.get("direction"),
        "bucket": record.get("bucket"),
        "score_eligibility": record.get("score_eligibility"),
        "final_score": record.get("final_score"),
        "executable_candidate": record.get("executable_candidate"),
        "rank_reason": record.get("rank_reason"),
        "blockers": list(record.get("blockers") or []),
        "warnings": list(record.get("warnings") or []),
        "safety_flags": list(record.get("safety_flags") or []),
        "canonical_source": "ranked_opportunity_pipeline_v1",
        "lineage_ok": True,
    }
    return annotate_top_opportunity_authority(
        row,
        pipeline_source=CANONICAL_RANKED_SNAPSHOT_SOURCE,
        status_authority=CANONICAL_CANDIDATE_POOL_AUTHORITY,
        rank_authority=CANONICAL_RANKING_AUTHORITY,
        execution_eligibility=False,
        execution_eligibility_authority=CANONICAL_RANKED_SNAPSHOT_SOURCE,
        phase2_status=str(record.get("bucket") or record.get("score_eligibility") or "UNKNOWN"),
        phase2_score=record.get("final_score"),
        raw_strategy_score=record.get("final_score"),
        fallback_state=fallback_state,
        blocked_reason=str(record.get("rank_reason") or "").strip() or None,
        advisory_reason=str(record.get("rank_reason") or "").strip() or None,
    )
