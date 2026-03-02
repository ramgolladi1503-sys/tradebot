import json
from pathlib import Path

from scripts.daily_blockers_report import build_blockers_report, run_blockers_report


def test_blockers_rollup_counts_and_orb_distribution(tmp_path):
    source = tmp_path / "suggestions.jsonl"
    rows = [
        {
            "timestamp_utc_iso": "2026-02-27T10:00:00+00:00",
            "permission_reason": "medium_global_conf",
            "entry_status": "OK",
            "decision_trace": {
                "orb_bias": "NEUTRAL",
                "orb_factor": 0.75,
                "global_conf": 0.5,
            },
        },
        {
            "timestamp_utc_iso": "2026-02-27T10:10:00+00:00",
            "permission_reason": "medium_global_conf",
            "entry_status": "STALE_OPTION_LTP",
            "decision_trace": {
                "orb_bias": "UP",
                "orb_factor": 0.5,
                "global_conf": 0.3,
            },
        },
        {
            "timestamp_utc_iso": "2026-02-27T11:00:00+00:00",
            "permission_reason": "aligned_high_conf",
            "entry_status": "OK",
            "decision_trace": {
                "orb_bias": "UP",
                "orb_factor": 1.0,
                "global_conf": 0.7,
            },
        },
    ]
    with source.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    report, md_path, json_path = run_blockers_report(
        "2026-02-27",
        source_paths=[source],
        out_base=tmp_path / "runtime_reports",
    )

    assert report["total_rows"] == 3
    assert report["permission_reason_top10"][0]["name"] == "medium_global_conf"
    assert report["permission_reason_top10"][0]["count"] == 2
    assert any(row["name"] == "UP" for row in report["orb_bias_distribution"])
    assert md_path.exists()
    assert json_path.exists()


def test_blockers_report_marks_orb_factor_high_execute_block(tmp_path):
    rows = [
        {
            "timestamp_utc_iso": "2026-02-27T09:30:00+00:00",
            "permission_reason": "aligned_mid_conf",
            "entry_status": "OK",
            "decision_trace": {
                "orb_bias": "BEARISH",
                "orb_factor": 0.5,
                "global_conf": 0.5,
            },
        }
    ]

    report = build_blockers_report(rows, "2026-02-27")
    assert report["below_high_execute_due_to_orb_factor"] == 1
