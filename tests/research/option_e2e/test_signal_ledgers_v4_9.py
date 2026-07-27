from __future__ import annotations

from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_9.ledger_builder import build_signal_ledgers
from research.option_e2e_recertification_v4.signal_ledgers_v4_9.git_discovery import run_git_discovery
from research.option_e2e_recertification_v4.signal_ledgers_v4_9.filesystem_discovery import run_filesystem_discovery


def test_git_and_filesystem_discovery_execute_bounded_commands() -> None:
    repo = Path(".")

    git_result = run_git_discovery(repo)
    fs_result = run_filesystem_discovery()

    assert git_result["commands"]
    assert any("git branch --all" in item["command"] for item in git_result["commands"])
    assert all("exit_code" in item for item in git_result["commands"])
    assert isinstance(fs_result["roots"], list)


def test_v4_9_builder_records_discovery_without_false_no_signals() -> None:
    repo = Path(".")
    ledgers, summary, detail = build_signal_ledgers(repo)

    assert ledgers == []
    assert summary["oracle_verdict"] == "SIGNAL_RECOVERY_NOT_EXECUTED"
    assert summary["lane_count"] >= 18
    assert summary["historical_candidate_count"] >= 1
    assert detail["oracle"]["verdict"] == "SIGNAL_RECOVERY_NOT_EXECUTED"
    assert detail["reconciliation"]["status"] == "SIGNAL_RECOVERY_NOT_EXECUTED"
    assert detail["git_discovery"]["commands"]
    assert detail["inventory"]["entries"]
