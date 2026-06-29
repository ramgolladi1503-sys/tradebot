from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.candidate_lineage_ledger import (
    build_candidate_lineage_rows,
    validate_candidate_lineage_row,
    write_candidate_lineage_ledger,
)


def _row(**overrides):
    base = {
        "timestamp": "2026-06-29T10:00:00+00:00",
        "ts_epoch": 1.0,
        "cycle_id": "cycle-1",
        "mode": "live",
        "symbol": "NIFTY",
        "underlying": "NIFTY",
        "instrument_id": "cand-1",
        "strategy_name": "trend_pullback",
        "candidate_id": "cand-1",
        "stage": "phase2",
        "stage_status": "passed",
        "displayable": True,
        "rankable": True,
        "executable": True,
        "top_opportunity": False,
        "execution_ok": True,
        "ranking_bucket": "EXECUTABLE_CANDIDATE",
        "final_score": 0.81,
        "setup_score": 0.72,
        "entropy": 0.61,
        "regime": "TREND",
        "quote_age_sec": 1.2,
        "option_ltp_age_sec": 1.2,
        "underlying_tick_age_sec": 0.8,
        "spread": 0.08,
        "spread_pct": 0.012,
        "liquidity_ok": True,
        "depth_available": True,
        "quote_source": "LIVE",
        "fallback_used": False,
        "recovered_fallback": False,
        "stale_quote": False,
        "advisory": False,
        "degraded": False,
        "block_reason": "",
        "block_reason_code": "",
        "downgrade_reasons": [],
        "source_file_or_component": "core/orchestrator.py",
        "outcome_contract": {"calibration_source": "replay"},
    }
    base.update(overrides)
    return base


def test_candidate_lineage_records_generated_candidates(tmp_path: Path):
    rows, summary = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="generated", stage_status="generated", candidate_id="cand-generated")],
    )
    assert rows[0]["candidate_id"] == "cand-generated"
    assert rows[0]["stage"] == "generated"
    assert summary["generated_total"] == 1


def test_candidate_lineage_records_tradebuilder_blocks(tmp_path: Path):
    rows, summary = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="tradebuilder", stage_status="blocked", block_reason="FEED_LTP_STALE", block_reason_code="FEED_LTP_STALE", stale_quote=True)],
    )
    assert rows[0]["block_reason_code"] == "FEED_LTP_STALE"
    assert rows[0]["executable"] is False
    assert summary["blocked_by_feed_ltp_stale"] == 1


def test_candidate_lineage_records_phase2_blocks():
    rows, _ = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="paper",
        stage_rows=[_row(stage="phase2", stage_status="blocked", block_reason="STALE_OPTION_TICK", block_reason_code="STALE_OPTION_TICK", executable=False)],
    )
    assert rows[0]["stage"] == "phase2"
    assert rows[0]["stage_status"] == "blocked"
    assert rows[0]["executable"] is False


def test_candidate_lineage_records_rankable_vs_displayable():
    rows, _ = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="replay",
        stage_rows=[
            _row(stage="display", stage_status="passed", displayable=True, rankable=False, executable=False, top_opportunity=False, advisory=True),
        ],
    )
    assert rows[0]["displayable"] is True
    assert rows[0]["rankable"] is False
    assert rows[0]["executable"] is False


def test_selected_rows_do_not_have_block_reason():
    rows, _ = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="phase2", stage_status="selected", top_opportunity=True, block_reason="SHOULD_NOT_PERSIST", block_reason_code="SHOULD_NOT_PERSIST")],
    )
    assert rows[0]["block_reason"] == ""
    assert rows[0]["selection_reason"] == "top_opportunity_selected"


def test_selected_rows_use_selection_reason():
    rows, _ = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="phase2", stage_status="selected", top_opportunity=True, block_reason="", block_reason_code="")],
    )
    assert rows[0]["selection_reason"] == "top_opportunity_selected"


def test_top_opportunity_requires_executable_and_rankable():
    rows, _ = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="phase2", stage_status="selected", top_opportunity=True, executable=True, rankable=True)],
    )
    assert rows[0]["top_opportunity"] is True
    assert rows[0]["executable"] is True
    assert rows[0]["rankable"] is True


def test_candidate_lineage_records_fallback_as_non_executable():
    rows, _ = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="phase2", stage_status="blocked", fallback_used=True, executable=False, block_reason="contract_resolution_fallback_blocked")],
    )
    assert rows[0]["fallback_used"] is True
    assert rows[0]["executable"] is False
    assert rows[0]["block_reason"]


