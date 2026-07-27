from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_SECRET_KEY = re.compile(r"(api[_-]?key|secret|token|password|authorization|cookie)", re.I)
_SECRET_VALUE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._-]{8,}|(?:sk|AIza|ghp|github_pat_)[a-z0-9_-]{8,})"
)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            output[key_text] = "[REDACTED]" if _SECRET_KEY.search(key_text) else redact_secrets(item)
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[REDACTED]", value)
    return value


def contains_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_SECRET_KEY.search(str(key)) or contains_secret(item) for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(contains_secret(item) for item in value)
    return isinstance(value, str) and bool(_SECRET_VALUE.search(value))
