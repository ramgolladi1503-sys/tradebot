from __future__ import annotations

from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.artifact_parser import parse_vwap_artifacts
from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.ledger_builder import build_signal_ledgers


def test_v4_10_2_excludes_invalidated_history_and_returns_no_signal_rows() -> None:
    repo = Path(".")
    records, summary, detail = build_signal_ledgers(repo)

    assert records == []
    assert summary["execution_status"] == "SIGNAL_EXECUTION_BLOCKED"
    assert summary["oracle_verdict"] == "SIGNAL_EXECUTION_BLOCKED"
    assert detail["reconciliation"]["status"] == "SIGNAL_EXECUTION_BLOCKED"
    assert detail["reconciliation"]["signal_count"] == 0
    assert detail["reconciliation"]["invalidated_historical_record_count"] >= 1
    assert detail["artifacts"]["legacy_option_replay_audit_records"]
    assert detail["artifacts"]["invalidated_historical_records"]


def test_v4_10_2_parser_separates_legacy_option_replay_from_invalidated_history() -> None:
    repo = Path(".")
    parsed = parse_vwap_artifacts(repo)

    assert all(record["artifact_type"] == "historical_signal_ledger_record" for record in parsed["invalidated_historical_records"])
    assert any(record["artifact_type"] == "candidate_replay_report" for record in parsed["legacy_option_replay_audit_records"])
