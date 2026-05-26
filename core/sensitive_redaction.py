from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_NORMALIZED_EXACT_SENSITIVE_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "auth_token",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "credential",
    "credentials",
    "jwt",
    "kite_access_token",
    "password",
    "refresh_token",
    "secret",
    "session_id",
    "session_token",
}

_SENSITIVE_SUFFIXES = (
    "_token",
    "_secret",
    "_password",
    "_cookie",
    "_credential",
    "_credentials",
)

_KEY_VALUE_PATTERN = re.compile(
    r"(?i)(access[_-]?token|api[_-]?key|authorization|password|secret|session)\s*([=:])\s*['\"]?[^\s,'\"]+"
)
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[a-z0-9._\-+/=]{12,}")


def _normalize_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")


def is_sensitive_key(key: object) -> bool:
    normalized = _normalize_key(key)
    if not normalized:
        return False
    if normalized in _NORMALIZED_EXACT_SENSITIVE_KEYS:
        return True
    return normalized.endswith(_SENSITIVE_SUFFIXES) or normalized.startswith(("secret_", "password_"))


def redact_text(value: object) -> str:
    text = str(value or "")
    if not text:
        return text
    safe = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", text)
    safe = _KEY_VALUE_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        safe,
    )
    return safe


def redact_sensitive_data(value: Any) -> Any:
    """Return a JSON-safe copy with credential-looking fields redacted."""

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out[str(key)] = REDACTED if is_sensitive_key(key) else redact_sensitive_data(item)
        return out
    if isinstance(value, (bytes, bytearray)):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_sensitive_data(item) for item in value]
    return value


def summarize_context(value: Any) -> dict[str, Any]:
    """Return a non-sensitive incident-safe context summary.

    This intentionally avoids preserving arbitrary values. Incident and halt records are
    durable operational artifacts, so they should keep shape/debug hints without carrying
    raw broker/auth/runtime payloads.
    """

    if isinstance(value, Mapping):
        keys = [str(key) for key in value.keys()]
        visible_keys = sorted(key for key in keys if not is_sensitive_key(key))[:25]
        sensitive_count = sum(1 for key in keys if is_sensitive_key(key))
        return {
            "context_type": "mapping",
            "field_count": len(keys),
            "visible_fields": visible_keys,
            "redacted_field_count": sensitive_count,
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {
            "context_type": "sequence",
            "item_count": len(value),
        }
    if value is None:
        return {"context_type": "none"}
    return {"context_type": type(value).__name__}


def redact_json_line(line: str) -> str:
    try:
        payload = json.loads(line)
    except Exception:
        return REDACTED
    return json.dumps(redact_sensitive_data(payload), sort_keys=True, default=str)


__all__ = [
    "REDACTED",
    "is_sensitive_key",
    "redact_json_line",
    "redact_sensitive_data",
    "redact_text",
    "summarize_context",
]
