"""UI Adapter for Canonical Ranked Pipeline."""

from typing import Any
from core.advisory_schema import AdvisorySchemaError

def adapt_candidate_rank_record_to_ui(record: dict) -> dict:
    """Convert a CandidateRankRecord to a safe UI row."""
    if not isinstance(record, dict):
        raise AdvisorySchemaError("record_not_dict")

    import uuid
    import time
    return {
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
