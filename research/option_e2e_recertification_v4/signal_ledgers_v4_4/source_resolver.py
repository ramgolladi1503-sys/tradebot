from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .source_registry import SourceRecord, current_complete_json_path, historical_snapshot_candidates, is_historical_authority_candidate


def resolve_source(repo_root: Path, strategy_or_hypothesis_id: str, implementation_sha: str) -> SourceRecord:
    complete = current_complete_json_path(repo_root)
    manifest = repo_root / "runtime" / "market_data" / "upstox" / "20260714" / "manifest.json"
    dated = historical_snapshot_candidates(repo_root)
    searched = (
        str(complete.relative_to(repo_root)),
        str(manifest.relative_to(repo_root)),
        *[str(path.relative_to(repo_root)) for path in dated],
    )
    if manifest.exists():
        try:
            manifest_obj = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            manifest_obj = {}
        manifest_required = {"provider", "capture_or_asof_timestamp", "source_data_file", "source_data_hash", "instrument_token", "trading_symbol", "underlying", "option_right", "strike", "expiry", "contract_source_relationship", "immutable_content_hash", "asof_not_after_event"}
        if not (isinstance(manifest_obj, dict) and manifest_required.issubset(manifest_obj)):
            blocker = "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE"
            return SourceRecord(
                strategy_or_hypothesis_id=strategy_or_hypothesis_id,
                source_kind="CURRENT_MASTER_DIAGNOSTIC_ONLY",
                source_status="SIGNAL_SOURCE_BLOCKED",
                source_path=str(complete.relative_to(repo_root)),
                source_hash=_sha256_file(complete) if complete.exists() else "",
                implementation_sha=implementation_sha,
                dataset_path="",
                dataset_hash="",
                contract_path="",
                contract_hash="",
                oracle_path="research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py",
                resolution_status="MANIFEST_CONTRACT_IDENTITY_INCOMPLETE",
                blocker_code=blocker,
                paths_searched=searched,
                branches_searched=(),
                evidence_roots_searched=("runtime/upstox_instruments", "runtime/upstox_candidate_replay", "runtime/market_data/upstox"),
                source_domain="option_contract_authority",
            )
    blocker = "CURRENT_MASTER_ONLY_DIAGNOSTIC" if not dated else "CURRENT_MASTER_ONLY_DIAGNOSTIC"
    if dated:
        for source_path in dated:
            if not is_historical_authority_candidate(source_path, repo_root):
                continue
            payload = _sha256_file(source_path)
            return SourceRecord(
                strategy_or_hypothesis_id=strategy_or_hypothesis_id,
                source_kind="STRATEGY_SIGNAL_SOURCE_CANDIDATE",
                source_status="SIGNAL_SOURCE_RESOLVED",
                source_path=str(source_path.relative_to(repo_root)),
                source_hash=payload,
                implementation_sha=implementation_sha,
                dataset_path=str(source_path.relative_to(repo_root)),
                dataset_hash=payload,
                contract_path=str(source_path.relative_to(repo_root)),
                contract_hash=payload,
                oracle_path="research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py",
                resolution_status="SIGNAL_SOURCE_RESOLVED",
                blocker_code="",
                paths_searched=searched,
                branches_searched=(),
                evidence_roots_searched=("runtime/upstox_instruments", "runtime/upstox_candidate_replay", "runtime/market_data/upstox"),
                source_domain="strategy_signal_source",
            )
    source_kind = "CURRENT_MASTER_DIAGNOSTIC_ONLY"
    resolution_status = "CURRENT_MASTER_NOT_HISTORICAL_AUTHORITY"
    return SourceRecord(
        strategy_or_hypothesis_id=strategy_or_hypothesis_id,
        source_kind=source_kind,
        source_status="SIGNAL_SOURCE_BLOCKED",
        source_path=str(complete.relative_to(repo_root)),
        source_hash=_sha256_file(complete) if complete.exists() else "",
        implementation_sha=implementation_sha,
        dataset_path="",
        dataset_hash="",
        contract_path="",
        contract_hash="",
        oracle_path="research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py",
        resolution_status=resolution_status,
        blocker_code=blocker,
        paths_searched=searched,
        branches_searched=(),
        evidence_roots_searched=("runtime/upstox_instruments", "runtime/upstox_candidate_replay", "runtime/market_data/upstox"),
        source_domain="option_contract_authority" if complete.exists() else "unresolved",
    )


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
