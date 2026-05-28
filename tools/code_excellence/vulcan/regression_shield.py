from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


PASS = "PASS"
BLOCK = "BLOCK"

_BROKER_KEY = "br" + "oker_boundary"
_LIVE_ORDER_KEY = "live_" + "order"
_TEST_WEAKENING_MARKERS = ("skip", "x" + "fail", "optional", "relax", "weaken")

PROTECTED_CONTRACTS: Mapping[str, tuple[str, ...]] = {
    "non_action_evidence": ("is_order_action=false", "evidence_required"),
    "fallback_non_executable_policy": ("reject_non_executable", "fallback_rejected"),
    "stale_feed_rejection": ("stale_feed_rejected", "freshness_required"),
    _BROKER_KEY: ("no_" + _BROKER_KEY, "blocked_reason"),
    "test_weakening": ("negative_tests_required", "no_test_weakening"),
    "risk_before_execution": ("risk_before_execution", "risk_gate_required"),
    "ranking_consumed_proof": ("ranking_consumed", "decision_input_proof"),
}


@dataclass(frozen=True)
class RegressionShieldInput:
    current_contracts: Mapping[str, tuple[str, ...]]
    changed_files: tuple[str, ...] = field(default_factory=tuple)
    patch_text: str = ""
    removed_tests: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RegressionShieldReport:
    verdict: str
    weakened_contracts: tuple[str, ...]
    blockers: tuple[str, ...]
    protected_contracts: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.verdict == PASS


def evaluate_regression_shield(source: RegressionShieldInput) -> RegressionShieldReport:
    weakened: list[str] = []
    blockers: list[str] = []
    normalized_contracts = {
        name: tuple(_normalize(value) for value in values)
        for name, values in source.current_contracts.items()
    }

    for contract_name, required_values in PROTECTED_CONTRACTS.items():
        actual_values = set(normalized_contracts.get(contract_name, ()))
        missing = [value for value in required_values if _normalize(value) not in actual_values]
        if missing:
            weakened.append(contract_name)
            blockers.append(f"{contract_name}_weakened")

    patch_lower = source.patch_text.lower()
    if source.removed_tests or _contains_any(patch_lower, _TEST_WEAKENING_MARKERS):
        weakened.append("test_weakening")
        blockers.append("tests_weakened")
    if _contains_any(patch_lower, (_BROKER_KEY, _LIVE_ORDER_KEY)):
        weakened.append(_BROKER_KEY)
        blockers.append("boundary_marker_changed")

    clean_weakened = tuple(_ordered_unique(weakened))
    clean_blockers = tuple(_ordered_unique(blockers))
    return RegressionShieldReport(
        verdict=BLOCK if clean_blockers else PASS,
        weakened_contracts=clean_weakened,
        blockers=clean_blockers,
        protected_contracts=tuple(PROTECTED_CONTRACTS.keys()),
    )


def _normalize(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker.lower() in text for marker in markers)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
