from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_offline_feed_candidate_truth_proof_pack import (
    build_offline_feed_candidate_truth_proof_pack,
    default_scenarios,
    write_proof_pack,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _scenario_map():
    pack = build_offline_feed_candidate_truth_proof_pack()
    return {scenario.scenario_name: scenario for scenario in pack.scenarios}


def test_offline_truth_pack_healthy_candidate_passes():
    scenario = _scenario_map()["healthy_executable_candidate"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "EXECUTABLE"
    assert scenario.actual_result == "EXECUTABLE"
    assert scenario.executable_allowed is True
    assert scenario.reportable_executable is True
    assert scenario.phase2_input_state == "ACCEPTED"
    assert scenario.final_emit_allowed is True
    assert scenario.read_only is True
    assert scenario.append is False
    assert scenario.is_order_action is False
    assert scenario.broker_api_called is False
    assert scenario.live_order_allowed is False


def test_offline_truth_pack_feed_dead_blocks_executable_looking_candidate():
    scenario = _scenario_map()["feed_dead_blocks_executable_looking_candidate"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "BLOCKED"
    assert scenario.actual_result == "BLOCKED"
    assert scenario.executable_allowed is False
    assert scenario.reportable_executable is False
    assert scenario.final_emit_allowed is False
    assert "RECOVERY_BLOCKED" in scenario.blockers
    assert "WS_DISCONNECTED" in scenario.blockers
    assert scenario.feed_truth_state == "RECOVERY_BLOCKED"


def test_offline_truth_pack_stale_option_ltp_blocks_final_emit():
    scenario = _scenario_map()["stale_option_ltp_blocks_final_emit"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "BLOCKED"
    assert scenario.actual_result == "BLOCKED"
    assert scenario.reportable_executable is False
    assert scenario.final_emit_allowed is False
    assert "STALE_OPTION_LTP" in scenario.blockers
    assert scenario.phase2_drop_counts["stale_option_ltp"] == 1


def test_offline_truth_pack_missing_context_counts_phase2_categories():
    scenario = _scenario_map()["missing_context_counts_phase2_categories"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "BLOCKED"
    assert scenario.phase2_drop_counts["missing_live_timing_context"] == 1
    assert scenario.phase2_drop_counts["missing_spread_context"] == 1
    assert scenario.phase2_drop_counts["missing_liquidity_context"] == 1
    assert scenario.phase2_drop_counts["unknown_quote_source"] == 1
    assert scenario.final_emit_allowed is False


def test_offline_truth_pack_advisory_synthetic_fallback_not_executable():
    scenario = _scenario_map()["advisory_synthetic_fallback_not_executable"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "BLOCKED"
    assert scenario.actual_result == "BLOCKED"
    assert scenario.reportable_executable is False
    assert scenario.final_emit_allowed is False
    assert "ADVISORY_OR_QUEUE_ONLY" in scenario.blockers
    assert "SYNTHETIC_OR_FALLBACK" in scenario.blockers
    assert scenario.phase2_input_state == "INPUT_DROPPED"


def test_offline_truth_pack_phase2_no_input_not_hard_execution():
    scenario = _scenario_map()["phase2_no_input_not_hard_execution"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "NO_INPUT"
    assert scenario.actual_result == "NO_INPUT"
    assert scenario.phase2_input_state == "NO_INPUT"
    assert scenario.phase2_drop_counts == {}
    assert "hard_execution" not in scenario.blockers


def test_offline_truth_pack_phase2_input_dropped_has_categories():
    scenario = _scenario_map()["phase2_input_dropped_has_categories"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "INPUT_DROPPED"
    assert scenario.actual_result == "INPUT_DROPPED"
    assert scenario.phase2_input_state == "INPUT_DROPPED"
    assert scenario.phase2_drop_counts["hard_execution"] == 2
    assert scenario.final_emit_allowed is False


def test_offline_truth_pack_phase2_accepted_path_preserved():
    scenario = _scenario_map()["phase2_accepted_path_preserved"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "ACCEPTED"
    assert scenario.actual_result == "ACCEPTED"
    assert scenario.phase2_input_state == "ACCEPTED"
    assert scenario.executable_allowed is True
    assert scenario.reportable_executable is True
    assert scenario.final_emit_allowed is True


def test_offline_truth_pack_snapshot_mirrors_no_split_brain():
    scenario = _scenario_map()["snapshot_mirrors_no_split_brain"]

    assert scenario.pass_fail is True
    assert scenario.mirror_fields["logs"] == scenario.mirror_fields[".runtime"] == scenario.mirror_fields[".runtime/logs"]
    assert scenario.mirror_fields["logs"]["feed_truth_state"] == "RECOVERY_BLOCKED"
    assert scenario.mirror_fields["logs"]["feed_truth_allows_executable_candidates"] is False
    assert scenario.mirror_fields["logs"]["option_feed_block_reason_by_symbol"]["NIFTY"] == "NO_LIVE_OPTION_FEED"
    assert scenario.mirror_fields["logs"]["process_restart_required"] is True
    assert scenario.mirror_fields["logs"]["ws_reconnect_allowed"] is False


def test_offline_truth_pack_ws1006_terminal_state_blocks_execution():
    scenario = _scenario_map()["ws1006_terminal_state_blocks_execution"]

    assert scenario.pass_fail is True
    assert scenario.expected_result == "BLOCKED"
    assert scenario.actual_result == "BLOCKED"
    assert scenario.feed_truth_state == "RECOVERY_BLOCKED"
    assert scenario.executable_allowed is False
    assert scenario.reportable_executable is False
    assert scenario.final_emit_allowed is False
    assert "WS1006_PROCESS_RESTART_REQUIRED" in scenario.blockers


def test_offline_truth_pack_cli_writes_json_and_markdown(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_offline_feed_candidate_truth_proof_pack.py",
            "--out-dir",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    json_path = tmp_path / "offline_feed_candidate_truth_proof_pack.json"
    markdown_path = tmp_path / "summary.md"
    assert json_path.exists()
    assert markdown_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_allowed"] is False
    assert payload["scenario_count"] == 10
    assert payload["fail_count"] == 0
    assert payload["pass_count"] == 10
    assert payload["scenarios"][0]["scenario_name"] == "healthy_executable_candidate"
    assert "Offline Feed/Candidate Truth Proof Pack" in markdown_path.read_text(encoding="utf-8")


def test_offline_truth_pack_write_helper_fails_closed_on_expected_mismatch(tmp_path: Path):
    scenarios = tuple(default_scenarios())[:1]
    bad_case = scenarios[0]
    bad_scenario = bad_case.__class__(
        name=bad_case.name,
        expected_result="BLOCKED",
        feed_snapshot=bad_case.feed_snapshot,
        candidate=bad_case.candidate,
        phase2_raw_candidates=bad_case.phase2_raw_candidates,
        phase2_ranked_candidates=bad_case.phase2_ranked_candidates,
        latency_guard=bad_case.latency_guard,
        mirror_check=bad_case.mirror_check,
    )

    outcome = write_proof_pack(tmp_path, scenarios=[bad_scenario])

    assert outcome["exit_code"] != 0
    assert outcome["failures"]
    assert (tmp_path / "offline_feed_candidate_truth_proof_pack.json").exists()
    assert (tmp_path / "summary.md").exists()
