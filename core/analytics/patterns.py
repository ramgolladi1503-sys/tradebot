from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


PATTERN_MOMENTUM_EXPANSION = "MOMENTUM_EXPANSION"
PATTERN_GAMMA_BURST = "GAMMA_BURST"
PATTERN_TREND_EXTENSION = "TREND_EXTENSION"
PATTERN_UNKNOWN = "UNKNOWN"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def classify_pattern(row: Mapping[str, Any]) -> str:
    pre_return_5m = _safe_float(row.get("pre_return_5m"))
    pre_return_15m = _safe_float(row.get("pre_return_15m"))
    compression_score = _safe_float(row.get("compression_score"))
    volume_burst_ratio = _safe_float(row.get("volume_burst_ratio"))
    pct_move = _safe_float(row.get("pct_move"))
    post_t0_jump_5m = _safe_float(row.get("post_t0_jump_5m"))
    index_return_15m = _safe_float(row.get("index_return_15m"))

    if (
        pre_return_15m is not None
        and pre_return_15m > 0.10
        and volume_burst_ratio is not None
        and volume_burst_ratio > 2.0
        and compression_score is not None
        and compression_score < 0.55
    ):
        return PATTERN_MOMENTUM_EXPANSION

    if (
        pct_move is not None
        and pct_move >= 0.80
        and pre_return_5m is not None
        and pre_return_5m < 0.05
        and post_t0_jump_5m is not None
        and post_t0_jump_5m >= 0.20
    ):
        return PATTERN_GAMMA_BURST

    if (
        index_return_15m is not None
        and index_return_15m > 0.01
        and pre_return_15m is not None
        and pre_return_15m > 0.03
    ):
        return PATTERN_TREND_EXTENSION

    return PATTERN_UNKNOWN


def summarize_patterns(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        label = str(row.get("pattern") or classify_pattern(row))
        counter[label] += 1
    return dict(counter)
