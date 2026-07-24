from __future__ import annotations

from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_10.git_discovery import (
    run_git_discovery,
)
from research.option_e2e_recertification_v4.signal_ledgers_v4_10.ledger_builder import (
    build_signal_ledgers,
)

_SIGNAL_FIELDS = {
    "signal_id",
    "feature_cutoff_ts",
    "signal_ts",
    "earliest_entry_ts",
    "direction",
}


def test_v4_10_legacy_vertical_slice_cannot_be_signal_certification() -> None:
    lane_audits, summary, detail = build_signal_ledgers(Path("."))

    assert summary["oracle_verdict"] != "SIGNAL_LEDGER_CERTIFIED"
    assert detail["oracle"]["verdict"] != "SIGNAL_LEDGER_CERTIFIED"
    assert detail["reconciliation"]["status"] == "SOURCE_BLOCKED"
    assert lane_audits
    for audit in lane_audits:
        assert audit["status"] == "SOURCE_BLOCKED"
        assert audit["read_only"] is True
        assert audit["execution_allowed"] is False
        assert audit["broker_api_called"] is False
        assert audit["is_order_action"] is False
        assert audit["allowed_for_live_execution"] is False
        assert not (_SIGNAL_FIELDS & set(audit))


def test_v4_10_git_discovery_records_command_outcomes() -> None:
    result = run_git_discovery(Path("."))
    commands = result["commands"]

    assert commands
    assert any(item["command"] == "git worktree list --porcelain" for item in commands)
    assert any("-SVWAP_RECLAIM" in item["command"] for item in commands)
    assert all("exit_code" in item for item in commands)
    assert all("stdout" in item and "stderr" in item for item in commands)
