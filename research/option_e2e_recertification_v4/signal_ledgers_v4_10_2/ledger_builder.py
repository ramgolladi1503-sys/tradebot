from __future__ import annotations

from pathlib import Path

from .artifact_parser import parse_vwap_artifacts
from .determinism import build_determinism_fingerprint
from .execution_contract import VwapExecutionContract
from .ledger_oracle import certify_ledger
from .lane_executor import execute_vwap_contract
from .reconciliation import reconcile
from .source_discovery import discover_vwap_sources
from .vwap_adapter import build_vwap_adapter


def build_signal_ledgers(repo_root: Path):
    sources = discover_vwap_sources(repo_root)
    artifacts = parse_vwap_artifacts(repo_root)
    adapter = build_vwap_adapter(repo_root)
    contract = VwapExecutionContract(
        strategy_id="VWAP_RECLAIM",
        canonical_alias_group="VWAP_RECLAIM",
        implementation_path=sources["implementation_path"],
        implementation_commit="unknown",
        implementation_file_hash="unknown",
        adapter_path=adapter["path"],
        adapter_hash=adapter["hash"],
        dataset_path="",
        dataset_hash="",
        params_contract_path="",
        params_hash="",
        development_boundary="closed",
        holdout_boundary="closed",
        required_columns=("timestamp", "open", "high", "low", "close", "volume"),
        timezone="Asia/Kolkata",
        completed_bar_policy="completed-bar-only",
        feature_cutoff_policy="feature_cutoff <= signal_ts",
        signal_timestamp_policy="timezone-aware",
        earliest_entry_policy="signal_ts < earliest_entry_ts",
    )
    execution = execute_vwap_contract(contract, artifacts)
    records: list[dict[str, object]] = []
    oracle = certify_ledger(records)
    reconciliation = reconcile(records, artifacts)
    detail = {
        "sources": sources,
        "artifacts": artifacts,
        "execution": execution,
        "contract": contract.__dict__,
        "oracle": oracle,
        "reconciliation": reconciliation,
        "determinism": build_determinism_fingerprint(repo_root),
    }
    return records, {"oracle_verdict": oracle["verdict"], "execution_status": execution["status"]}, detail

