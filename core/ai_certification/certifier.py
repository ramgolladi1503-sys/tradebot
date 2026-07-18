from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .bundle import CertificationBundle, canonical_json_bytes
from .contracts import (
    CertificationReport,
    EvidenceCertification,
    GateResult,
    GateStatus,
    StrategyVerdict,
)
from .knowledge import CuratedKnowledgeBase
from .policy import CertificationPolicy, default_policy
from .source_validator import validate_source_index
from .validators import DEFAULT_VALIDATORS, Validator


CERTIFICATION_VALIDATORS: tuple[Validator, ...] = (
    DEFAULT_VALIDATORS[0],
    DEFAULT_VALIDATORS[1],
    validate_source_index,
    *DEFAULT_VALIDATORS[2:],
)


@dataclass
class BacktestCertificationAgent:
    """Read-only orchestration layer; deterministic validators own the verdict."""

    policy: CertificationPolicy = default_policy()
    validators: tuple[Validator, ...] = CERTIFICATION_VALIDATORS
    knowledge_base: CuratedKnowledgeBase | None = None

    def certify(self, bundle_path: str | Path) -> CertificationReport:
        bundle = CertificationBundle.load(bundle_path)
        gates: list[GateResult] = []
        for validator in self.validators:
            try:
                gates.append(validator(bundle, self.policy))
            except Exception as exc:
                gates.append(
                    GateResult(
                        gate=getattr(validator, "__name__", "unknown_validator"),
                        status=GateStatus.ERROR,
                        reason_code="VALIDATOR_EXCEPTION",
                        summary=f"Validator failed closed: {type(exc).__name__}: {exc}",
                    )
                )

        evidence_status = _evidence_status(gates)
        strategy_verdict = _strategy_verdict(gates, evidence_status)
        blockers = tuple(
            f"{gate.gate}:{gate.reason_code}"
            for gate in gates
            if gate.mandatory
            and gate.status
            in (GateStatus.FAIL, GateStatus.UNEVALUATED, GateStatus.ERROR)
        )
        warnings = tuple(
            f"{gate.gate}:{gate.reason_code}"
            for gate in gates
            if not gate.mandatory and gate.status is not GateStatus.PASS
        )
        bundle_digest = bundle.digest()
        knowledge_refs = self._knowledge_refs(gates)
        trace_payload = {
            "run_id": str(bundle.manifest.get("run_id", "")),
            "bundle_digest": bundle_digest,
            "policy_version": self.policy.version,
            "gates": [gate.to_dict() for gate in gates],
            "evidence_status": evidence_status.value,
            "strategy_verdict": strategy_verdict.value,
        }
        trace_id = hashlib.sha256(canonical_json_bytes(trace_payload)).hexdigest()
        return CertificationReport(
            schema_version="1.0",
            run_id=str(bundle.manifest.get("run_id", "UNKNOWN")),
            strategy_id=str(bundle.manifest.get("strategy_id", "UNKNOWN")),
            evidence_certification=evidence_status,
            strategy_verdict=strategy_verdict,
            policy_version=self.policy.version,
            repository_commit=str(bundle.manifest.get("repository_commit", "UNKNOWN")),
            bundle_digest=bundle_digest,
            trace_id=trace_id,
            gates=tuple(gates),
            blockers=blockers,
            warnings=warnings,
            knowledge_refs=knowledge_refs,
        )

    def _knowledge_refs(self, gates: Iterable[GateResult]) -> tuple[str, ...]:
        if self.knowledge_base is None:
            return ()
        query = " ".join(
            f"{gate.gate} {gate.reason_code} {gate.summary}"
            for gate in gates
            if gate.status is not GateStatus.PASS
        ) or "strict option replay certification policy"
        return tuple(
            chunk.citation for chunk in self.knowledge_base.retrieve(query, limit=4)
        )


def _evidence_status(gates: Iterable[GateResult]) -> EvidenceCertification:
    mandatory = [gate for gate in gates if gate.mandatory]
    if any(gate.status is GateStatus.ERROR for gate in mandatory):
        return EvidenceCertification.AGENT_ERROR
    if any(gate.status is GateStatus.FAIL for gate in mandatory):
        return EvidenceCertification.REJECTED
    if any(gate.status is GateStatus.UNEVALUATED for gate in mandatory):
        return EvidenceCertification.INSUFFICIENT_EVIDENCE
    return EvidenceCertification.CERTIFIED


def _strategy_verdict(
    gates: Iterable[GateResult],
    evidence_status: EvidenceCertification,
) -> StrategyVerdict:
    gate_map = {gate.gate: gate for gate in gates}
    if evidence_status is EvidenceCertification.REJECTED:
        timing = gate_map.get("temporal_causality")
        if timing is not None and timing.status is GateStatus.FAIL:
            return StrategyVerdict.INVALID_DUE_TO_LEAKAGE
        data_gates = (
            "bundle_manifest",
            "artifact_hashes",
            "source_artifact_provenance",
            "source_authority",
            "data_provenance",
            "execution_realism",
        )
        if any(
            gate_map.get(name) is not None
            and gate_map[name].status is GateStatus.FAIL
            for name in data_gates
        ):
            return StrategyVerdict.INVALID_DUE_TO_DATA
        return StrategyVerdict.WITHHELD
    if evidence_status is not EvidenceCertification.CERTIFIED:
        return StrategyVerdict.WITHHELD
    consistency = gate_map.get("strategy_result_consistency")
    if consistency is None or consistency.status is not GateStatus.PASS:
        return StrategyVerdict.WITHHELD
    computed = consistency.details.get("computed_verdict")
    try:
        return StrategyVerdict(str(computed))
    except ValueError:
        return StrategyVerdict.WITHHELD


def certify_bundle(
    bundle_path: str | Path,
    *,
    repository_root: str | Path | None = None,
    policy: CertificationPolicy | None = None,
) -> CertificationReport:
    knowledge = (
        CuratedKnowledgeBase.from_repository(repository_root)
        if repository_root is not None
        else None
    )
    agent = BacktestCertificationAgent(
        policy=policy or default_policy(),
        knowledge_base=knowledge,
    )
    return agent.certify(bundle_path)
