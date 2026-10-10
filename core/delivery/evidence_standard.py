"""Evidence-standard validation layered on the canonical delivery work item.

This module validates references and role separation only. It cannot authenticate
people, determine whether a cited source is authoritative, or prove that an
external artifact is scientifically convincing.
"""
from __future__ import annotations

import re
from typing import Any

from .models import EvidenceStatus, EvidenceType, WorkItem
from .roles import DeliveryRole


STANDARD_KEY = "evidence_standard"
GATES = {
    "G1_SOURCE": (EvidenceType.SOURCE_VERIFICATION_EVIDENCE,
                  {DeliveryRole.BUSINESS_ANALYST, DeliveryRole.SOLUTION_ARCHITECT,
                   DeliveryRole.SYSTEM_ARCHITECT, DeliveryRole.QUANT_RESEARCH_ARCHITECT,
                   DeliveryRole.PRODUCT_OWNER}),
    "G2_CORRECTNESS": (EvidenceType.CORRECTNESS_VERIFICATION_EVIDENCE,
                       {DeliveryRole.QA_ENGINEER, DeliveryRole.SENIOR_QA}),
    "G3_ADVERSARIAL": (EvidenceType.ADVERSARIAL_VERIFICATION_EVIDENCE,
                       {DeliveryRole.QA_ENGINEER, DeliveryRole.SENIOR_QA}),
    "G4_INDEPENDENT": (EvidenceType.INDEPENDENT_EVIDENCE,
                       {DeliveryRole.QUANT_RESEARCH_ARCHITECT, DeliveryRole.UAT_REVIEWER,
                        DeliveryRole.RELEASE_MANAGER, DeliveryRole.PRODUCTION_SRE}),
}
CLAIM_STATUSES = {"VERIFIED", "UNVERIFIED", "CONTRADICTED", "NOT_APPLICABLE"}
CLAIM_KINDS = {
    "requirement", "mathematical", "implementation", "data_contract",
    "operational_reliability", "predictive_validity", "profitability",
    "security", "performance", "other",
}
ASSUMPTION_TYPES = {"PUBLISHED_FACT", "THEORETICAL_ASSUMPTION", "EMPIRICAL_HYPOTHESIS"}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_SHA_RE = re.compile(r"(?:^|\b)sha256:[0-9a-f]{64}(?:\b|$)")


