from __future__ import annotations

import json
from pathlib import Path

from research.option_e2e_recertification_v4.ce_pe_history_inventory_v1.build_inventory import build


def test_empty_root_reports_no_valid_option_sessions_and_blocks_strategy(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    manifest = tmp_path / "machine-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "current_root_id": "EMPTY_ROOT",
                        "absolute_path": str(root),
                        "allowed_candidate_classes": ["RAW_OPTION_TICK_DATASET"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = build(
        machine_manifest=manifest,
        output_dir=tmp_path / "evidence",
    )

    assert summary["valid_option_session_dates"] == []
    assert summary["valid_option_session_count"] == 0
    assert summary["chronological_coverage_verdict"] == "NO_VALID_OPTION_SESSIONS"
    assert summary["strategy_development_authorized"] is False
    assert summary["outcomes_read"] is False
    assert summary["pnl_read"] is False
    assert summary["holdout_outcomes_read"] is False
