from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .adapter_contract import SignalLedgerContract
from .coverage_report import build_coverage_report
from .ledger_oracle import certify_ledger
from .source_registry import SourceRecord, source_record_payload
from .source_resolver import resolve_source


def build_signal_ledgers(repo_root: Path, inventory_path: Path) -> tuple[list[SignalLedgerContract], dict[str, Any], dict[str, Any]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    implementation_sha = _sha256_file(Path(__file__).resolve())
    source_records: list[SourceRecord] = []
    ledgers: list[SignalLedgerContract] = []
    for entity in inventory.get("entities", []):
        if not entity.get("counted_as_strategy"):
            continue
        record = resolve_source(repo_root, str(entity["id"]), implementation_sha)
        source_records.append(record)
        ledgers.append(
            SignalLedgerContract(
                strategy_or_hypothesis_id=str(entity["id"]),
                canonical_alias_group=str(entity.get("v4_certification_track") or entity.get("entity_type") or ""),
                signal_id=f"{entity['id']}:{record.resolution_status}",
                session="frozen",
                feature_cutoff_ts="",
                signal_ts="",
                earliest_entry_ts="",
                direction="UNKNOWN",
                signal_strength="0",
                params_hash="",
                source_artifact_hash=record.source_hash,
                implementation_sha=implementation_sha,
                dataset_hash=record.dataset_hash,
                fold_id="",
                is_holdout=False,
                source_kind=record.source_kind,
                oracle_status=record.resolution_status,
            )
        )
    oracle = certify_ledger(ledgers)
    coverage = build_coverage_report(source_records)
    summary = {
        "strategy_count": len(ledgers),
        "resolved_count": coverage["resolved"],
        "blocked_count": coverage["blocked"],
        "blocker_codes": coverage["blocker_codes"],
        "oracle_verdict": oracle["verdict"],
    }
    return ledgers, summary, {"source_records": [source_record_payload(record) for record in source_records], "oracle": oracle, "coverage": coverage}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
