from __future__ import annotations

import hashlib
from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.execution_contract import (
    VwapExecutionContract,
    validate_vwap_execution_contract,
)
from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.artifact_parser import parse_vwap_artifacts
from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2 import ledger_builder


def _real_contract(repo: Path) -> VwapExecutionContract:
    sources = {
        "implementation_path": str(repo / "strategies" / "movement" / "vwap_reclaim.py"),
    }
    return VwapExecutionContract(
        strategy_id="VWAP_RECLAIM",
        canonical_alias_group="VWAP_RECLAIM",
        implementation_path=sources["implementation_path"],
        implementation_commit="ec82dbbd64556f94ec38eab1017848d1b6669659",
        implementation_file_hash=ledger_builder.build_real_implementation_hash(sources["implementation_path"]),
        adapter_path=str(repo / "strategies" / "movement" / "vwap_reclaim.py"),
        adapter_hash=ledger_builder.build_real_implementation_hash(sources["implementation_path"]),
        dataset_path=str(repo / "runtime" / "strategy_validation" / "VWAP_RECLAIM" / "candidate_replay_report.json"),
        dataset_hash=hashlib.sha256((repo / "runtime" / "strategy_validation" / "VWAP_RECLAIM" / "candidate_replay_report.json").read_bytes()).hexdigest(),
        params_contract_path=str(repo / "docs" / "agent_reviews" / "option_e2e_v4_10_1_option_replay_blocker_invalidation.md"),
        params_hash=hashlib.sha256((repo / "docs" / "agent_reviews" / "option_e2e_v4_10_1_option_replay_blocker_invalidation.md").read_bytes()).hexdigest(),
        development_boundary="closed",
        holdout_boundary="closed",
        required_columns=("timestamp", "open", "high", "low", "close", "volume"),
        timezone="Asia/Kolkata",
        completed_bar_policy="completed-bar-only",
        feature_cutoff_policy="feature_cutoff <= signal_ts",
        signal_timestamp_policy="timezone-aware",
        earliest_entry_policy="signal_ts < earliest_entry_ts",
    )


def test_v4_10_2_excludes_invalidated_history_and_returns_no_signal_rows() -> None:
    repo = Path(".")
    records, summary, detail = ledger_builder.build_signal_ledgers(repo)

    assert records == []
    assert summary["execution_status"] == "SIGNAL_EXECUTION_BLOCKED_WITH_EXACT_EXECUTION_EVIDENCE"
    assert summary["oracle_verdict"] == "SIGNAL_EXECUTION_BLOCKED_WITH_EXACT_EXECUTION_EVIDENCE"
    assert detail["reconciliation"]["status"] == "SIGNAL_EXECUTION_BLOCKED"
    assert detail["reconciliation"]["signal_count"] == 0
    assert detail["reconciliation"]["invalidated_historical_record_count"] >= 1
    assert detail["artifacts"]["legacy_option_replay_audit_records"]
    assert detail["artifacts"]["invalidated_historical_records"]
    assert detail["contract_report"]["valid"] is True
    assert detail["execution"]["status"] == "SIGNAL_EXECUTION_BLOCKED_WITH_EXACT_EXECUTION_EVIDENCE"


def test_v4_10_2_contract_validator_rejects_placeholders() -> None:
    repo = Path(".")
    contract = _real_contract(repo)
    invalid_contract = VwapExecutionContract(
        **{**contract.__dict__, "dataset_hash": "placeholder", "params_hash": ""}
    )

    report = validate_vwap_execution_contract(invalid_contract)

    assert report["valid"] is False
    assert "dataset_hash" in report["failures"]
    assert "params_hash" in report["failures"]


def test_v4_10_2_builder_never_calls_executor_until_contract_validates(monkeypatch) -> None:
    repo = Path(".")

    def fail_execute(*_args, **_kwargs):
        raise AssertionError("executor should not be called for invalid contracts")

    monkeypatch.setattr(ledger_builder, "execute_vwap_contract", fail_execute)
    monkeypatch.setattr(
        ledger_builder,
        "validate_vwap_execution_contract",
        lambda _contract: {"valid": False, "failures": ["dataset_hash"], "contract_hashes": {}},
    )

    records, summary, detail = ledger_builder.build_signal_ledgers(repo)

    assert records == []
    assert summary["execution_status"] == "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE"
    assert detail["execution"]["blockers"] == ["dataset_hash"]


def test_v4_10_2_parser_separates_legacy_option_replay_from_invalidated_history() -> None:
    repo = Path(".")
    parsed = parse_vwap_artifacts(repo)

    assert all(record["artifact_type"] == "historical_signal_ledger_record" for record in parsed["invalidated_historical_records"])
    assert any(record["artifact_type"] == "candidate_replay_report" for record in parsed["legacy_option_replay_audit_records"])
