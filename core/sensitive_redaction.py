from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_FRAGMENTS = (
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "credential",
    "jwt",
    "kite_access_token",
    "password",
    "refresh_token",
    "secret",
    "session",
    "token",
)

_KEY_VALUE_PATTERN = re.compile(
    r"(?i)(access[_-]?token|api[_-]?key|authorization|password|secret|session)\s*([=:])\s*['\"]?[^\s,'\"]+"
)
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[a-z0-9._\-+/=]{12,}")


def is_sensitive_key(key: object) -> bool:
    text = str(key or "").strip().lower()
    if not text:
        return False
    return any(fragment in text for fragment in _SENSITIVE_KEY_FRAGMENTS)


def redact_text(value: object) -> str:
    text = str(value or "")
    if not text:
        return text
    safe = _KEY_VALUE_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", text)
    safe = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", safe)
    return safe


def redact_sensitive_data(value: Any) -> Any:
    """Return a JSON-safe copy with secret-looking keys and token-like text redacted.

    This is intentionally conservative. Trading diagnostics and audit records may include
    arbitrary broker responses; preserving those objects verbatim is not worth leaking a
    Kite token, API key, session id, cookie, or bearer credential into logs/runtime files.
    """
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out[str(key)] = REDACTED if is_sensitive_key(key) else redact_sensitive_data(item)
        return out
    if isinstance(value, (str, bytes, bytearray)):
        if isinstance(value, str):
            return redact_text(value)
        return REDACTED
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_sensitive_data(item) for item in value]
    return value