def validate_evidence_standard_record(item: WorkItem, *, contract_hash: str | None = None) -> None:
    """Fail closed when an opted-in work item contains an invalid claim record."""
    standard = item.extensions.get(STANDARD_KEY)
    if standard is None:
        return  # Legacy work items remain readable during report-only migration.
    if not isinstance(standard, dict) or standard.get("schema_version") != 1:
        raise ValueError("evidence_standard must be an object with schema_version=1")
    applicability = standard.get("applicability")
    if applicability not in {"REQUIRED", "NOT_APPLICABLE"}:
        raise ValueError("evidence_standard applicability must be REQUIRED or NOT_APPLICABLE")
    if standard.get("enforcement_mode") != "REPORT_ONLY":
        raise ValueError("evidence_standard enforcement_mode must remain REPORT_ONLY in v1")
    claims = standard.get("claims")
    if not isinstance(claims, list):
        raise ValueError("evidence_standard claims must be a list")
    if applicability == "NOT_APPLICABLE":
        reason = standard.get("applicability_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("NOT_APPLICABLE requires an explicit applicability_reason")
        refs = standard.get("evidence_refs")
        known_ids = {e.evidence_id for e in item.evidence}
        if not isinstance(refs, list) or not refs or any(
            not isinstance(ref, str) or not ref.strip() or ref not in known_ids for ref in refs
        ):
            raise ValueError("NOT_APPLICABLE requires evidence_refs to known work-item evidence")
        if claims:
            raise ValueError("NOT_APPLICABLE work item cannot contain material claims")
        return
    if not claims:
        raise ValueError("REQUIRED evidence_standard must list at least one material claim")
    assessed_paths = standard.get("assessed_paths")
    if not isinstance(assessed_paths, list) or not assessed_paths or any(
        not isinstance(path, str) or not path.strip() or path.startswith("/") or ".." in path.split("/")
        for path in assessed_paths
    ):
        raise ValueError("REQUIRED evidence_standard needs safe, non-empty assessed_paths")

    evidence_by_id = {e.evidence_id: e for e in item.evidence}
    if contract_hash is not None:
        for evidence in item.evidence:
            if evidence.evidence_type in {spec[0] for spec in GATES.values()} and evidence.work_item_hash != contract_hash:
                raise ValueError("evidence standard gate evidence is bound to an older work-item contract hash")
    developer_authors = {
        e.author for e in item.evidence if e.evidence_type == EvidenceType.DEV_TEST_EVIDENCE
    }
    seen_claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("evidence_standard claim must be an object")
        claim_id, statement = claim.get("claim_id"), claim.get("statement")
        if not isinstance(claim_id, str) or not claim_id.strip() or claim_id in seen_claim_ids:
            raise ValueError("claim_id must be non-empty and unique within a work item")
        seen_claim_ids.add(claim_id)
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError(f"claim {claim_id} requires a statement")
        if claim.get("claim_kind") not in CLAIM_KINDS:
            raise ValueError(f"claim {claim_id} has an unsupported claim_kind")
        status = claim.get("status")
        if status not in CLAIM_STATUSES:
            raise ValueError(f"claim {claim_id} has an unsupported status")
        source_ids = claim.get("source_ids")
        assumptions = claim.get("assumptions")
        if not isinstance(source_ids, list) or any(not isinstance(x, str) or not x.strip() for x in source_ids):
            raise ValueError(f"claim {claim_id} source_ids must be a list of non-empty IDs")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError(f"claim {claim_id} has duplicate source_ids")
        if not isinstance(assumptions, list):
            raise ValueError(f"claim {claim_id} assumptions must be a list")
        assumption_ids: set[str] = set()
        for assumption in assumptions:
            if not isinstance(assumption, dict):
                raise ValueError(f"claim {claim_id} assumptions must identify type and source")
            assumption_id = assumption.get("assumption_id")
            if not isinstance(assumption_id, str) or not assumption_id.strip() or assumption_id in assumption_ids:
                raise ValueError(f"claim {claim_id} assumption_id must be non-empty and unique")
            assumption_ids.add(assumption_id)
            if not isinstance(assumption.get("statement"), str) or not assumption["statement"].strip():
                raise ValueError(f"claim {claim_id} assumption requires a statement")
            classification = assumption.get("classification")
            if classification not in ASSUMPTION_TYPES:
                raise ValueError(f"claim {claim_id} assumption needs PUBLISHED_FACT, THEORETICAL_ASSUMPTION, or EMPIRICAL_HYPOTHESIS")
            assumption_sources = assumption.get("source_ids")
            if not isinstance(assumption_sources, list) or any(
                not isinstance(source_id, str) or not source_id.strip() for source_id in assumption_sources
            ):
                raise ValueError(f"claim {claim_id} assumption source_ids must be explicit strings")
            if classification == "PUBLISHED_FACT" and not assumption_sources:
                raise ValueError(f"claim {claim_id} published facts require at least one source")
        gates = claim.get("gate_evidence")
        if not isinstance(gates, dict) or set(gates) - set(GATES):
            raise ValueError(f"claim {claim_id} gate_evidence has unknown gate keys")
        if status == "NOT_APPLICABLE":
            reason = claim.get("limitation")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"claim {claim_id} NOT_APPLICABLE requires a limitation")
            supporting_refs = claim.get("evidence_refs")
            if not isinstance(supporting_refs, list) or not supporting_refs or any(
                not isinstance(ref, str) or not ref.strip() for ref in supporting_refs
            ):
                raise ValueError(f"claim {claim_id} NOT_APPLICABLE requires supporting evidence_refs")
            if not any(ref in evidence_by_id or ref in source_ids for ref in supporting_refs):
                raise ValueError(f"claim {claim_id} NOT_APPLICABLE evidence_refs must identify known evidence or source")
            if gates:
                raise ValueError(f"claim {claim_id} NOT_APPLICABLE cannot claim passing gates")
            continue
        if status in {"UNVERIFIED", "CONTRADICTED"}:
            reason = claim.get("limitation")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"claim {claim_id} {status} requires a limitation or contradiction summary")

        linked = {}
        for gate_name, evidence_id in gates.items():
            if gate_name not in GATES:
                continue
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                raise ValueError(f"claim {claim_id} gate {gate_name} requires an evidence_id")
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                raise ValueError(f"claim {claim_id} gate {gate_name} references missing evidence {evidence_id}")
            expected_type, allowed_roles = GATES[gate_name]
            if evidence.evidence_type != expected_type or evidence.role not in allowed_roles:
                raise ValueError(f"claim {claim_id} gate {gate_name} references wrong evidence type or role")
            if evidence.status == EvidenceStatus.NOT_APPLICABLE:
                raise ValueError(f"claim {claim_id} gate {gate_name} cannot be N/A when claim is material")
            linked[gate_name] = evidence

        if status == "VERIFIED":
            if set(linked) != set(GATES):
                raise ValueError(f"claim {claim_id} VERIFIED requires evidence for all four gates")
            if not source_ids:
                raise ValueError(f"claim {claim_id} VERIFIED requires at least one registered source")
            if any(e.status != EvidenceStatus.PASS for e in linked.values()):
                raise ValueError(f"claim {claim_id} VERIFIED conflicts with failed or blocked gate evidence")
            if any(source_id not in linked["G1_SOURCE"].references for source_id in source_ids):
                raise ValueError(f"claim {claim_id} G1 evidence must reference every registered source ID")
            for gate_name in ("G2_CORRECTNESS", "G3_ADVERSARIAL", "G4_INDEPENDENT"):
                if not any(_ARTIFACT_SHA_RE.search(ref) for ref in linked[gate_name].references):
                    raise ValueError(f"claim {claim_id} {gate_name} must reference a SHA-256-bound artifact")
            if claim.get("claim_kind") in {"predictive_validity", "profitability"}:
                certification_ref = claim.get("research_certification_ref")
                if not isinstance(certification_ref, str) or not certification_ref.strip():
                    raise ValueError(f"claim {claim_id} requires separate research certification evidence")
        if status == "CONTRADICTED" and not any(
            evidence.status == EvidenceStatus.FAIL for evidence in linked.values()
        ):
            raise ValueError(f"claim {claim_id} CONTRADICTED requires a failing referenced gate result")

        for gate_name in ("G2_CORRECTNESS", "G3_ADVERSARIAL", "G4_INDEPENDENT"):
            evidence = linked.get(gate_name)
            if evidence is not None and evidence.author in developer_authors:
                raise ValueError(f"claim {claim_id} {gate_name} reviewer cannot be a developer author")
        qa_authors = [linked[name].author for name in ("G2_CORRECTNESS", "G3_ADVERSARIAL", "G4_INDEPENDENT")
                      if name in linked]
        if len(qa_authors) != len(set(qa_authors)):
            raise ValueError(f"claim {claim_id} correctness, adversarial, and independent reviewers must be distinct")


