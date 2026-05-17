import json
from pathlib import Path

from core.opportunity_diagnostics import (
    build_opportunity_diagnostics,
    load_candidate_rows,
    write_opportunity_diagnostics_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_build_opportunity_diagnostics_flags_flat_buy_fallback_output_view():
    rows = [
        {
            "confidence_raw": 0.46,
            "side": "BUY",
            "execution_status": "QUEUE_ONLY",
            "quote_source": "recovered_fallback",
            "primary_blocker": "STALE_OPTION_LTP",
        },
        {
            "confidence_raw": 0.45,
            "side": "BUY",
            "execution_status": "ADVISORY_ONLY",
            "quote_source": "recovered_fallback",
            "primary_blocker": "STALE_OPTION_LTP",
        },
        {
            "confidence_raw": 0.44,
            "side": "BUY",
            "execution_status": "EXECUTE",
            "quote_source": "recovered_fallback",
            "primary_blocker": "MEDIUM_GLOBAL_CONF",
        },
    ]

    report = build_opportunity_diagnostics(rows, source_path="memory")

    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["row_count"] == 3
    assert report["confidence_raw_min"] == 0.44
    assert report["confidence_raw_max"] == 0.46
    assert report["flat_confidence_detected"] is True
    assert report["buy_side_ratio"] == 1.0
    assert report["sell_side_ratio"] == 0.0
    assert report["recovered_fallback_count"] == 3
    assert report["executable_count"] == 1
    assert report["queue_only_count"] == 1
    assert report["advisory_count"] == 1
    assert report["rank_field_present"] is False
    assert report["opportunity_score_present"] is False
    assert report["ui_is_ranked_opportunity_view"] is False
    assert "ui_appears_filtered_output_view_not_ranked_opportunity_view" in report["warnings"]


def test_build_opportunity_diagnostics_recognizes_ranked_opportunity_view():
    rows = [
        {"rank": 1, "opportunity_score": 0.82, "confidence_raw": 0.78, "side": "BUY", "execution_status": "EXECUTE"},
        {"rank": 2, "opportunity_score": 0.61, "confidence_raw": 0.58, "side": "SELL", "execution_status": "QUEUE_ONLY"},
    ]

    report = build_opportunity_diagnostics(rows)

    assert report["rank_field_present"] is True
    assert report["opportunity_score_present"] is True
    assert report["ui_is_ranked_opportunity_view"] is True
    assert report["buy_side_ratio"] == 0.5
    assert report["sell_side_ratio"] == 0.5
    assert "rank_field_missing" not in report["warnings"]
    assert "opportunity_score_missing" not in report["warnings"]


def test_load_candidate_rows_and_write_report_from_jsonl(tmp_path):
    logs = tmp_path / "logs"
    suggestions = logs / "suggestions.jsonl"
    _write_jsonl(
        suggestions,
        [
            {"confidence_raw": 0.50, "side": "BUY", "execution_status": "QUEUE_ONLY"},
            {"confidence_raw": 0.49, "side": "BUY", "execution_status": "QUEUE_ONLY"},
        ],
    )

    rows, source = load_candidate_rows(logs_dir=logs)
    assert source == str(suggestions)
    assert len(rows) == 2

    out = tmp_path / "report.json"
    written = write_opportunity_diagnostics_report(logs_dir=logs, output_path=out)
    data = json.loads(written.read_text(encoding="utf-8"))

    assert written == out
    assert data["source_path"] == str(suggestions)
    assert data["row_count"] == 2
