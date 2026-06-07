"""Read-only candidate pool quality and diversity analysis.

This module summarizes candidate-pool breadth, concentration, and fallback
contamination without changing execution, ranking formulas, broker behavior, or
strategy generation. It is intentionally conservative: missing metadata does not
invent diversity.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

POOL_QUALITY_SCHEMA_VERSION = 1
_BULLISH_DIRECTIONS = frozenset({"BUY_CALL", "LONG_CALL", "CALL", "CE", "BULLISH", "BUY", "LONG"})
_BEARISH_DIRECTIONS = frozenset({"BUY_PUT", "LONG_PUT", "PUT", "PE", "BEARISH", "SELL", "SHORT", "SELL_CALL", "SELL_PUT"})
_NO_TRADE_DIRECTIONS = frozenset({"NO_TRADE", "NONE", "SKIP"})


@dataclass(frozen=True)
class CandidatePoolQualityReport:
    schema_version: int
    read_only: bool
    append: bool
    candidate_count: int
    executable_count: int
    near_executable_count: int
    advisory_count: int
    blocked_count: int
    fallback_count: int
    unique_symbol_count: int
    unique_strategy_family_count: int
    bullish_count: int
    bearish_count: int
    range_count: int
    other_direction_count: int
    duplicate_group_count: int
    duplicate_candidate_count: int
    same_symbol_concentration_count: int
    same_family_concentration_count: int
    fallback_contamination_ratio: float
    diversity_score: float
    quality_score: float
    readiness_state: str
    reasons: tuple[str, ...]
    symbol_counts: dict[str, int]
    strategy_family_counts: dict[str, int]
    direction_counts: dict[str, int]
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "candidate_count": self.candidate_count,
            "executable_count": self.executable_count,
            "near_executable_count": self.near_executable_count,
            "advisory_count": self.advisory_count,
            "blocked_count": self.blocked_count,
            "fallback_count": self.fallback_count,
            "unique_symbol_count": self.unique_symbol_count,
            "unique_strategy_family_count": self.unique_strategy_family_count,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "range_count": self.range_count,
            "other_direction_count": self.other_direction_count,
            "duplicate_group_count": self.duplicate_group_count,
            "duplicate_candidate_count": self.duplicate_candidate_count,
            "same_symbol_concentration_count": self.same_symbol_concentration_count,
            "same_family_concentration_count": self.same_family_concentration_count,
            "fallback_contamination_ratio": self.fallback_contamination_ratio,
            "diversity_score": self.diversity_score,
            "quality_score": self.quality_score,
            "readiness_state": self.readiness_state,
            "reasons": list(self.reasons),
            "symbol_counts": dict(self.symbol_counts),
            "strategy_family_counts": dict(self.strategy_family_counts),
            "direction_counts": dict(self.direction_counts),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def analyze_candidate_pool(rows: Iterable[Mapping[str, Any]]) -> CandidatePoolQualityReport:
    items = tuple(_row(row) for row in rows or ())
    candidate_count = len(items)
    executable_count = sum(1 for row in items if _is_executable(row))
    near_executable_count = sum(1 for row in items if _is_near_executable(row))
    advisory_count = sum(1 for row in items if _is_advisory(row))
    blocked_count = sum(1 for row in items if _is_blocked(row))
    fallback_count = sum(1 for row in items if _is_fallback(row))

    symbol_counts = Counter(_text(row.get("symbol")).upper() or "UNKNOWN" for row in items)
    family_counts = Counter(_text(row.get("strategy_family")).lower() or "unknown" for row in items)
    direction_counts = Counter(_direction_family(row) for row in items)

    duplicate_group_count = _duplicate_group_count(items)
    duplicate_candidate_count = _duplicate_candidate_count(items)
    same_symbol_concentration_count = max(symbol_counts.values(), default=0)
    same_family_concentration_count = max(family_counts.values(), default=0)
    unique_symbol_count = len(symbol_counts)
    unique_strategy_family_count = len(family_counts)
    bullish_count = int(direction_counts.get("BULLISH", 0))
    bearish_count = int(direction_counts.get("BEARISH", 0))
    range_count = int(direction_counts.get("RANGE", 0))
    other_direction_count = max(candidate_count - bullish_count - bearish_count - range_count, 0)

    fallback_contamination_ratio = _ratio(fallback_count, candidate_count)
    diversity_score = _diversity_score(
        candidate_count=candidate_count,
        unique_symbol_count=unique_symbol_count,
        unique_strategy_family_count=unique_strategy_family_count,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        range_count=range_count,
    )
    quality_score, readiness_state, reasons = _quality_score(
        candidate_count=candidate_count,
        executable_count=executable_count,
        near_executable_count=near_executable_count,
        advisory_count=advisory_count,
        blocked_count=blocked_count,
        fallback_count=fallback_count,
        unique_symbol_count=unique_symbol_count,
        unique_strategy_family_count=unique_strategy_family_count,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        range_count=range_count,
        duplicate_group_count=duplicate_group_count,
        duplicate_candidate_count=duplicate_candidate_count,
        same_symbol_concentration_count=same_symbol_concentration_count,
        same_family_concentration_count=same_family_concentration_count,
        fallback_contamination_ratio=fallback_contamination_ratio,
        diversity_score=diversity_score,
    )

    return CandidatePoolQualityReport(
        schema_version=POOL_QUALITY_SCHEMA_VERSION,
        read_only=True,
        append=False,
        candidate_count=candidate_count,
        executable_count=executable_count,
        near_executable_count=near_executable_count,
        advisory_count=advisory_count,
        blocked_count=blocked_count,
        fallback_count=fallback_count,
        unique_symbol_count=unique_symbol_count,
        unique_strategy_family_count=unique_strategy_family_count,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        range_count=range_count,
        other_direction_count=other_direction_count,
        duplicate_group_count=duplicate_group_count,
        duplicate_candidate_count=duplicate_candidate_count,
        same_symbol_concentration_count=same_symbol_concentration_count,
        same_family_concentration_count=same_family_concentration_count,
        fallback_contamination_ratio=fallback_contamination_ratio,
        diversity_score=diversity_score,
        quality_score=quality_score,
        readiness_state=readiness_state,
        reasons=reasons,
        symbol_counts=dict(sorted(symbol_counts.items(), key=lambda item: (-item[1], item[0]))),
        strategy_family_counts=dict(sorted(family_counts.items(), key=lambda item: (-item[1], item[0]))),
        direction_counts=dict(sorted(direction_counts.items(), key=lambda item: (-item[1], item[0]))),
    )


def pool_quality_penalty_for_row(row: Mapping[str, Any], pool: CandidatePoolQualityReport) -> tuple[float, list[str]]:
    payload = _row(row)
    reasons: list[str] = []
    penalty = 0.0

    if _is_fallback(payload):
        penalty += 0.24
        reasons.append("fallback_candidate")
    if _is_blocked(payload):
        penalty += 0.18
        reasons.append("blocked_candidate")

    symbol = _text(payload.get("symbol")).upper() or "UNKNOWN"
    symbol_count = int(pool.symbol_counts.get(symbol, 0))
    if symbol_count > 1:
        penalty += min(0.18, 0.06 * (symbol_count - 1))
        reasons.append("same_symbol_concentration")

    family = _text(payload.get("strategy_family")).lower() or "unknown"
    family_count = int(pool.strategy_family_counts.get(family, 0))
    if family_count > 1:
        penalty += min(0.14, 0.04 * (family_count - 1))
        reasons.append("same_family_concentration")

    direction = _direction_family(payload)
    direction_count = int(pool.direction_counts.get(direction, 0))
    if direction_count > 1:
        penalty += min(0.10, 0.03 * (direction_count - 1))
        reasons.append("direction_concentration")

    if pool.duplicate_group_count > 0:
        penalty += min(0.08, 0.02 * pool.duplicate_group_count)
        reasons.append("duplicate_group_concentration")
    if pool.fallback_contamination_ratio > 0.25:
        penalty += min(0.12, pool.fallback_contamination_ratio * 0.18)
        reasons.append("fallback_contamination")
    if pool.quality_score < 0.5:
        penalty += 0.05
        reasons.append("low_pool_quality")

    return _clamp01(penalty), _dedupe(reasons)


def _quality_score(
    *,
    candidate_count: int,
    executable_count: int,
    near_executable_count: int,
    advisory_count: int,
    blocked_count: int,
    fallback_count: int,
    unique_symbol_count: int,
    unique_strategy_family_count: int,
    bullish_count: int,
    bearish_count: int,
    range_count: int,
    duplicate_group_count: int,
    duplicate_candidate_count: int,
    same_symbol_concentration_count: int,
    same_family_concentration_count: int,
    fallback_contamination_ratio: float,
    diversity_score: float,
) -> tuple[float, str, tuple[str, ...]]:
    reasons: list[str] = []
    score = 1.0

    if candidate_count == 0:
        return 0.0, "EMPTY", ("empty_pool",)

    if candidate_count < 2:
        score -= 0.32
        reasons.append("thin_pool")
    if executable_count == 0:
        score -= 0.20
        reasons.append("no_executable_candidates")
    if fallback_count > 0:
        score -= min(0.30, fallback_contamination_ratio * 0.34 + 0.05)
        reasons.append("fallback_contamination")
    if duplicate_candidate_count > 0:
        score -= min(0.18, 0.04 * duplicate_candidate_count)
        reasons.append("duplicate_candidates")
    if duplicate_group_count > 0:
        score -= min(0.10, 0.02 * duplicate_group_count)
        reasons.append("duplicate_groups")
    if same_symbol_concentration_count > 1:
        score -= min(0.18, 0.05 * (same_symbol_concentration_count - 1))
        reasons.append("same_symbol_concentration")
    if same_family_concentration_count > 1:
        score -= min(0.14, 0.04 * (same_family_concentration_count - 1))
        reasons.append("same_family_concentration")
    if bullish_count == 0 or bearish_count == 0:
        score -= 0.10
        reasons.append("one_sided_direction_coverage")
    if range_count == 0 and (bullish_count > 0 or bearish_count > 0):
        score -= 0.03
        reasons.append("missing_range_coverage")
    score -= max(0.0, 0.20 - diversity_score) * 0.35
    if near_executable_count > 0:
        score += min(0.04, 0.01 * near_executable_count)
    if advisory_count > 0:
        score += min(0.03, 0.005 * advisory_count)
    if blocked_count > candidate_count / 2:
        score -= 0.08
        reasons.append("blocked_heavy_pool")

    score = _clamp01(score)
    if score >= 0.75:
        state = "DIVERSE"
    elif candidate_count < 2:
        state = "THIN"
    elif fallback_contamination_ratio >= 0.4:
        state = "FALLBACK_HEAVY"
    elif unique_symbol_count <= 1 or unique_strategy_family_count <= 1 or same_symbol_concentration_count >= 3:
        state = "CONCENTRATED"
    elif bullish_count == 0 or bearish_count == 0:
        state = "ONE_SIDED"
    else:
        state = "BALANCED"
    return score, state, _dedupe(reasons)


def _diversity_score(
    *,
    candidate_count: int,
    unique_symbol_count: int,
    unique_strategy_family_count: int,
    bullish_count: int,
    bearish_count: int,
    range_count: int,
) -> float:
    if candidate_count <= 0:
        return 0.0
    symbol_ratio = unique_symbol_count / candidate_count
    family_ratio = unique_strategy_family_count / candidate_count
    directional_ratio = min(1.0, (bool(bullish_count) + bool(bearish_count) + bool(range_count)) / 3.0)
    spread_ratio = min(1.0, unique_symbol_count / max(1, unique_strategy_family_count))
    return _clamp01((symbol_ratio * 0.34) + (family_ratio * 0.32) + (directional_ratio * 0.24) + (min(spread_ratio, 1.0) * 0.10))


def _duplicate_group_count(rows: tuple[Mapping[str, Any], ...]) -> int:
    groups: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (
            _text(row.get("symbol")).upper() or "UNKNOWN",
            _text(row.get("strategy_family")).lower() or "unknown",
            _direction_family(row),
        )
        groups[key] = groups.get(key, 0) + 1
    return sum(1 for count in groups.values() if count > 1)


def _duplicate_candidate_count(rows: tuple[Mapping[str, Any], ...]) -> int:
    groups: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (
            _text(row.get("symbol")).upper() or "UNKNOWN",
            _text(row.get("strategy_family")).lower() or "unknown",
            _direction_family(row),
        )
        groups[key] = groups.get(key, 0) + 1
    return sum(max(count - 1, 0) for count in groups.values())


def _is_executable(row: Mapping[str, Any]) -> bool:
    return bool(
        _text(row.get("expectancy_status") or row.get("keep_watch_kill_status")).upper() == "KEEP"
        and _text(row.get("permission")).upper() == "EXECUTE"
        and _text(row.get("final_action")).upper() == "EXECUTE"
        and _text(row.get("execution_truth_state")).upper() not in {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}
        and bool(row.get("reportable_executable"))
        and bool(row.get("execution_allowed"))
        and not _is_fallback(row)
    )


def _is_near_executable(row: Mapping[str, Any]) -> bool:
    status = _text(row.get("expectancy_status") or row.get("keep_watch_kill_status")).upper()
    if status != "KEEP":
        return False
    if _is_fallback(row) or _is_blocked(row):
        return False
    permission = _text(row.get("permission")).upper()
    execution_status = _text(row.get("execution_status")).lower()
    return bool(permission in {"QUEUE_ONLY", "ADVISORY_ONLY"} or execution_status in {"queue_only", "advisory_only"})


def _is_advisory(row: Mapping[str, Any]) -> bool:
    status = _text(row.get("expectancy_status") or row.get("keep_watch_kill_status")).upper()
    return bool(status == "WATCH" and not _is_fallback(row) and not _is_blocked(row))


def _is_blocked(row: Mapping[str, Any]) -> bool:
    execution_truth_state = _text(row.get("execution_truth_state")).upper()
    if execution_truth_state in {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}:
        return True
    blockers = list(row.get("blockers") or []) + list(row.get("execution_truth_blockers") or [])
    for blocker in blockers:
        text = _text(blocker).upper()
        if any(token in text for token in ("STALE", "LTP_STALE", "WS_DISCONNECTED", "GLOBAL_FEED_UNHEALTHY", "RECOVERY_BLOCKED", "WS1006", "PROCESS_RESTART_REQUIRED")):
            return True
    return _text(row.get("permission")).upper() == "BLOCK" or _text(row.get("final_action")).upper() == "BLOCK"


def _is_fallback(row: Mapping[str, Any]) -> bool:
    if bool(row.get("fallback_used")):
        return True
    if _text(row.get("candidate_class")).lower() == "fallback":
        return True
    if _text(row.get("row_kind")).lower() in {"fallback", "recovered_fallback"}:
        return True
    if "fallback" in _text(row.get("candidate_type")).lower():
        return True
    if "fallback" in _text(row.get("candidate_origin")).lower():
        return True
    if _text(row.get("trade_id")).startswith("softrej_"):
        return True
    if _text(row.get("quote_source")).upper() in {"REST_FALLBACK", "SYNTHETIC_OFFHOURS", "SUBSCRIPTION_FAILED"}:
        return True
    return False


def _direction_family(row: Mapping[str, Any]) -> str:
    normalized = _text(row.get("direction") or row.get("side") or row.get("direction_family") or "").upper()
    if normalized in _BULLISH_DIRECTIONS:
        return "BULLISH"
    if normalized in _BEARISH_DIRECTIONS:
        return "BEARISH"
    if normalized in _NO_TRADE_DIRECTIONS:
        return "NO_TRADE"
    return "OTHER"


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    return dict(row) if isinstance(row, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _clamp01(numerator / denominator)


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


__all__ = [
    "POOL_QUALITY_SCHEMA_VERSION",
    "CandidatePoolQualityReport",
    "analyze_candidate_pool",
    "pool_quality_penalty_for_row",
]