def validate_source_registry(registry: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise ValueError("source registry must be an object with schema_version=1")
    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ValueError("source registry sources must be a list")
    result: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("source registry entries must be objects")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip() or source_id in result:
            raise ValueError("source_id must be non-empty and unique")
        if source.get("status") not in {"VERIFIED", "UNVERIFIED"}:
            raise ValueError(f"source {source_id} has invalid status")
        if not isinstance(source.get("locator"), str) or not source["locator"].strip():
            raise ValueError(f"source {source_id} requires a locator")
        for field in ("source_type", "authority", "limitations"):
            if not isinstance(source.get(field), str) or not source[field].strip():
                raise ValueError(f"source {source_id} requires {field}")
        result[source_id] = source
    return result


def validate_claim_registry(registry: Any, sources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise ValueError("claim registry must be an object with schema_version=1")
    claims = registry.get("claims")
    if not isinstance(claims, list):
        raise ValueError("claim registry claims must be a list")
    result: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("claim registry entries must be objects")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip() or claim_id in result:
            raise ValueError("claim_id must be non-empty and unique in claim registry")
        if claim.get("status") not in CLAIM_STATUSES:
            raise ValueError(f"claim {claim_id} has invalid status")
        if claim.get("claim_kind") not in CLAIM_KINDS:
            raise ValueError(f"claim {claim_id} has invalid claim_kind")
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            raise ValueError(f"claim {claim_id} requires a statement")
        scope_paths = claim.get("scope_paths")
        if not isinstance(scope_paths, list) or not scope_paths or any(
            not isinstance(path, str) or not path.strip() or path.startswith("/") or ".." in path.split("/")
            for path in scope_paths
        ):
            raise ValueError(f"claim {claim_id} requires safe, non-empty scope_paths")
        ids = claim.get("source_ids")
        if not isinstance(ids, list) or any(source_id not in sources for source_id in ids):
            raise ValueError(f"claim {claim_id} references an unknown source")
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or any(not isinstance(ref, str) or not ref.strip() for ref in refs):
            raise ValueError(f"claim {claim_id} evidence_refs must be a list of auditable references")
        if claim.get("status") in {"VERIFIED", "CONTRADICTED", "NOT_APPLICABLE"} and not refs:
            raise ValueError(f"claim {claim_id} {claim['status']} requires evidence_refs")
        if claim.get("status") != "VERIFIED" and not isinstance(claim.get("limitation"), str):
            raise ValueError(f"claim {claim_id} non-verified status requires a limitation")
        if claim.get("status") != "VERIFIED" and not claim["limitation"].strip():
            raise ValueError(f"claim {claim_id} non-verified status requires a limitation")
        result[claim_id] = claim
    return result


def validate_subject_commit(standard: dict[str, Any], candidate_sha: str) -> None:
    """Reject stale records and any VERIFIED claim not bound to the exact head."""
    if not _SHA_RE.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be 40 lowercase hex characters")
    record_sha = standard.get("subject_commit_sha")
    if record_sha is not None and record_sha != candidate_sha:
        raise ValueError("work-item subject SHA does not match the candidate commit")
    claims = standard.get("claims", [])
    # The CI report binds the sealed work-item/evidence hashes to candidate_sha.
    # Requiring a record to embed its own containing commit would be self-referential.


def summarize_evidence_standard(item: WorkItem) -> dict[str, Any]:
    """Expose claim-gate status to delivery readiness without making it blocking."""
    standard = item.extensions.get(STANDARD_KEY)
    summary = {
        "mode": "REPORT_ONLY",
        "blocking": False,
        "status": "UNVERIFIED",
        "reason": "no claim-level evidence-standard record is attached",
        "claims": [],
    }
    if not isinstance(standard, dict):
        return summary
    if standard.get("applicability") == "NOT_APPLICABLE":
        summary["status"] = "NOT_APPLICABLE"
        summary["reason"] = standard.get("applicability_reason", "")
        return summary
    summary["reason"] = "claim-level evidence gates are informational during v1 migration"
    by_id = {e.evidence_id: e for e in item.evidence}
    for claim in standard.get("claims", []):
        gate_statuses = {name: "BLOCKED" for name in GATES}
        for name, evidence_id in claim.get("gate_evidence", {}).items():
            evidence = by_id.get(evidence_id)
            if evidence is not None:
                gate_statuses[name] = evidence.status.value
        summary["claims"].append({
            "claim_id": claim.get("claim_id"),
            "declared_status": claim.get("status", "UNVERIFIED"),
            "assessment_status": ("UNVERIFIED" if claim.get("status") == "VERIFIED"
                                  else claim.get("status", "UNVERIFIED")),
            "verification_level": "STRUCTURAL_ONLY",
            "gate_statuses": gate_statuses,
            "limitation": claim.get("limitation", ""),
        })
    return summary
