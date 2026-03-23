from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_candidate_pipeline.py"
    spec = importlib.util.spec_from_file_location("verify_candidate_pipeline", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_verify_candidate_pipeline_reports_runtime_scoring_and_identity_health(tmp_path):
    module = _load_module()
    suggestions_path = tmp_path / "logs" / "suggestions.jsonl"
    rejected_path = tmp_path / "logs" / "rejected_candidates.jsonl"

    _write_jsonl(
        suggestions_path,
        [
            {
                "trade_id": "T-ACTIVE",
                "ts_epoch": 4,
                "final_action": "ADVISORY_ONLY",
                "candidate_status": "advisory_only",
                "rank_score": 0.91,
                "opportunity_score": 0.86,
                "score_breakdown": {"components": {"setup_strength": 0.88}},
                "strategy_family": "breakout",
                "candidate_type": "options",
                "symbol": "NIFTY",
            },
            {
                "trade_id": "T-OFFHOURS",
                "ts_epoch": 3,
                "final_action": "ADVISORY_ONLY",
                "candidate_status": "advisory_only",
                "rank_score": 0.67,
                "opportunity_score": 0.63,
                "score_breakdown": {"components": {"timing_score": 0.55}},
                "strategy_family": "volatility_expansion",
                "candidate_type": "options",
                "quote_validation_status": "OFFHOURS_SYNTHETIC",
                "symbol": "BANKNIFTY",
            },
            {
                "trade_id": "T-MISSING-SCORE",
                "ts_epoch": 2,
                "final_action": "BLOCK",
                "candidate_status": "advisory_only",
                "strategy_family": "unknown",
                "candidate_type": "unknown",
                "symbol": "FINNIFTY",
            },
        ],
    )
    _write_jsonl(
        rejected_path,
        [
            {
                "trade_id": "T-BLOCKED-CONTRACT",
                "ts_epoch": 1,
                "final_action": "BLOCK",
                "candidate_status": "blocked_contract",
                "rank_score": 0.42,
                "opportunity_score": 0.39,
                "score_breakdown": {"components": {"penalty_score": 0.22}},
                "strategy_family": "breakout",
                "candidate_type": "options",
                "hard_reason": "unresolved_contract",
                "reason_code": "unresolved_contract",
                "symbol": "SENSEX",
            }
        ],
    )

    report = module.build_candidate_pipeline_report(
        suggestions_paths=[suggestions_path],
        rejected_paths=[rejected_path],
        limit=20,
        top_n=10,
    )

    assert report["total_rows"] == 4
    assert report["rank_score_present_count"] == 3
    assert report["rank_score_missing_count"] == 1
    assert report["final_action_distribution"] == {
        "ADVISORY_ONLY": 2,
        "BLOCK": 2,
    }
    assert report["strategy_family_distribution"] == {
        "breakout": 2,
        "unknown": 1,
        "volatility_expansion": 1,
    }
    assert report["candidate_type_distribution"] == {
        "options": 3,
        "unknown": 1,
    }
    assert report["top_ranked"][0]["trade_id"] == "T-ACTIVE"
    assert report["top_ranked"][0]["rank_score"] == 0.91
    assert report["top_ranked"][1]["trade_id"] == "T-OFFHOURS"
    missing_rows = report["rows_missing_score_metadata"]
    assert len(missing_rows) == 1
    assert missing_rows[0]["trade_id"] == "T-MISSING-SCORE"
    assert missing_rows[0]["missing_fields"] == [
        "rank_score",
        "opportunity_score",
        "score_breakdown",
    ]

    rendered = module.render_candidate_pipeline_report(report)
    assert "Candidate Pipeline Verification" in rendered
    assert "Final action distribution:" in rendered
    assert "Strategy family distribution:" in rendered
    assert "Top 10 by rank_score:" in rendered
    assert "trade_id=T-ACTIVE" in rendered
    assert "trade_id=T-BLOCKED-CONTRACT" in rendered
    assert "trade_id=T-MISSING-SCORE" in rendered