def test_candidate_lineage_records_stale_quote_as_non_executable():
    rows, _ = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="phase2", stage_status="blocked", stale_quote=True, executable=False, block_reason="STALE_OPTION_TICK")],
    )
    assert rows[0]["stale_quote"] is True
    assert rows[0]["executable"] is False


def test_fallback_stale_advisory_degraded_never_executable_in_lineage():
    for flag in ("fallback_used", "recovered_fallback", "stale_quote", "advisory", "degraded"):
        rows, _ = build_candidate_lineage_rows(
            cycle_id=f"cycle-{flag}",
            mode="live",
            stage_rows=[_row(stage="phase2", stage_status="blocked", executable=True, execution_ok=True, block_reason=flag, **{flag: True})],
        )
        assert rows[0]["executable"] is False
        assert validate_candidate_lineage_row(rows[0]) == []


def test_candidate_funnel_summary_counts_by_stage():
    _, summary = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[
            _row(stage="generated", stage_status="generated"),
            _row(stage="tradebuilder", stage_status="passed"),
            _row(stage="phase2", stage_status="passed"),
        ],
    )
    assert summary["generated_total"] == 3
    assert summary["tradebuilder_passed_total"] >= 1
    assert summary["phase2_passed_total"] >= 1


def test_candidate_funnel_summary_counts_by_block_reason():
    _, summary = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[
            _row(stage="tradebuilder", stage_status="blocked", block_reason="FEED_LTP_STALE", block_reason_code="FEED_LTP_STALE", stale_quote=True),
            _row(stage="tradebuilder", stage_status="blocked", block_reason="STALE_OPTION_TICK", block_reason_code="STALE_OPTION_TICK", stale_quote=True),
        ],
    )
    assert summary["blocked_total"] == 2
    assert summary["blocked_by_feed_ltp_stale"] >= 1
    assert summary["blocked_by_stale_option_tick"] >= 1


def test_blocked_total_excludes_selected_rows():
    _, summary = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[
            _row(stage="phase2", stage_status="selected", top_opportunity=True),
            _row(stage="phase2", stage_status="blocked", block_reason="STALE_OPTION_TICK"),
        ],
        summary_inputs={"blocked_total": 99},
    )
    assert summary["blocked_total"] == 1


def test_phase2_direct_entry_path_is_explicit():
    rows, summary = build_candidate_lineage_rows(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="phase2", stage_status="passed")],
        summary_inputs={"tradebuilder_input_total": 0, "phase2_input_total": 1},
    )
    assert rows[0]["entry_path"] == "phase2_direct"
    assert summary["phase2_input_total"] == 1
    assert summary["tradebuilder_input_total"] == 0


def test_lineage_observability_does_not_change_execution_ok():
    row = _row(executable=True, execution_ok=True)
    original = dict(row)
    rows, _ = build_candidate_lineage_rows(cycle_id="cycle-1", mode="live", stage_rows=[row])
    assert row == original
    assert rows[0]["execution_ok"] is True


def test_lineage_observability_does_not_promote_top_opportunity(tmp_path: Path):
    row = _row(executable=False, top_opportunity=False, stage_status="blocked", block_reason="NO_TRADE")
    rows, _ = build_candidate_lineage_rows(cycle_id="cycle-1", mode="live", stage_rows=[row])
    assert rows[0]["top_opportunity"] is False
    assert rows[0]["executable"] is False
    assert validate_candidate_lineage_row(rows[0]) == []


def test_write_candidate_lineage_ledger(tmp_path: Path):
    lineage_path = tmp_path / "runtime" / "candidate_lineage" / "candidate_funnel_20260629.jsonl"
    summary_path = tmp_path / "runtime" / "candidate_lineage" / "candidate_funnel_summary_20260629.jsonl"
    out_lineage, out_summary, summary, rows = write_candidate_lineage_ledger(
        cycle_id="cycle-1",
        mode="live",
        stage_rows=[_row(stage="phase2", stage_status="selected", top_opportunity=True)],
        lineage_path=lineage_path,
        summary_path=summary_path,
    )
    assert out_lineage.exists()
    assert out_summary.exists()
    assert rows[0]["top_opportunity"] is True
    payload = json.loads(out_lineage.read_text().splitlines()[0])
    assert payload["cycle_id"] == "cycle-1"
    summary_payload = json.loads(out_summary.read_text().splitlines()[0])
    assert summary_payload["cycle_id"] == "cycle-1"


