from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .session import SessionAnalysis


def write_analysis_bundle(
    analysis: SessionAnalysis,
    output_dir: str | Path,
) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    record = analysis.to_record()
    json_path = root / "session_analysis.json"
    markdown_path = root / "session_report.md"
    json_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    manifest = analysis.manifest
    funnel = analysis.candidate_funnel
    readiness = analysis.outcome_readiness
    markdown = "\n".join(
        [
            "# Aixion Trade Intelligence — Offline Session Report",
            "",
            f"- Session: `{manifest['session_id']}`",
            f"- Run: `{manifest['run_id']}`",
            f"- Verdict: `{manifest['verdict']}`",
            f"- Events: `{manifest['event_count']}`",
            f"- Instruments: `{manifest['instrument_count']}`",
            f"- Analysis hash: `{analysis.analysis_hash}`",
            "",
            "## Data truth",
            "",
            f"- Valid: `{manifest['valid']}`",
            f"- Invalid-quality events: `{manifest['invalid_quality_event_count']}`",
            f"- Producer sequence gaps: `{manifest['producer_sequence_gap_total']}`",
            f"- Event-log SHA-256: `{manifest['event_log_sha256']}`",
            "",
            "## Candidate truth",
            "",
            f"- Candidates: `{funnel['candidate_count']}`",
            f"- Candidate-to-outcome complete: `{funnel['complete_candidate_to_outcome_count']}`",
            f"- Blockers: `{json.dumps(funnel['blocker_counts'], sort_keys=True)}`",
            "",
            "## Diagnosis readiness",
            "",
            f"- Ready for strategy diagnosis: `{readiness['ready_for_strategy_diagnosis']}`",
            f"- Ready for profitability claim: `{readiness['ready_for_profitability_claim']}`",
            f"- Boundary: `{readiness['reason']}`",
            "",
            "## Claim boundary",
            "",
            "This report validates offline evidence integrity and lineage only. It does not certify trading edge, live execution, option-fill realism, capacity, or holdout profitability.",
            "",
        ]
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "analysis_hash": analysis.analysis_hash,
    }
