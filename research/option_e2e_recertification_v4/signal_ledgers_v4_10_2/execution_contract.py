from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib


@dataclass(frozen=True)
class VwapExecutionContract:
    strategy_id: str
    canonical_alias_group: str
    implementation_path: str
    implementation_commit: str
    implementation_file_hash: str
    adapter_path: str | None
    adapter_hash: str | None
    source_manifest_path: str
    source_manifest_hash: str
    params_contract_path: str
    params_hash: str
    development_boundary_manifest_path: str
    development_boundary_hash: str
    holdout_boundary_manifest_path: str
    holdout_boundary_hash: str
    required_columns: tuple[str, ...]
    timezone: str
    completed_bar_policy: str
    feature_cutoff_policy: str
    signal_timestamp_policy: str
    earliest_entry_policy: str


_PLACEHOLDERS = {"", "unknown", "placeholder", "causal-adapter-placeholder"}


def _is_placeholder(value: object) -> bool:
    return str(value or "").strip().lower() in _PLACEHOLDERS


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_vwap_execution_contract(contract: VwapExecutionContract) -> dict[str, object]:
    failures: list[str] = []
    for field_name in (
        "strategy_id",
        "canonical_alias_group",
        "implementation_path",
        "implementation_commit",
        "implementation_file_hash",
        "source_manifest_path",
        "source_manifest_hash",
        "params_contract_path",
        "params_hash",
        "development_boundary_manifest_path",
        "development_boundary_hash",
        "holdout_boundary_manifest_path",
        "holdout_boundary_hash",
        "timezone",
        "completed_bar_policy",
        "feature_cutoff_policy",
        "signal_timestamp_policy",
        "earliest_entry_policy",
    ):
        if _is_placeholder(getattr(contract, field_name)):
            failures.append(field_name)

    if not Path(contract.implementation_path).exists():
        failures.append("implementation_path:missing")
    elif _sha256(contract.implementation_path) != contract.implementation_file_hash:
        failures.append("implementation_file_hash:mismatch")

    for field_name, hash_field in (
        ("source_manifest_path", "source_manifest_hash"),
        ("params_contract_path", "params_hash"),
        ("development_boundary_manifest_path", "development_boundary_hash"),
        ("holdout_boundary_manifest_path", "holdout_boundary_hash"),
    ):
        path = getattr(contract, field_name)
        if not Path(path).exists():
            failures.append(f"{field_name}:missing")
        elif _sha256(path) != getattr(contract, hash_field):
            failures.append(f"{hash_field}:mismatch")

    if contract.adapter_path is not None:
        if _is_placeholder(contract.adapter_path):
            failures.append("adapter_path")
        elif not Path(contract.adapter_path).exists():
            failures.append("adapter_path:missing")
        elif contract.adapter_hash is None or _sha256(contract.adapter_path) != contract.adapter_hash:
            failures.append("adapter_hash:mismatch")
    elif contract.adapter_hash is not None:
        failures.append("adapter_hash:unexpected")

    return {
        "valid": not failures,
        "failures": failures,
        "contract_hashes": {
            "implementation_file_hash": contract.implementation_file_hash,
            "adapter_hash": contract.adapter_hash,
            "source_manifest_hash": contract.source_manifest_hash,
            "params_hash": contract.params_hash,
            "development_boundary_hash": contract.development_boundary_hash,
            "holdout_boundary_hash": contract.holdout_boundary_hash,
        },
    }


def build_real_implementation_hash(path: str) -> str:
    return _sha256(path)
