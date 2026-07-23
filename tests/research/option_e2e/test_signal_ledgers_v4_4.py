from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
    assert record.resolution_status == "CURRENT_MASTER_NOT_HISTORICAL_AUTHORITY"
    assert record.blocker_code == "CURRENT_MASTER_ONLY_DIAGNOSTIC"
    assert record.dataset_path == ""
    assert record.dataset_hash == ""
    assert record.contract_path == ""
    assert record.contract_hash == ""


def test_incomplete_manifest_returns_exact_blocker_and_uses_no_current_master_fields(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "runtime" / "upstox_instruments").mkdir(parents=True)
    (repo / "runtime" / "upstox_instruments" / "complete.json").write_text("[]", encoding="utf-8")
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
    assert record.blocker_code == "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE"
    assert record.resolution_status == "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE"
    assert record.dataset_path == ""
    assert record.dataset_hash == ""
    assert record.contract_path == ""
    assert record.contract_hash == ""
    assert record.source_hash == hashlib.sha256((repo / "runtime" / "upstox_instruments" / "complete.json").read_bytes()).hexdigest()
    assert manifest.exists()
    assert "provider" not in json.loads(manifest.read_text(encoding="utf-8"))


def test_tamper_does_not_upgrade_current_master_only_resolution(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "runtime" / "upstox_instruments").mkdir(parents=True)
    (repo / "runtime" / "upstox_instruments" / "complete.json").write_text("[]", encoding="utf-8")
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
