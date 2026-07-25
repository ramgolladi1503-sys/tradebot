from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VwapExecutionContract:
    strategy_id: str
    canonical_alias_group: str
    implementation_path: str
    implementation_commit: str
    implementation_file_hash: str
    adapter_path: str | None
    adapter_hash: str | None
    dataset_path: str
    dataset_hash: str
    parameter_manifest_path: str
    parameter_hash: str
    split_manifest_path: str
    split_hash: str
    required_columns: tuple[str, ...]
    timezone: str
    completed_bar_policy: str
    feature_cutoff_policy: str
    signal_timestamp_policy: str
    earliest_entry_policy: str


_PLACEHOLDERS = {"", "unknown", "placeholder", "causal-adapter-placeholder"}
_REQUIRED_SEMANTIC_FIELDS = (
    "strategy_id",
    "canonical_alias_group",
    "implementation_path",
    "implementation_commit",
    "implementation_file_hash",
    "dataset_path",
    "dataset_hash",
    "parameter_manifest_path",
    "parameter_hash",
    "split_manifest_path",
    "split_hash",
    "timezone",
    "completed_bar_policy",
    "feature_cutoff_policy",
    "signal_timestamp_policy",
    "earliest_entry_policy",
)


def _is_placeholder(value: object) -> bool:
    return str(value or "").strip().lower() in _PLACEHOLDERS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_path_hash(
    path_value: str,
    expected_hash: str,
    field_name: str,
    failures: list[str],
) -> None:
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        failures.append(f"{field_name}:missing")
        return
    if _sha256(path) != expected_hash:
        failures.append(f"{field_name}:hash_mismatch")


def validate_vwap_execution_contract(contract: VwapExecutionContract) -> dict[str, object]:
    """Validate file integrity only after semantic authorities have been frozen."""

    failures: list[str] = []
    for field_name in _REQUIRED_SEMANTIC_FIELDS:
        if _is_placeholder(getattr(contract, field_name)):
            failures.append(f"{field_name}:missing_or_placeholder")

    if not contract.required_columns:
        failures.append("required_columns:missing")

    _validate_path_hash(
        contract.implementation_path,
        contract.implementation_file_hash,
        "implementation",
        failures,
    )
    _validate_path_hash(contract.dataset_path, contract.dataset_hash, "dataset", failures)
    _validate_path_hash(
        contract.parameter_manifest_path,
        contract.parameter_hash,
        "parameter_manifest",
        failures,
    )
    _validate_path_hash(contract.split_manifest_path, contract.split_hash, "split_manifest", failures)

    if contract.adapter_path is None:
        if contract.adapter_hash is not None:
            failures.append("adapter_hash:unexpected_without_adapter")
    else:
        if _is_placeholder(contract.adapter_path) or _is_placeholder(contract.adapter_hash):
            failures.append("adapter:missing_or_placeholder")
        elif contract.adapter_hash is not None:
            _validate_path_hash(contract.adapter_path, contract.adapter_hash, "adapter", failures)

    return {
        "valid": not failures,
        "failures": sorted(set(failures)),
        "validation_scope": "FILE_INTEGRITY_AFTER_SEMANTIC_AUTHORITY",
        "contract_hashes": {
            "implementation_file_hash": contract.implementation_file_hash,
            "adapter_hash": contract.adapter_hash,
            "dataset_hash": contract.dataset_hash,
            "parameter_hash": contract.parameter_hash,
            "split_hash": contract.split_hash,
        },
    }


def build_real_implementation_hash(path: str) -> str:
    return _sha256(Path(path))
