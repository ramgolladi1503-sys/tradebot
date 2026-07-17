from __future__ import annotations

import re
from typing import Any


_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"mark\s+(this\s+)?strategy\s+(as\s+)?profitable", re.I),
    re.compile(r"override\s+(the\s+)?(judge|system|guardrail)", re.I),
    re.compile(r"place\s+(a\s+)?(live\s+)?order", re.I),
    re.compile(r"reveal\s+(the\s+)?(api\s+)?key", re.I),
)


def sanitize_untrusted_text(value: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    sanitized = value
    for index, pattern in enumerate(_PATTERNS, start=1):
        if pattern.search(sanitized):
            flags.append(f"prompt_injection_pattern_{index}")
            sanitized = pattern.sub("[UNTRUSTED_INSTRUCTION_REMOVED]", sanitized)
    return sanitized, flags


def build_model_evidence_view(value: Any) -> tuple[Any, list[str]]:
    flags: list[str] = []

    def walk(item: Any) -> Any:
        if isinstance(item, str):
            cleaned, found = sanitize_untrusted_text(item)
            flags.extend(found)
            return cleaned
        if isinstance(item, dict):
            return {str(key): walk(child) for key, child in item.items() if str(key) not in {"api_key", "broker_credentials", "access_token"}}
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, tuple):
            return [walk(child) for child in item]
        return item

    return walk(value), sorted(set(flags))
