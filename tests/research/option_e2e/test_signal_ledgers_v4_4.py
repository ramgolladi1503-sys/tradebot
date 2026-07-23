from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_4.ledger_builder import build_signal_ledgers
from research.option_e2e_recertification_v4.signal_ledgers_v4_4.ledger_oracle import certify_ledger
from research.option_e2e_recertification_v4.signal_ledgers_v4_4.adapter_contract import SignalLedgerContract
from research.option_e2e_recertification_v4.signal_ledgers_v4_4.source_resolver import resolve_source


def _write_manifest(repo_root: Path, payload: dict[str, object]) -> Path:
    manifest = repo_root / "runtime" / "market_data" / "upstox" / "20260714" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def test_current_master_is_diagnostic_only(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "runtime" / "upstox_instruments").mkdir(parents=True)
    (repo / "runtime" / "upstox_instruments" / "complete.json").write_text("[]", encoding="utf-8")

    record = resolve_source(repo, "VWAP_RECLAIM", "abc123")

    assert record.source_kind == "CURRENT_MASTER_DIAGNOSTIC_ONLY"
    assert record.source_status == "SIGNAL_SOURCE_BLOCKED"
    assert record.resolution_status == "CURRENT_MASTER_NOT_HISTORICAL_AUTHORITY"
    assert record.blocker_code == "CURRENT_MASTER_ONLY_DIAGNOSTIC"
    assert record.dataset_path == ""
    assert record.dataset_hash == ""
    assert record.contract_path == ""
    assert record.contract_hash == ""
    assert record.source_domain == "option_contract_authority"


def test_incomplete_manifest_returns_exact_blocker_and_stays_read_only(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "runtime" / "upstox_instruments").mkdir(parents=True)
    complete = repo / "runtime" / "upstox_instruments" / "complete.json"
    complete.write_text("[]", encoding="utf-8")
    manifest = _write_manifest(
        repo,
        {
            "session_date": "20260714",
            "finalized_at": "2026-07-14T15:35:00.659041",
            "coverage_keys": 878,
        },
    )

    record = resolve_source(repo, "VWAP_RECLAIM", "abc123")

    assert record.source_path == "runtime/upstox_instruments/complete.json"
    assert record.source_kind == "CURRENT_MASTER_DIAGNOSTIC_ONLY"
    assert record.source_status == "SIGNAL_SOURCE_BLOCKED"
    assert record.blocker_code == "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE"
    assert record.resolution_status == "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE"
    assert record.dataset_path == ""
    assert record.dataset_hash == ""
    assert record.contract_path == ""
    assert record.contract_hash == ""
    assert record.source_hash == hashlib.sha256(complete.read_bytes()).hexdigest()
    assert manifest.exists()
    assert "provider" not in json.loads(manifest.read_text(encoding="utf-8"))


def test_tamper_does_not_upgrade_blocked_resolution(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "runtime" / "upstox_instruments").mkdir(parents=True)
    complete = repo / "runtime" / "upstox_instruments" / "complete.json"
    complete.write_text("[]", encoding="utf-8")
    manifest = _write_manifest(
        repo,
        {
            "session_date": "20260714",
            "finalized_at": "2026-07-14T15:35:00.659041",
            "coverage_keys": 878,
        },
    )

    first = resolve_source(repo, "VWAP_RECLAIM", "abc123")
    manifest.write_text(
        json.dumps(
            {
                "session_date": "20260714",
                "finalized_at": "2026-07-14T15:35:00.659041",
                "coverage_keys": 878,
                "tampered": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    second = resolve_source(repo, "VWAP_RECLAIM", "abc123")

    assert first.source_hash == second.source_hash
    assert first.source_kind == second.source_kind == "CURRENT_MASTER_DIAGNOSTIC_ONLY"
    assert first.blocker_code == second.blocker_code == "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE"
    assert first.dataset_hash == second.dataset_hash == ""
    assert first.contract_hash == second.contract_hash == ""


def test_ledger_builder_refuses_placeholder_certification(tmp_path: Path) -> None:
    repo = tmp_path
    inventory = repo / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "id": "VWAP_RECLAIM",
                        "counted_as_strategy": True,
                        "v4_certification_track": "v4",
                        "entity_type": "strategy",
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (repo / "runtime" / "upstox_instruments").mkdir(parents=True)
    (repo / "runtime" / "upstox_instruments" / "complete.json").write_text("[]", encoding="utf-8")

    ledgers, summary, detail = build_signal_ledgers(repo, inventory)

    assert ledgers == []
    assert summary["strategy_count"] == 0
    assert summary["oracle_verdict"] == "SIGNAL_LEDGER_NOT_CERTIFIED"
    assert detail["coverage"]["resolved"] == 0
    assert detail["coverage"]["blocked"] == 1
    assert detail["source_records"][0]["source_status"] == "SIGNAL_SOURCE_BLOCKED"


def test_oracle_rejects_empty_placeholder_ledger() -> None:
    result = certify_ledger([])
    assert result["verdict"] == "SIGNAL_LEDGER_NOT_CERTIFIED"


def test_oracle_rejects_placeholder_ledger_fields() -> None:
    result = certify_ledger(
        [
            SignalLedgerContract(
                strategy_or_hypothesis_id="VWAP_RECLAIM",
                canonical_alias_group="v4",
                signal_id="VWAP_RECLAIM:SIGNAL_SOURCE_RESOLVED",
                session="frozen",
                feature_cutoff_ts="",
                signal_ts="",
                earliest_entry_ts="",
                direction="UNKNOWN",
                signal_strength="0",
                params_hash="",
                source_artifact_hash="hash",
                implementation_sha="impl",
                dataset_hash="dataset",
                fold_id="",
                is_holdout=False,
                source_kind="STRATEGY_SIGNAL_SOURCE_CANDIDATE",
                oracle_status="SIGNAL_SOURCE_RESOLVED",
            )
        ]
    )
    assert result["verdict"] == "SIGNAL_LEDGER_NOT_CERTIFIED"
    assert "MISSING_FEATURE_CUTOFF_TS" in result["failures"]
    assert "MISSING_SIGNAL_TS" in result["failures"]
    assert "MISSING_EARLIEST_ENTRY_TS" in result["failures"]
    assert "MISSING_PARAMS_HASH" in result["failures"]


def test_oracle_rejects_unknown_direction_and_placeholder_implementation_sha() -> None:
    result = certify_ledger(
        [
            SignalLedgerContract(
                strategy_or_hypothesis_id="VWAP_RECLAIM",
                canonical_alias_group="v4",
                signal_id="VWAP_RECLAIM:SIGNAL_SOURCE_RESOLVED",
                session="frozen",
                feature_cutoff_ts="2026-07-14T09:15:00+05:30",
                signal_ts="2026-07-14T09:16:00+05:30",
                earliest_entry_ts="2026-07-14T09:16:30+05:30",
                direction="UNKNOWN",
                signal_strength="0.42",
                params_hash="params",
                source_artifact_hash="sourcehash",
                implementation_sha="placeholder",
                dataset_hash="datasethash",
                fold_id="fold-1",
                is_holdout=False,
                source_kind="STRATEGY_SIGNAL_SOURCE_CANDIDATE",
                oracle_status="SIGNAL_SOURCE_RESOLVED",
            )
        ]
    )
    assert result["verdict"] == "SIGNAL_LEDGER_NOT_CERTIFIED"
    assert "UNKNOWN_DIRECTION" in result["failures"]
    assert "INVALID_IMPLEMENTATION_SHA" in result["failures"]
