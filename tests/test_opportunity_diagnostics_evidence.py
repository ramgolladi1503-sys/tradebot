import json
from pathlib import Path

from scripts.capture_opportunity_diagnostics_evidence import (
    build_evidence_bundle,
    render_markdown_summary,
    write_evidence_bundle,
)


def test_build_evidence_bundle_marks_empty_runtime_capture_as_next_action():
    report = {
        "row_count": 0,
        "warnings": ["no_candidate_rows_visible"],
        "ui_is_ranked_opportunity_view": None,
    }

    bundle = build_evidence_bundle(report, source_path="/missing/suggestions.jsonl")

    assert bundle["read_only"] is True
    assert bundle["is_order_action"] is False
    assert bundle["source_exists"] is False
    assert bundle["row_count"] == 0
    assert "no_runtime_rows_captured" in bundle["warnings"]
    assert bundle["next_action"] == "capture_live_or_latest_runtime_suggestions_then_rerun_diagnostics"


def test_write_evidence_bundle_from_fixture(tmp_path):
    fixture = Path("tests/fixtures/opportunity_diagnostics_sample.jsonl")
    output_dir = tmp_path / "evidence"

    written = write_evidence_bundle(input_path=fixture, output_dir=output_dir)

    assert written["json"].exists()
    assert written["markdown"].exists()

    data = json.loads(written["json"].read_text(encoding="utf-8"))
    report = data["diagnostic_report"]

    assert data["read_only"] is True
    assert data["is_order_action"] is False
    assert data["source_exists"] is True
    assert data["row_count"] == 3
    assert report["flat_confidence_detected"] is True
    assert report["buy_side_ratio"] == 1.0
    assert report["recovered_fallback_count"] == 3
    assert report["ui_is_ranked_opportunity_view"] is False
    assert data["next_action"] == "design_candidate_pool_and_ranking_contract_from_observed_gaps"


def test_render_markdown_summary_contains_key_evidence_fields():
    bundle = {
        "source_path": "sample.jsonl",
        "source_exists": True,
        "row_count": 1,
        "diagnostic_report": {
            "confidence_raw_min": 0.1,
            "confidence_raw_max": 0.2,
            "confidence_raw_mean": 0.15,
            "confidence_raw_std": 0.05,
            "flat_confidence_detected": True,
            "buy_side_ratio": 1.0,
            "sell_side_ratio": 0.0,
            "recovered_fallback_count": 1,
            "executable_count": 0,
            "queue_only_count": 1,
            "advisory_count": 0,
            "rank_field_present": False,
            "opportunity_score_present": False,
            "ui_is_ranked_opportunity_view": False,
        },
        "warnings": ["rank_field_missing"],
        "next_action": "design_candidate_pool_and_ranking_contract_from_observed_gaps",
    }

    markdown = render_markdown_summary(bundle)

    assert "Opportunity Diagnostics Evidence" in markdown
    assert "Rank field present" in markdown
    assert "rank_field_missing" in markdown
    assert "design_candidate_pool_and_ranking_contract_from_observed_gaps" in markdown
