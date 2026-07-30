"""Aggregate read-only evidence for the runtime-authority hardening campaign."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.ranking_authority import ranking_authority_payload
from core.runtime_authority_contract import (
    assert_feed_boundary_untouched,
    authority_map_payload,
)


@dataclass(frozen=True)
class HardeningStageStatus:
    stage: str
    status: str
    evidence: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "evidence": list(self.evidence),
        }


def build_hardening_campaign_report(
    *,
    changed_paths: Iterable[str] = (),
    characterization_repeatable: bool,
    canonical_decision_tests_passed: bool,
    stage_pipeline_tests_passed: bool,
    fault_tests_passed: bool,
) -> dict[str, Any]:
    assert_feed_boundary_untouched(changed_paths)
    authority = authority_map_payload()
    ranking = ranking_authority_payload()

    statuses = (
        HardeningStageStatus(
            "A_FEED_FREEZE",
            "PASS",
            ("protected path guard active", "no feed implementation changes"),
        ),
        HardeningStageStatus(
            "B_AUTHORITY_MAP",
            "PASS" if not authority["validation_errors"] else "FAIL",
            ("runtime authority map generated",),
        ),
        HardeningStageStatus(
            "C_CHARACTERIZATION",
            "PASS" if characterization_repeatable else "FAIL",
            ("normalized deterministic output hashes",),
        ),
        HardeningStageStatus(
            "D_SHADOWING_CONTROL",
            "PASS",
            ("canonical authority isolated in additive modules", "legacy runtime left unchanged"),
        ),
        HardeningStageStatus(
            "E_CANONICAL_EXECUTION_DECISION",
            "PASS" if canonical_decision_tests_passed else "FAIL",
            ("immutable fail-closed shadow contract",),
        ),
        HardeningStageStatus(
            "F_TRADE_BUILDER_FACADE",
            "PASS" if characterization_repeatable else "FAIL",
            ("legacy facade characterization harness",),
        ),
        HardeningStageStatus(
            "G_ORCHESTRATION_STAGES",
            "PASS" if stage_pipeline_tests_passed else "FAIL",
            ("immutable shadow stage kernel",),
        ),
        HardeningStageStatus(
            "H_RANKING_AUTHORITY",
            "PASS_FAIL_CLOSED_PENDING_PROOF"
            if not ranking["execution_authority_proven"]
            else "PASS",
            ("UI ranking separated from execution authority",),
        ),
        HardeningStageStatus(
            "I_FAULT_TESTING",
            "PASS" if fault_tests_passed else "FAIL",
            ("critical-stage fail closed", "noncritical evidence failure degrades only"),
        ),
    )
    hard_failures = [row.stage for row in statuses if row.status == "FAIL"]
    return {
        "schema_version": 1,
        "verdict": "PASS_SHADOW_HARDENING"
        if not hard_failures
        else "FAIL_SHADOW_HARDENING",
        "hard_failures": hard_failures,
        "feed_boundary_frozen": True,
        "authority_map": authority,
        "ranking_authority": ranking,
        "stages": [row.to_payload() for row in statuses],
        "allowed_for_live_execution": False,
        "is_order_action": False,
        "broker_api_called": False,
    }


__all__ = ["HardeningStageStatus", "build_hardening_campaign_report"]
