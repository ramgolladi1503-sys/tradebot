from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterable


PASS = "PASS"
WARN = "WARN"
BLOCK = "BLOCK"
PRODUCTION_GRADE_THRESHOLD = 80

_SILENT_FALLBACK_MARKERS = (
    "except Exception: pass",
    "except: pass",
    "return None",
    "or {}",
    "or []",
    "ignore_errors=True",
    "silent fallback",
)
_FAIL_CLOSED_MARKERS = (
    "raise ValueError",
    "raise RuntimeError",
    "return False",
    "blocked_reason",
    "rejection_reason",
    "fail_closed",
)
_SAFE_DEFAULT_MARKERS = ("default=False", "safe_default", "enabled=False", "allow=False")
_EVIDENCE_MARKERS = ("evidence", "reason", "proof", "trace", "report")
_SIDE_EFFECT_MARKERS = ("br" + "oker", "live_" + "order", "place_" + "order", "send_" + "order", "execute_" + "order")
_CONTRACT_WEAKENING_MARKERS = ("skip", "xfail", "optional", "best effort", "relax", "weaken")


@dataclass(frozen=True)
class HardeningInput:
    changed_files: tuple[str, ...]
    patch_text: str
    tests_changed: tuple[str, ...] = field(default_factory=tuple)
    negative_tests_changed: tuple[str, ...] = field(default_factory=tuple)
    scoped_runtime_change: bool = False
    contract_changed: bool = False


@dataclass(frozen=True)
class HardeningScore:
    score: int
    verdict: str
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    production_grade_claim_allowed: bool


def score_hardening(source: HardeningInput) -> HardeningScore:
    score = 50
    reasons: list[str] = ["base_static_score"]
    blockers: list[str] = []
    patch = source.patch_text
    lowered = patch.lower()

    if _contains_any(lowered, _SILENT_FALLBACK_MARKERS):
        score -= 25
        reasons.append("silent_fallback_detected")
    if _contains_any(patch, _FAIL_CLOSED_MARKERS):
        score += 15
        reasons.append("fail_closed_behavior_detected")
    if _contains_any(patch, _SAFE_DEFAULT_MARKERS):
        score += 10
        reasons.append("safe_default_detected")
    if _contains_any(lowered, _EVIDENCE_MARKERS):
        score += 10
        reasons.append("evidence_rich_output_detected")
    if source.tests_changed:
        score += 10
        reasons.append("tests_changed")
    if source.negative_tests_changed:
        score += 15
        reasons.append("negative_tests_changed")
    else:
        score -= 10
        reasons.append("negative_tests_absent")
    if _contains_any(lowered, _CONTRACT_WEAKENING_MARKERS) or source.contract_changed:
        score -= 20
        reasons.append("contract_weakening_risk")
    if _contains_any(lowered, _SIDE_EFFECT_MARKERS) and not source.scoped_runtime_change:
        score -= 50
        blockers.append("unscoped_runtime_side_effect")
        reasons.append("runtime_side_effect_marker_detected")
    if not source.changed_files:
        score -= 10
        blockers.append("changed_files_absent")
    if not _has_non_production_scope(source.changed_files) and _contains_any(lowered, _SIDE_EFFECT_MARKERS):
        blockers.append("production_path_side_effect_risk")

    score = max(0, min(100, score))
    if blockers:
        verdict = BLOCK
    elif score < PRODUCTION_GRADE_THRESHOLD:
        verdict = WARN
    else:
        verdict = PASS

    return HardeningScore(
        score=score,
        verdict=verdict,
        reasons=tuple(_ordered_unique(reasons)),
        blockers=tuple(_ordered_unique(blockers)),
        production_grade_claim_allowed=verdict == PASS and score >= PRODUCTION_GRADE_THRESHOLD,
    )


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    haystack = text.lower()
    return any(marker.lower() in haystack for marker in markers)


def _has_non_production_scope(paths: tuple[str, ...]) -> bool:
    if not paths:
        return False
    return all(_is_test_path(path) or path.startswith("tools/code_excellence/") or path.startswith("docs/") for path in paths)


def _is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.startswith("tests/") or PurePosixPath(normalized).name.startswith("test_")


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
