from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .artifact_parser import parse_vwap_artifacts
from .determinism import build_determinism_fingerprint
from .execution_contract import (
    VwapExecutionContract,
    build_real_implementation_hash,
    validate_vwap_execution_contract,
)
from .ledger_oracle import certify_ledger
from .reconciliation import reconcile
from .source_discovery import discover_vwap_sources
from .source_search_manifest import build_source_search_manifest


def build_signal_ledgers(repo_root: Path):
    sources = discover_vwap_sources(repo_root)
    artifacts = parse_vwap_artifacts(repo_root)
    implementation_hash = build_real_implementation_hash(sources["implementation_path"])
    source_manifest = build_source_search_manifest(repo_root)
    params_path = repo_root / "core" / "strategy_parameter_profiles.py"
    dev_boundary_path = repo_root / "research" / "option_e2e_recertification_v4" / "v4_10_2_development_boundary.json"
    holdout_boundary_path = repo_root / "research" / "option_e2e_recertification_v4" / "v4_10_2_holdout_boundary.json"

    for path, payload in (
        (dev_boundary_path, {"boundary": "development", "sessions": ["2024-06-28"], "source": "tradebot-data/independent_underlying_confirmation_v3"}),
        (holdout_boundary_path, {"boundary": "holdout", "sessions": ["2024-07-09", "2024-07-10"], "source": "tradebot-ml-evidence/structural-state-discovery-v5"}),
    ):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    contract = VwapExecutionContract(
        strategy_id="VWAP_RECLAIM",
        canonical_alias_group="VWAP_RECLAIM",
        implementation_path=sources["implementation_path"],
        implementation_commit="5bdb7de782db0d5321ba988b08252639841359ed",
        implementation_file_hash=implementation_hash,
        adapter_path=None,
        adapter_hash=None,
        source_manifest_path=source_manifest["path"],
        source_manifest_hash=source_manifest["hash"],
        params_contract_path=str(params_path),
        params_hash=hashlib.sha256(params_path.read_bytes()).hexdigest(),
        development_boundary_manifest_path=str(dev_boundary_path),
        development_boundary_hash=hashlib.sha256(dev_boundary_path.read_bytes()).hexdigest(),
        holdout_boundary_manifest_path=str(holdout_boundary_path),
        holdout_boundary_hash=hashlib.sha256(holdout_boundary_path.read_bytes()).hexdigest(),
        required_columns=("timestamp", "open", "high", "low", "close", "volume"),
        timezone="Asia/Kolkata",
        completed_bar_policy="completed-bar-only",
        feature_cutoff_policy="feature_cutoff <= signal_ts",
        signal_timestamp_policy="timezone-aware",
        earliest_entry_policy="signal_ts < earliest_entry_ts",
    )
    contract_report = validate_vwap_execution_contract(contract)
    records: list[dict[str, object]] = []
    execution = {
        "status": "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE",
        "blockers": contract_report["failures"] or [source_manifest["reason"]],
        "execution_allowed": False,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
        "read_only": True,
    }
    oracle = certify_ledger(records, contract_report, source_manifest)
    reconciliation = reconcile(records, artifacts)
    detail = {
        "sources": sources,
        "artifacts": artifacts,
        "execution": execution,
        "contract": contract.__dict__,
        "contract_report": contract_report,
        "source_manifest": source_manifest,
        "oracle": oracle,
        "reconciliation": reconciliation,
        "determinism": build_determinism_fingerprint(repo_root),
    }
    return records, {"oracle_verdict": oracle["verdict"], "execution_status": execution["status"]}, detail
