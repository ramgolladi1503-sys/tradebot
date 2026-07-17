from __future__ import annotations

import re
from typing import Any


_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"mark\s+(this\s+)?strategy\s+(as\s+)?profitable", re.I),
    re.compile(r"override\s+(the\s+)?(judge|system|guardrail)", re.I),
    re.compile(r"place\s+(a\s+)?(live\s+)?order", re.I),
    re.compile(r"reveal\s+(the\s+)?(api\s+)?key", re.I),
)
_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{25,}"),
    re.compile(r"(?i)bearer\s+[0-9A-Za-z._~+/-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[^\s,;]+"),
)
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "gemini_api_key",
    "broker_credentials",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
}


def redact_secret_text(value: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    redacted = value
    for index, pattern in enumerate(_SECRET_PATTERNS, start=1):
        if pattern.search(redacted):
            flags.append(f"secret_pattern_{index}")
            redacted = pattern.sub("[SECRET_REDACTED]", redacted)
    return redacted, flags


def sanitize_untrusted_text(value: str) -> tuple[str, list[str]]:
    sanitized, flags = redact_secret_text(value)
    for index, pattern in enumerate(_INJECTION_PATTERNS, start=1):
        if pattern.search(sanitized):
            flags.append(f"prompt_injection_pattern_{index}")
            sanitized = pattern.sub("[UNTRUSTED_INSTRUCTION_REMOVED]", sanitized)
    return sanitized, sorted(set(flags))


def build_model_evidence_view(value: Any) -> tuple[Any, list[str]]:
    flags: list[str] = []

    def walk(item: Any) -> Any:
        if isinstance(item, str):
            cleaned, found = sanitize_untrusted_text(item)
            flags.extend(found)
            return cleaned
        if isinstance(item, dict):
            output: dict[str, Any] = {}
            for key, child in item.items():
                normalized = str(key).strip().lower()
                if normalized in _SECRET_KEYS:
                    flags.append(f"secret_key_removed:{normalized}")
                    continue
                output[str(key)] = walk(child)
            return output
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, tuple):
            return [walk(child) for child in item]
        return item

    return walk(value), sorted(set(flags))
