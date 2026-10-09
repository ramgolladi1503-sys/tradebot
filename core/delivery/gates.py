from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .models import Evidence, EvidenceStatus, EvidenceType


class GateName(str, Enum):
    EVIDENCE_G1_SOURCE = "EVIDENCE_G1_SOURCE"
    EVIDENCE_G2_CORRECTNESS = "EVIDENCE_G2_CORRECTNESS"
    EVIDENCE_G3_ADVERSARIAL = "EVIDENCE_G3_ADVERSARIAL"
    EVIDENCE_G4_INDEPENDENT = "EVIDENCE_G4_INDEPENDENT"
    G0_REQUIREMENT = "G0_REQUIREMENT"
    G1_ARCHITECTURE = "G1_ARCHITECTURE"
    G2_DEVELOPMENT = "G2_DEVELOPMENT"
    G3_QA = "G3_QA"
    G4_UAT = "G4_UAT"
    G5_PRODUCT = "G5_PRODUCT"
    G6_CI = "G6_CI"
    G7_RELEASE = "G7_RELEASE"
    G8_MERGE = "G8_MERGE"
    G9_PRODUCTION_VERIFY = "G9_PRODUCTION_VERIFY"


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: GateStatus
    reason: str
    evidence_ids: tuple[str, ...] = ()


GATE_EVIDENCE = {
    GateName.EVIDENCE_G1_SOURCE: EvidenceType.SOURCE_VERIFICATION_EVIDENCE,
    GateName.EVIDENCE_G2_CORRECTNESS: EvidenceType.CORRECTNESS_VERIFICATION_EVIDENCE,
    GateName.EVIDENCE_G3_ADVERSARIAL: EvidenceType.ADVERSARIAL_VERIFICATION_EVIDENCE,
    GateName.EVIDENCE_G4_INDEPENDENT: EvidenceType.INDEPENDENT_EVIDENCE,
    GateName.G0_REQUIREMENT: EvidenceType.REQUIREMENT_EVIDENCE,
    GateName.G1_ARCHITECTURE: EvidenceType.ARCHITECTURE_EVIDENCE,
    GateName.G2_DEVELOPMENT: EvidenceType.DEV_TEST_EVIDENCE,
    GateName.G3_QA: EvidenceType.QA_EVIDENCE,
    GateName.G4_UAT: EvidenceType.UAT_EVIDENCE,
    GateName.G5_PRODUCT: EvidenceType.PRODUCT_ACCEPTANCE_EVIDENCE,
    GateName.G6_CI: EvidenceType.CI_EVIDENCE,
    GateName.G7_RELEASE: EvidenceType.RELEASE_EVIDENCE,
    GateName.G7_RELEASE: EvidenceType.RELEASE_EVIDENCE,
    GateName.G9_PRODUCTION_VERIFY: EvidenceType.PRODUCTION_VERIFICATION_EVIDENCE,
}


def evaluate_gate(name: GateName | str, evidence: Iterable[Evidence],
                  required_checks: Iterable[str] = ()) -> GateResult:
    try:
        gate = GateName(name)
    except ValueError:
        return GateResult(str(name), GateStatus.BLOCKED, "unknown gate")
    relevant = [e for e in evidence if GATE_EVIDENCE.get(gate) == e.evidence_type]
    if gate == GateName.G8_MERGE:
        return GateResult(gate.value, GateStatus.BLOCKED,
                          "merge approval is a transition, not caller-set gate evidence")
    if not relevant:
        return GateResult(gate.value, GateStatus.BLOCKED, "required evidence missing")
    latest = relevant[-1]
    if latest.status == EvidenceStatus.NOT_APPLICABLE:
        if latest.summary.strip() and latest.references:
            return GateResult(gate.value, GateStatus.NOT_APPLICABLE,
                              latest.summary, (latest.evidence_id,))
        return GateResult(gate.value, GateStatus.BLOCKED,
                          "N/A requires a reason and at least one reference", (latest.evidence_id,))
    if latest.status == EvidenceStatus.FAIL:
        return GateResult(gate.value, GateStatus.FAIL, latest.summary, (latest.evidence_id,))
    if latest.status != EvidenceStatus.PASS:
        return GateResult(gate.value, GateStatus.BLOCKED, latest.summary, (latest.evidence_id,))
    if gate == GateName.G6_CI:
        required = tuple(required_checks)
        if not required:
            return GateResult(gate.value, GateStatus.BLOCKED,
                              "no required CI checks are declared", (latest.evidence_id,))
        results = dict(latest.check_results)
        if len(results) != len(latest.check_results):
            return GateResult(gate.value, GateStatus.BLOCKED, "duplicate CI check names",
                              (latest.evidence_id,))
        missing = sorted(set(required) - results.keys())
        if missing:
            return GateResult(gate.value, GateStatus.BLOCKED,
                              "required CI checks missing: " + ", ".join(missing),
                              (latest.evidence_id,))
        bad = sorted(k for k in required if results[k] != "SUCCESS")
        if bad:
            return GateResult(gate.value, GateStatus.FAIL,
                              "required CI checks not proven successful: " + ", ".join(bad),
                              (latest.evidence_id,))
    return GateResult(gate.value, GateStatus.PASS, latest.summary, (latest.evidence_id,))
