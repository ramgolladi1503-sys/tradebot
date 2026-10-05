from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime
from enum import Enum
from typing import Any

from .models import Evidence


def canonical_json(value: Any) -> str:
    """Stable JSON encoding used for hashes and persisted work items."""
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def evidence_payload(evidence: Evidence) -> dict[str, Any]:
    payload = _plain(evidence)
    payload.pop("content_hash", None)
    return payload


def seal_evidence(evidence: Evidence, work_item_hash: str, sequence: int,
                  previous_hash: str) -> Evidence:
    evidence = replace(evidence, work_item_hash=work_item_hash,
                       sequence=sequence, previous_hash=previous_hash)
    return replace(evidence, content_hash=sha256_json(evidence_payload(evidence)))


def verify_evidence_hash(evidence: Evidence) -> bool:
    return bool(evidence.content_hash) and evidence.content_hash == sha256_json(evidence_payload(evidence))


def validate_timestamp(timestamp: str) -> None:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
