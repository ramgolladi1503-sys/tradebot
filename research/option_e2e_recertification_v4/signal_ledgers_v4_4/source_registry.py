from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    strategy_or_hypothesis_id: str
    source_kind: str
    source_status: str
    source_path: str
    source_hash: str
    implementation_sha: str
    dataset_path: str
    dataset_hash: str
    contract_path: str
    contract_hash: str
    oracle_path: str
    resolution_status: str
    blocker_code: str
    paths_searched: tuple[str, ...]
    branches_searched: tuple[str, ...]
    evidence_roots_searched: tuple[str, ...]
    source_domain: str


def current_complete_json_path(repo_root: Path) -> Path:
    return repo_root / "runtime" / "upstox_instruments" / "complete.json"


def historical_snapshot_candidates(repo_root: Path) -> list[Path]:
    roots = [
        repo_root / "runtime" / "upstox_instruments",
        repo_root / "runtime" / "upstox_candidate_replay",
        repo_root / "runtime" / "market_data" / "upstox",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".json", ".csv", ".parquet"}:
                continue
            if any(token in path.name for token in ("202", "snapshot", "manifest")):
                candidates.append(path)
    return sorted(candidates)


def is_historical_authority_candidate(path: Path, repo_root: Path) -> bool:
    try:
        rel = path.relative_to(repo_root).as_posix()
    except Exception:
        rel = path.as_posix()
    if rel.startswith("runtime/market_data/upstox/"):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        required = {"provider", "capture_or_asof_timestamp", "source_data_file", "source_data_hash", "instrument_token", "trading_symbol", "underlying", "option_right", "strike", "expiry", "contract_source_relationship", "immutable_content_hash", "asof_not_after_event"}
        return bool(isinstance(obj, dict) and required.issubset(obj))
    if rel.startswith("runtime/upstox_instruments/"):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        if not isinstance(obj, list) or not obj:
            return False
        required = {"provider", "capture_or_asof_timestamp", "instrument_key", "trading_symbol", "underlying", "option_right", "strike", "expiry", "source_hash", "valid_at_signal_timestamp"}
        return any(isinstance(row, dict) and required.issubset(row) for row in obj)
    return False


def source_record_payload(record: SourceRecord) -> dict[str, Any]:
    return {
        "strategy_or_hypothesis_id": record.strategy_or_hypothesis_id,
        "source_kind": record.source_kind,
        "source_status": record.source_status,
        "source_path": record.source_path,
        "source_hash": record.source_hash,
        "implementation_sha": record.implementation_sha,
        "dataset_path": record.dataset_path,
        "dataset_hash": record.dataset_hash,
        "contract_path": record.contract_path,
        "contract_hash": record.contract_hash,
        "oracle_path": record.oracle_path,
        "resolution_status": record.resolution_status,
        "blocker_code": record.blocker_code,
        "paths_searched": list(record.paths_searched),
        "branches_searched": list(record.branches_searched),
        "evidence_roots_searched": list(record.evidence_roots_searched),
        "source_domain": record.source_domain,
    }
