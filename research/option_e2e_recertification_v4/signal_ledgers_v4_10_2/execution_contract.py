from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
from typing import Iterable


@dataclass(frozen=True)
class VwapExecutionContract:
    strategy_id: str
    canonical_alias_group: str
    implementation_path: str
    implementation_commit: str
    implementation_file_hash: str
    adapter_path: str
    adapter_hash: str
    dataset_path: str
    dataset_hash: str
    params_contract_path: str
    params_hash: str
    development_boundary: str
    holdout_boundary: str
    required_columns: tuple[str, ...]
    timezone: str
    completed_bar_policy: str
    feature_cutoff_policy: str
    signal_timestamp_policy: str
    earliest_entry_policy: str


_PLACEHOLDER_VALUES = {
    "",
    "unknown",
    "placeholder",
    "causal-adapter-placeholder",
}


def _is_placeholder(value: object) -> bool:
    text = str(value or "").strip().lower()
    return text in _PLACEHOLDER_VALUES


def _missing_or_placeholder(field_name: str, value: object, failures: list[str]) -> None:
    if _is_placeholder(value):
        failures.append(field_name)


def _hash_file(path: str) -> str:
    file_path = Path(path)
    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return digest


def validate_vwap_execution_contract(contract: VwapExecutionContract) -> dict[str, object]:
    failures: list[str] = []
    _missing_or_placeholder("implementation_commit", contract.implementation_commit, failures)
    _missing_or_placeholder("implementation_file_hash", contract.implementation_file_hash, failures)
    _missing_or_placeholder("adapter_hash", contract.adapter_hash, failures)
    _missing_or_placeholder("dataset_path", contract.dataset_path, failures)
    _missing_or_placeholder("dataset_hash", contract.dataset_hash, failures)
    _missing_or_placeholder("params_contract_path", contract.params_contract_path, failures)
    _missing_or_placeholder("params_hash", contract.params_hash, failures)

    file_hash_fields = (
        "implementation_path",
        "adapter_path",
        "dataset_path",
        "params_contract_path",
    )
    for path_field in file_hash_fields:
        path_value = getattr(contract, path_field)
        if not _is_placeholder(path_value) and not Path(str(path_value)).exists():
            failures.append(f"{path_field}:missing")
            continue
        if path_field == "implementation_path" and not _is_placeholder(contract.implementation_file_hash):
            if _hash_file(str(path_value)) != contract.implementation_file_hash:
                failures.append("implementation_file_hash:mismatch")
        if path_field == "adapter_path" and not _is_placeholder(contract.adapter_hash):
            if _hash_file(str(path_value)) != contract.adapter_hash:
                failures.append("adapter_hash:mismatch")
        if path_field == "dataset_path" and not _is_placeholder(contract.dataset_hash):
            if _hash_file(str(path_value)) != contract.dataset_hash:
                failures.append("dataset_hash:mismatch")
        if path_field == "params_contract_path" and not _is_placeholder(contract.params_hash):
            if _hash_file(str(path_value)) != contract.params_hash:
                failures.append("params_hash:mismatch")

    required_fields: Iterable[str] = (
        "strategy_id",
        "canonical_alias_group",
        "development_boundary",
        "holdout_boundary",
        "completed_bar_policy",
        "feature_cutoff_policy",
        "signal_timestamp_policy",
        "earliest_entry_policy",
        "timezone",
    )
    for field_name in required_fields:
        _missing_or_placeholder(field_name, getattr(contract, field_name), failures)

    return {
        "valid": not failures,
        "failures": failures,
        "contract_hashes": {
            "implementation_file_hash": contract.implementation_file_hash,
            "adapter_hash": contract.adapter_hash,
            "dataset_hash": contract.dataset_hash,
            "params_hash": contract.params_hash,
        },
    }


def build_real_implementation_hash(path: str) -> str:
    return _hash_file(path)
