from __future__ import annotations

from copy import deepcopy

from .determinism import semantic_hash


def validate_semantic_hash(payload: object, expected_sha256: str) -> bool:
    return semantic_hash(payload) == expected_sha256


def run_tamper_probe(payload: dict[str, object], field_name: str, replacement: object) -> dict[str, object]:
    original_hash = semantic_hash(payload)
    mutated = deepcopy(payload)
    mutated[field_name] = replacement
    mutated_hash = semantic_hash(mutated)
    return {
        "field_name": field_name,
        "detected": original_hash != mutated_hash,
        "original_semantic_sha256": original_hash,
        "mutated_semantic_sha256": mutated_hash,
    }
