from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from .bundle import AuditBundle, AuditBundleError
from .catalog import CONTROL_CATALOG
from .context import deep_merge, dotted_get
from .contracts import (
    AuditReport,
    AuditVerdict,
    ControlDefinition,
    ControlResult,
    ControlStatus,
    EvidenceRef,
)
from .security import contains_secret, redact_secrets


class AgenticQAAuditor:
    SCHEMA_VERSION = "agentic-qa-audit/v1"

    def __init__(self, *, policy_version: str = "agentic-qa-policy/v1") -> None:
        self.policy_version = policy_version

    def audit_bundle(self, root: str | Path) -> AuditReport:
        try:
            bundle = AuditBundle.load(root)
            context = self._build_context(bundle)
            results = tuple(self._evaluate(control, context, bundle) for control in CONTROL_CATALOG)
            return self._build_report(bundle, context, results)
        except AuditBundleError as exc:
            result = ControlResult(
                control_id="AQ-11",
                domain="evidence_integrity",
                title="Manifest present",
                status=ControlStatus.ERROR,
                score=0,
                reason_code="BUNDLE_LOAD_ERROR",
                summary=str(exc),
                severity=CONTROL_CATALOG[10].severity,
                hard_fail=True,
            )
            return AuditReport(
                schema_version=self.SCHEMA_VERSION,
                run_id="UNKNOWN",
                trace_id=str(uuid.uuid4()),
                policy_version=self.policy_version,
                repository_commit="UNKNOWN",
                bundle_digest="UNAVAILABLE",
                verdict=AuditVerdict.AUDITOR_ERROR,
                controls=(result,),
                deterministic_score=0.0,
                passed=0,
                failed=0,
                insufficient=0,
                errors=1,
                hard_failures=("AQ-11:BUNDLE_LOAD_ERROR",),
            )

    def _build_context(self, bundle: AuditBundle) -> dict[str, Any]:
        manifest = bundle.manifest
        context: dict[str, Any] = {}
        deep_merge(context, manifest)
        artifacts = bundle.read_json_artifacts()
        for logical_name, payload in artifacts.items():
            if isinstance(payload, dict):
                deep_merge(context, payload)
                context.setdefault("_artifacts", {})[logical_name] = payload

        observed = bundle.observed_artifacts()
        artifacts_declared = bool(bundle.artifacts)
        safe = artifacts_declared and all(bool(item["safe"]) for item in observed.values())
        exist = artifacts_declared and all(bool(item["exists"]) for item in observed.values())
        hashes_declared = artifacts_declared and all(bool(item["expected_sha256"]) for item in observed.values())
        hashes_match = hashes_declared and all(
            item["expected_sha256"] == item["observed_sha256"] for item in observed.values()
        )
        run_id = str(context.get("run_id") or manifest.get("bundle_id") or "")
        trace_id = str(context.get("trace_id") or manifest.get("trace_id") or "")
        repository_commit = str(context.get("repository_commit") or manifest.get("repository_commit") or "")
        policy_version = str(context.get("policy_version") or self.policy_version)
        manifest_schema_valid = bool(run_id and repository_commit and isinstance(manifest.get("artifacts"), dict))

        derived = {
            "manifest_present": True,
            "manifest_schema_valid": manifest_schema_valid,
            "artifact_paths_safe": safe,
            "artifacts_exist": exist,
            "artifact_hashes_match": hashes_match,
            "bundle_digest_reproducible": True,
            "identity_complete": bool(run_id and trace_id),
        }
        context["_derived"] = {**context.get("_derived", {}), **derived}
        context["_observed_artifacts"] = observed
        context["run_id"] = run_id
        context["trace_id"] = trace_id
        context["repository_commit"] = repository_commit
        context["policy_version"] = policy_version
        context["bundle_digest"] = bundle.digest()

        redacted = redact_secrets(context)
        context.setdefault("security", {})["secret_redaction_passed"] = not contains_secret(redacted)
        return context

    def _evaluate(self, control: ControlDefinition, context: dict[str, Any], bundle: AuditBundle) -> ControlResult:
        present, actual = dotted_get(context, control.key)
        refs = self._refs_for(control, bundle)
        if not present:
            return ControlResult(
                control_id=control.control_id,
                domain=control.domain,
                title=control.title,
                status=ControlStatus.INSUFFICIENT,
                score=3,
                reason_code="EVIDENCE_MISSING",
                summary=f"Required evidence key is missing: {control.key}",
                severity=control.severity,
                hard_fail=control.hard_fail,
                evidence_refs=refs,
                details={"key": control.key, "expected": control.expected},
            )
        try:
            passed = self._apply_rule(control.rule, actual, control.expected)
        except (TypeError, ValueError) as exc:
            return ControlResult(
                control_id=control.control_id,
                domain=control.domain,
                title=control.title,
                status=ControlStatus.ERROR,
                score=0,
                reason_code="RULE_EVALUATION_ERROR",
                summary=str(exc),
                severity=control.severity,
                hard_fail=control.hard_fail,
                evidence_refs=refs,
                details={"key": control.key, "actual": actual, "expected": control.expected},
            )
        return ControlResult(
            control_id=control.control_id,
            domain=control.domain,
            title=control.title,
            status=ControlStatus.PASS if passed else ControlStatus.FAIL,
            score=10 if passed else 0,
            reason_code="CONTROL_PASS" if passed else "CONTROL_FAIL",
            summary=control.description if passed else f"Control failed for {control.key}",
            severity=control.severity,
            hard_fail=control.hard_fail,
            evidence_refs=refs,
            details={"key": control.key, "actual": actual, "expected": control.expected},
        )

    @staticmethod
    def _apply_rule(rule: str, actual: Any, expected: Any) -> bool:
        if rule == "is_true":
            return actual is True
        if rule == "equals":
            return actual == expected
        if rule == "nonempty":
            return actual is not None and str(actual).strip() != ""
        if rule == "zero":
            return float(actual) == 0.0
        if rule == "min":
            return float(actual) >= float(expected)
        raise ValueError(f"unsupported rule: {rule}")

    @staticmethod
    def _refs_for(control: ControlDefinition, bundle: AuditBundle) -> tuple[EvidenceRef, ...]:
        refs = [EvidenceRef(bundle.manifest_name, f"/{control.key.replace('.', '/')}")]
        for logical_name, metadata in sorted(bundle.artifacts.items()):
            if logical_name in control.key or control.key.split(".", 1)[0] in logical_name:
                refs.append(EvidenceRef(metadata.get("path", logical_name), "", metadata.get("sha256") or None))
        return tuple(refs[:4])

    def _build_report(
        self,
        bundle: AuditBundle,
        context: dict[str, Any],
        results: tuple[ControlResult, ...],
    ) -> AuditReport:
        counts = Counter(item.status for item in results)
        hard_failures = tuple(
            f"{item.control_id}:{item.reason_code}"
            for item in results
            if item.hard_fail and item.status in {ControlStatus.FAIL, ControlStatus.ERROR}
        )
        mandatory_insufficient = [
            item for item in results if item.hard_fail and item.status is ControlStatus.INSUFFICIENT
        ]
        if counts[ControlStatus.ERROR]:
            verdict = AuditVerdict.AUDITOR_ERROR
        elif hard_failures:
            verdict = AuditVerdict.REJECTED
        elif mandatory_insufficient:
            verdict = AuditVerdict.INSUFFICIENT_EVIDENCE
        elif counts[ControlStatus.FAIL] or counts[ControlStatus.INSUFFICIENT]:
            verdict = AuditVerdict.CONDITIONALLY_CERTIFIED
        else:
            verdict = AuditVerdict.CONTROL_PLANE_CERTIFIED
        score = round(sum(item.score for item in results) / max(1, len(results)), 2)
        warnings = tuple(
            f"{item.control_id}:{item.reason_code}"
            for item in results
            if not item.hard_fail and item.status is not ControlStatus.PASS
        )
        return AuditReport(
            schema_version=self.SCHEMA_VERSION,
            run_id=str(context.get("run_id") or "UNKNOWN"),
            trace_id=str(context.get("trace_id") or uuid.uuid4()),
            policy_version=str(context.get("policy_version") or self.policy_version),
            repository_commit=str(context.get("repository_commit") or "UNKNOWN"),
            bundle_digest=bundle.digest(),
            verdict=verdict,
            controls=results,
            deterministic_score=score,
            passed=counts[ControlStatus.PASS],
            failed=counts[ControlStatus.FAIL],
            insufficient=counts[ControlStatus.INSUFFICIENT],
            errors=counts[ControlStatus.ERROR],
            hard_failures=hard_failures,
            warnings=warnings,
        )


def write_report(report: AuditReport, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return output
