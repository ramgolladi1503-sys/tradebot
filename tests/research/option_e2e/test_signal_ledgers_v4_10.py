from __future__ import annotations

from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_10.ledger_builder import build_signal_ledgers
from research.option_e2e_recertification_v4.signal_ledgers_v4_10.git_discovery import run_git_discovery
from research.option_e2e_recertification_v4.signal_ledgers_v4_10.signal_artifact_loader import load_signal_artifacts


def test_v4_10_vertical_slice_reports_exact_blockers() -> None:
    repo = Path(".")
    ledgers, summary, detail = build_signal_ledgers(repo)

    assert len(ledgers) == 3
    assert summary["oracle_verdict"] == "SOURCE_BLOCKED"
    assert summary["reconciliation_status"] == "SOURCE_BLOCKED"
    assert detail["oracle"]["verdict"] == "SOURCE_BLOCKED"
    assert detail["reconciliation"]["exact_blockers"]
    assert "DATA_BLOCKED_REAL_OPTION_LTP_MISSING" in detail["reconciliation"]["exact_blockers"]
    assert "DATA_BLOCKED_STRESS_REPLAY_UNSUPPORTED_BY_DATA_CAPABILITY" in detail["reconciliation"]["exact_blockers"]
    assert detail["reconciliation"]["blocker_domains"] == [
        "SIGNAL_EXECUTION_BLOCKER",
        "SIGNAL_SOURCE_BLOCKER",
    ]
    assert {item["strategy_id"] for item in detail["lane_reports"]} == {"VWAP_RECLAIM", "OPENING_RANGE_BREAKOUT", "OPENING_STATE_MOMENTUM"}
    assert all(record["status"] == "SOURCE_BLOCKED" for record in detail["lane_reports"])
    assert all(record["read_only"] is True for record in detail["lane_reports"])
    assert detail["inventory"]["entries"]


def test_v4_10_discovery_and_artifact_loading_are_lane_scoped() -> None:
    repo = Path(".")
    git_result = run_git_discovery(repo)
    artifacts = load_signal_artifacts(repo)

    assert git_result["commands"]
    assert any("git worktree list --porcelain" in item["command"] for item in git_result["commands"])
    assert any(item["command"].startswith("git log --all -SVWAP_RECLAIM --oneline") for item in git_result["commands"])
    assert any(item["strategy_id"] == "VWAP_RECLAIM" for item in artifacts)
    assert any(item["strategy_id"] == "OPENING_RANGE_BREAKOUT" for item in artifacts)
    assert any(item["strategy_id"] == "OPENING_STATE_MOMENTUM" for item in artifacts)
