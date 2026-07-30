from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import EvidenceRef

_SENSITIVE_TOKENS = {
    "access_token", "api_key", "apikey", "authorization", "client_secret", "password",
    "refresh_token", "secret", "session_token", "token", "openai_api_key",
}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~-]{12,}", re.IGNORECASE),
)


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if lowered in _SENSITIVE_TOKENS or any(token in lowered for token in _SENSITIVE_TOKENS):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = redact(item)
        return out
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        out = value
        for pattern in _SECRET_VALUE_PATTERNS:
            out = pattern.sub("[REDACTED]", out)
        return out
    return value


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    row_count: int
    errors: tuple[str, ...]


class EvidenceLedger:
    """Append-only, redacted SHA-256 chained evidence ledger."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event_type: str, payload: Mapping[str, Any], *, session_id: str) -> EvidenceRef:
        clean_payload = redact(dict(payload or {}))
        with self._lock:
            previous_sha = self._last_sha()
            evidence_id = f"EV-{uuid.uuid4().hex}"
            body = {
                "schema_version": 1,
                "evidence_id": evidence_id,
                "session_id": str(session_id),
                "event_type": str(event_type),
                "created_at": utc_now_iso(),
                "previous_sha256": previous_sha,
                "payload": clean_payload,
            }
            digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
            row = {**body, "sha256": digest}
            with self.path.open("a", encoding="utf-8", buffering=1) as handle:
                handle.write(canonical_json(row) + "\n")
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        return EvidenceRef(evidence_id=evidence_id, event_type=str(event_type), sha256=digest)

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    out.append({"_parse_error": line_number})
                    continue
                if isinstance(row, dict):
                    out.append(row)
        return out

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        wanted = str(evidence_id)
        for row in self.rows():
            if str(row.get("evidence_id") or "") == wanted:
                return row
        return None

    def payload(self, evidence_id: str) -> Mapping[str, Any] | None:
        row = self.get(evidence_id)
        payload = row.get("payload") if isinstance(row, Mapping) else None
        return dict(payload) if isinstance(payload, Mapping) else None

    def verify(self) -> ChainVerification:
        errors: list[str] = []
        previous = "GENESIS"
        rows = self.rows()
        for index, row in enumerate(rows):
            if "_parse_error" in row:
                errors.append(f"row_{index}:invalid_json")
                continue
            claimed = str(row.get("sha256") or "")
            body = {key: value for key, value in row.items() if key != "sha256"}
            actual = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
            if claimed != actual:
                errors.append(f"row_{index}:sha256_mismatch")
            if str(row.get("previous_sha256") or "") != previous:
                errors.append(f"row_{index}:previous_sha256_mismatch")
            if self._contains_secret(row):
                errors.append(f"row_{index}:unredacted_secret")
            previous = claimed or actual
        return ChainVerification(valid=not errors, row_count=len(rows), errors=tuple(errors))

    def require(self, evidence_ids: Iterable[str]) -> tuple[bool, tuple[str, ...]]:
        missing = tuple(sorted({str(item) for item in evidence_ids if self.get(str(item)) is None}))
        return not missing, missing

    def _last_sha(self) -> str:
        rows = self.rows()
        if not rows:
            return "GENESIS"
        return str(rows[-1].get("sha256") or "GENESIS")

    @staticmethod
    def _contains_secret(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lowered = str(key).lower()
                if any(token in lowered for token in _SENSITIVE_TOKENS) and item not in (None, "", "[REDACTED]"):
                    return True
                if EvidenceLedger._contains_secret(item):
                    return True
            return False
        if isinstance(value, (list, tuple)):
            return any(EvidenceLedger._contains_secret(item) for item in value)
        if isinstance(value, str):
            return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)
        return False
