from __future__ import annotations

import re
from typing import Any, Mapping

from . import benchmark as B

_ORIGINAL_MAP_RECORD = B.map_record


def _two_lengths(text: str, token: str) -> tuple[int, int] | None:
    patterns = (
        rf"\b(\d{{1,3}})\s*[/xX,&-]\s*(\d{{1,3}})\s*{token}\b",
        rf"\b{token}\s*(\d{{1,3}})\s*[/xX,&-]\s*(\d{{1,3}})\b",
        rf"\b(\d{{1,3}})\s*{token}\b.*?\b(\d{{1,3}})\s*{token}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if not match:
            continue
        a, b = int(match.group(1)), int(match.group(2))
        if 2 <= a <= 300 and 2 <= b <= 300 and a != b:
            return tuple(sorted((a, b)))
    return None


def _opening_range_minutes(text: str) -> int | None:
    patterns = (
        r"\bfirst\s+(\d{1,3})\s*[- ]?(?:minute|min)\b",
        r"\bopening\s+range\D{0,20}(\d{1,3})\s*[- ]?(?:minute|min)\b",
        r"\borb\D{0,10}(\d{1,3})\s*[- ]?(?:minute|min)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 180:
                return value
    return None


def guarded_map_record(record: Mapping[str, Any]) -> tuple[B.MechanismSpec | None, str]:
    spec, status = _ORIGINAL_MAP_RECORD(record)
    if spec is None:
        return spec, status

    text = f"{record.get('title', '')} {record.get('description', '')}"
    if spec.family == "EMA_CROSS":
        lengths = _two_lengths(text, "ema")
        if lengths is not None:
            fast, slow = lengths
            spec = B.MechanismSpec(
                "EMA_CROSS",
                (("fast", float(fast)), ("slow", float(slow))),
                "description-derived EMA crossover lengths",
            )
    elif spec.family == "SMA_CROSS":
        lengths = _two_lengths(text, "sma")
        if lengths is not None:
            fast, slow = lengths
            spec = B.MechanismSpec(
                "SMA_CROSS",
                (("fast", float(fast)), ("slow", float(slow))),
                "description-derived SMA crossover lengths",
            )
    elif spec.family == "OPENING_RANGE_BREAKOUT":
        minutes = _opening_range_minutes(text)
        if minutes is not None and minutes != 15:
            return None, "OPENING_RANGE_WINDOW_NOT_IMPLEMENTED"
        spec = B.MechanismSpec(
            "OPENING_RANGE_BREAKOUT",
            (("minutes", 15.0),),
            "description-consistent 15-minute opening-range breakout",
        )
    return spec, status


def install() -> None:
    B.map_record = guarded_map_record