def test_candidate_lineage_invariants_helper_flags_bad_rows():
    errors = validate_candidate_lineage_row(
        {
            "stage_status": "selected",
            "top_opportunity": True,
            "rankable": False,
            "executable": False,
            "block_reason": "bad",
            "selection_reason": "",
            "fallback_used": True,
            "execution_ok": False,
        }
    )
    assert "non_blocked_row_has_block_reason" in errors
    assert "top_opportunity_requires_selected_status" not in errors
    assert "top_opportunity_requires_executable" in errors
    assert "top_opportunity_requires_rankable" in errors
    assert "degraded_truth_must_not_be_executable" not in errors
    assert "execution_ok_false_must_not_be_executable" not in errors


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def test_candidate_lineage_analyzer_flags_semantic_violations(tmp_path: Path):
    lineage_path = tmp_path / "candidate_funnel_20260629.jsonl"
    summary_path = tmp_path / "candidate_funnel_summary_20260629.jsonl"
    _write_jsonl(
        lineage_path,
        [
            {
                "cycle_id": "cycle-1",
                "candidate_id": "bad-selected",
                "strategy_name": "trend_pullback",
                "stage_status": "selected",
                "block_reason": "BAD_REASON",
                "top_opportunity": True,
                "executable": False,
                "fallback_used": False,
                "recovered_fallback": False,
                "stale_quote": False,
                "advisory": False,
                "degraded": False,
            },
            {
                "cycle_id": "cycle-1",
                "candidate_id": "bad-fallback",
                "strategy_name": "trend_pullback",
                "stage_status": "blocked",
                "block_reason": "fallback_used",
                "top_opportunity": False,
                "executable": True,
                "fallback_used": True,
                "entry_path": "",
            },
        ],
    )
    _write_jsonl(
        summary_path,
        [
            {
                "cycle_id": "cycle-1",
                "generated_total": 2,
                "tradebuilder_input_total": 0,
                "phase2_input_total": 1,
                "rankable_total": 0,
                "executable_total": 1,
                "top_opportunity_total": 1,
            }
        ],
    )
    result = subprocess.run(
        [sys.executable, "scripts/analyze_candidate_lineage.py", "--lineage", str(lineage_path), "--summary", str(summary_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "warning: selected-or-passed row has block_reason: bad-selected" in result.stdout
    assert "warning: top_opportunity not executable: bad-selected" in result.stdout
    assert "warning: degraded row executable: bad-fallback" in result.stdout
    assert "warning: phase2_input_total exceeds tradebuilder_input_total without explicit entry_path" in result.stdout


def test_candidate_lineage_analyzer_summarizes_block_reasons(tmp_path: Path):
    lineage_path = tmp_path / "candidate_funnel_20260629.jsonl"
    summary_path = tmp_path / "candidate_funnel_summary_20260629.jsonl"
    _write_jsonl(
        lineage_path,
        [
            {
                "cycle_id": "cycle-1",
                "candidate_id": "stale-1",
                "strategy_name": "trend_pullback",
                "stage_status": "blocked",
                "block_reason": "STALE_OPTION_TICK",
                "downgrade_reasons": ["stale_quote"],
                "executable": False,
                "entry_path": "strategy_to_tradebuilder",
            },
            {
                "cycle_id": "cycle-1",
                "candidate_id": "feed-1",
                "strategy_name": "opening_drive",
                "stage_status": "blocked",
                "block_reason": "FEED_LTP_STALE",
                "downgrade_reasons": [],
                "executable": False,
                "entry_path": "strategy_to_tradebuilder",
            },
        ],
    )
    _write_jsonl(
        summary_path,
        [
            {
                "cycle_id": "cycle-1",
                "generated_total": 2,
                "tradebuilder_input_total": 2,
                "phase2_input_total": 0,
                "rankable_total": 0,
                "executable_total": 0,
                "top_opportunity_total": 0,
            }
        ],
    )
    result = subprocess.run(
        [sys.executable, "scripts/analyze_candidate_lineage.py", "--lineage", str(lineage_path), "--summary", str(summary_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "cycles analyzed: 1" in result.stdout
    assert "STALE_OPTION_TICK: 1" in result.stdout
    assert "FEED_LTP_STALE: 1" in result.stdout
    assert "trend_pullback: 1" in result.stdout
