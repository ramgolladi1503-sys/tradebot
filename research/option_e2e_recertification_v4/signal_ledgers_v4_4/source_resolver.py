from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .source_registry import SourceRecord, current_complete_json_path, historical_snapshot_candidates, is_historical_authority_candidate


def resolve_source(repo_root: Path, strategy_or_hypothesis_id: str, implementation_sha: str) -> SourceRecord:
    complete = current_complete_json_path(repo_root)
    dated = historical_snapshot_candidates(repo_root)
    searched = (
        str(complete.relative_to(repo_root)) if complete.exists() else str(complete.relative_to(repo_root)),
        *[str(path.relative_to(repo_root)) for path in dated],
    )
    if dated:
        for source_path in dated:
            if not is_historical_authority_candidate(source_path, repo_root):
                continue
            payload = _sha256_file(source_path)
            return SourceRecord(
                strategy_or_hypothesis_id=strategy_or_hypothesis_id,
                source_kind="DATED_HISTORICAL_SNAPSHOT",
                source_path=str(source_path.relative_to(repo_root)),
                source_hash=payload,
                implementation_sha=implementation_sha,
                dataset_path=str(source_path.relative_to(repo_root)),
                dataset_hash=payload,
                contract_path=str(source_path.relative_to(repo_root)),
                contract_hash=payload,
                oracle_path="research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py",
                resolution_status="SIGNAL_LEDGER_CERTIFIED",
                blocker_code="",
                paths_searched=searched,
                branches_searched=("origin/main", "HEAD"),
                evidence_roots_searched=("runtime/upstox_instruments", "runtime/upstox_candidate_replay", "runtime/market_data/upstox"),
            )
        return SourceRecord(
            strategy_or_hypothesis_id=strategy_or_hypothesis_id,
            source_kind="CURRENT_MASTER_DIAGNOSTIC_ONLY",
            source_path=str(complete.relative_to(repo_root)),
            source_hash=_sha256_file(complete) if complete.exists() else "",
            implementation_sha=implementation_sha,
            dataset_path="",
            dataset_hash="",
            contract_path="",
            contract_hash="",
            oracle_path="research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py",
            resolution_status="MANIFEST_CONTRACT_IDENTITY_INCOMPLETE",
            blocker_code="MANIFEST_CONTRACT_IDENTITY_INCOMPLETE",
            paths_searched=searched,
            branches_searched=("origin/main", "HEAD"),
            evidence_roots_searched=("runtime/upstox_instruments", "runtime/upstox_candidate_replay", "runtime/market_data/upstox"),
        )
    blocker = "HISTORICAL_MAPPING_SNAPSHOT_NOT_FOUND" if not complete.exists() else "CURRENT_MASTER_ONLY_DIAGNOSTIC"
    return SourceRecord(
        strategy_or_hypothesis_id=strategy_or_hypothesis_id,
        source_kind="CURRENT_MASTER_DIAGNOSTIC_ONLY",
        source_path=str(complete.relative_to(repo_root)),
        source_hash=_sha256_file(complete) if complete.exists() else "",
        implementation_sha=implementation_sha,
        dataset_path="",
        dataset_hash="",
        contract_path="",
        contract_hash="",
        oracle_path="research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py",
        resolution_status="HOLDOUT_ACCESS_PROHIBITED" if blocker == "HISTORICAL_MAPPING_SNAPSHOT_NOT_FOUND" else "CURRENT_MASTER_NOT_HISTORICAL_AUTHORITY",
        blocker_code=blocker,
        paths_searched=searched,
        branches_searched=("origin/main", "HEAD"),
        evidence_roots_searched=("runtime/upstox_instruments", "runtime/upstox_candidate_replay", "runtime/market_data/upstox"),
    )


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
