"""Read-only strategy quality audit for EDGE-66.

This module audits StrategySpec metadata quality. It does not import strategy
modules, execute strategy callables, select strategies, generate candidates,
rank candidates, wire runtime behavior, call brokers, or create order intent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.strategy_spec import (
    STRATEGY_SPEC_UNSAFE_EVIDENCE,
    STRATEGY_SPEC_UNSAFE_REGIME,
    StrategySpec,
    StrategySpecIssue,
    StrategySpecRegistry,
    build_strategy_spec_registry,
)

STRATEGY_QUALITY_AUDIT_SCHEMA_VERSION = 1
STRATEGY_QUALITY_AUDIT_SOURCE = "strategy_quality_audit_v1"

QUALITY_STATUS_PASS = "PASS"
QUALITY_STATUS_WARN = "WARN"
QUALITY_STATUS_BLOCK = "BLOCK"

STRATEGY_QUALITY_REGISTRY_BLOCKED = "strategy_quality_registry_blocked"
STRATEGY_QUALITY_LOW_CONFIDENCE = "strategy_quality_low_confidence"
STRATEGY_QUALITY_NARROW_REGIME_COVERAGE = "strategy_quality_narrow_regime_coverage"
STRATEGY_QUALITY_SINGLE_DIRECTION = "strategy_quality_single_direction"
STRATEGY_QUALITY_MISSING_DESCRIPTION = "strategy_quality_missing_description"
STRATEGY_QUALITY_MISSING_EVIDENCE = "strategy_quality_missing_evidence"
STRATEGY_QUALITY_UNSAFE_REGIME_NOT_BLOCKED = "strategy_quality_unsafe_regime_not_blocked"
STRATEGY_QUALITY_EMPTY_REGISTRY = "strategy_quality_empty_registry"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class StrategyQualityFinding:
    strategy_id: str | None
    code: str
    severity: str
    message: str
    field: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
        }


@dataclass(frozen=True)
class StrategyQualityRecord:
    strategy_id: str
    family: str
    instruments: tuple[str, ...]
    declared_regimes: tuple[str, ...]
    quality_status: str
    findings: tuple[StrategyQualityFinding, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def blocker_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == QUALITY_STATUS_BLOCK)

    @property
    def warning_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == QUALITY_STATUS_WARN)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "strategy_id": self.strategy_id,
            "family": self.family,
            "instruments": list(self.instruments),
            "declared_regimes": list(self.declared_regimes),
            "quality_status": self.quality_status,
            "finding_count": len(self.findings),
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "findings": [finding.to_payload() for finding in self.findings],
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload


@dataclass(frozen=True)
class StrategyQualityAudit:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    registry_valid: bool
    records: tuple[StrategyQualityRecord, ...]
    findings: tuple[StrategyQualityFinding, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "registry_valid": self.registry_valid,
            "record_count": len(self.records),
            "strategy_ids": [record.strategy_id for record in self.records],
            "records": [record.to_payload() for record in self.records],
            "findings": [finding.to_payload() for finding in self.findings],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_strategy_quality_audit(
    registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None = None,
    *,
    source: str = STRATEGY_QUALITY_AUDIT_SOURCE,
) -> StrategyQualityAudit:
    """Build a read-only quality audit from StrategySpec metadata."""

    resolved_registry = _resolve_registry(registry)
    registry_findings = tuple(_finding_from_registry_issue(issue) for issue in resolved_registry.issues)
    records = tuple(_audit_spec(spec, registry_findings) for spec in resolved_registry.specs)
    findings = (*registry_findings, *tuple(finding for record in records for finding in record.findings))
    blockers = _dedupe_sorted(finding.code for finding in findings if finding.severity == QUALITY_STATUS_BLOCK)
    warnings = _dedupe_sorted(finding.code for finding in findings if finding.severity == QUALITY_STATUS_WARN)
    if not resolved_registry.specs:
        blockers = _dedupe_sorted((*blockers, STRATEGY_QUALITY_EMPTY_REGISTRY))
        findings = (
            *findings,
            StrategyQualityFinding(
                strategy_id=None,
                code=STRATEGY_QUALITY_EMPTY_REGISTRY,
                severity=QUALITY_STATUS_BLOCK,
                message="strategy quality audit requires at least one strategy spec",
            ),
        )
    return StrategyQualityAudit(
        schema_version=STRATEGY_QUALITY_AUDIT_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        registry_valid=resolved_registry.valid,
        records=records,
        findings=findings,
        blockers=blockers,
        warnings=warnings,
        metadata={
            "model": STRATEGY_QUALITY_AUDIT_SOURCE,
            "scope": "read_only_strategy_quality_audit_no_strategy_selection",
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
        },
    )


def _resolve_registry(
    registry: StrategySpecRegistry | Iterable[StrategySpec | Mapping[str, Any]] | None,
) -> StrategySpecRegistry:
    if isinstance(registry, StrategySpecRegistry):
        return registry
    return build_strategy_spec_registry(registry)


def _audit_spec(
    spec: StrategySpec,
    registry_findings: tuple[StrategyQualityFinding, ...],
) -> StrategyQualityRecord:
    findings: list[StrategyQualityFinding] = [
        finding for finding in registry_findings if finding.strategy_id == spec.strategy_id
    ]
    findings.extend(_quality_findings_for_spec(spec))
    blocker_count = sum(1 for finding in findings if finding.severity == QUALITY_STATUS_BLOCK)
    warning_count = sum(1 for finding in findings if finding.severity == QUALITY_STATUS_WARN)
    if blocker_count:
        status = QUALITY_STATUS_BLOCK
    elif warning_count:
        status = QUALITY_STATUS_WARN
    else:
        status = QUALITY_STATUS_PASS
    return StrategyQualityRecord(
        strategy_id=spec.strategy_id,
        family=spec.family,
        instruments=spec.instruments,
        declared_regimes=spec.declared_regimes,
        quality_status=status,
        findings=tuple(findings),
        metadata={
            "module_path": spec.module_path,
            "callable_name": spec.callable_name,
            "min_market_state_confidence": spec.min_market_state_confidence,
            "direction_capabilities": list(spec.direction_capabilities),
            "required_evidence_keys": list(spec.required_evidence_keys),
        },
    )


def _quality_findings_for_spec(spec: StrategySpec) -> tuple[StrategyQualityFinding, ...]:
    findings: list[StrategyQualityFinding] = []
    if spec.min_market_state_confidence < 0.50:
        findings.append(
            StrategyQualityFinding(
                strategy_id=spec.strategy_id,
                code=STRATEGY_QUALITY_LOW_CONFIDENCE,
                severity=QUALITY_STATUS_WARN,
                message="strategy declares low market-state confidence requirement",
                field="min_market_state_confidence",
            )
        )
    if sum(1 for _ in spec.declared_regimes) < 2:
        findings.append(
            StrategyQualityFinding(
                strategy_id=spec.strategy_id,
                code=STRATEGY_QUALITY_NARROW_REGIME_COVERAGE,
                severity=QUALITY_STATUS_WARN,
                message="strategy declares narrow regime coverage and needs future hypothesis proof",
                field="declared_regimes",
            )
        )
    if sum(1 for _ in spec.direction_capabilities) < 2:
        findings.append(
            StrategyQualityFinding(
                strategy_id=spec.strategy_id,
                code=STRATEGY_QUALITY_SINGLE_DIRECTION,
                severity=QUALITY_STATUS_WARN,
                message="strategy declares single-direction capability and needs directional-bias review",
                field="direction_capabilities",
            )
        )
    if not spec.description.strip():
        findings.append(
            StrategyQualityFinding(
                strategy_id=spec.strategy_id,
                code=STRATEGY_QUALITY_MISSING_DESCRIPTION,
                severity=QUALITY_STATUS_WARN,
                message="strategy spec has no human-readable quality description",
                field="description",
            )
        )
    return tuple(findings)


def _finding_from_registry_issue(issue: StrategySpecIssue) -> StrategyQualityFinding:
    severity = QUALITY_STATUS_BLOCK if issue.severity == "BLOCKER" else QUALITY_STATUS_WARN
    code = STRATEGY_QUALITY_REGISTRY_BLOCKED
    if issue.code == STRATEGY_SPEC_UNSAFE_EVIDENCE:
        code = STRATEGY_QUALITY_MISSING_EVIDENCE
    elif issue.code == STRATEGY_SPEC_UNSAFE_REGIME:
        code = STRATEGY_QUALITY_UNSAFE_REGIME_NOT_BLOCKED
    return StrategyQualityFinding(
        strategy_id=issue.strategy_id,
        code=code,
        severity=severity,
        message=issue.message,
        field=issue.field,
    )


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


__all__ = [
    "QUALITY_STATUS_BLOCK",
    "QUALITY_STATUS_PASS",
    "QUALITY_STATUS_WARN",
    "STRATEGY_QUALITY_AUDIT_SCHEMA_VERSION",
    "STRATEGY_QUALITY_AUDIT_SOURCE",
    "STRATEGY_QUALITY_EMPTY_REGISTRY",
    "STRATEGY_QUALITY_LOW_CONFIDENCE",
    "STRATEGY_QUALITY_MISSING_DESCRIPTION",
    "STRATEGY_QUALITY_MISSING_EVIDENCE",
    "STRATEGY_QUALITY_NARROW_REGIME_COVERAGE",
    "STRATEGY_QUALITY_REGISTRY_BLOCKED",
    "STRATEGY_QUALITY_SINGLE_DIRECTION",
    "STRATEGY_QUALITY_UNSAFE_REGIME_NOT_BLOCKED",
    "StrategyQualityAudit",
    "StrategyQualityFinding",
    "StrategyQualityRecord",
    "build_strategy_quality_audit",
]
