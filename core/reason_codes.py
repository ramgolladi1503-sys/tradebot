from __future__ import annotations

from typing import Iterable, List


def normalize_reason_codes(value) -> List[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return list(value.keys())
    if isinstance(value, Iterable):
        return [str(v) for v in value]
    return [str(value)]
