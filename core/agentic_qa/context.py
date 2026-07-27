from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


def deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        key_text = str(key)
        if isinstance(value, Mapping) and isinstance(target.get(key_text), dict):
            deep_merge(target[key_text], value)
        elif isinstance(value, Mapping):
            target[key_text] = deep_merge({}, value)
        else:
            target[key_text] = deepcopy(value)
    return target


def dotted_get(payload: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    current: Any = payload
    for segment in key.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, current
