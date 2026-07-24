from __future__ import annotations

import hashlib
import json
from typing import Any

_VOLATILE_KEYS = {"diagnostics", "physical_path", "created_at", "generated_at", "output_dir"}


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def semantic_hash(payload: object) -> str:
    normalized = _normalize(payload)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_determinism_fingerprint(payload: object) -> dict[str, str]:
    return {
        "algorithm": "sha256-canonical-json-v1",
        "semantic_sha256": semantic_hash(payload),
    }


def compare_deterministic_outputs(first: object, second: object) -> dict[str, object]:
    first_hash = semantic_hash(first)
    second_hash = semantic_hash(second)
    return {
        "match": first_hash == second_hash,
        "first_semantic_sha256": first_hash,
        "second_semantic_sha256": second_hash,
    }
