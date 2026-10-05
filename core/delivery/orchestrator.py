from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from .defects import unresolved_required, validate_defect
from .evidence import seal_evidence, sha256_json, validate_timestamp
from .gates import GateName, GateStatus, evaluate_gate
from .models import (Defect, DefectHistoryEntry, DeliveryState, Evidence, EvidenceStatus,
                     EvidenceType, StateHistoryEntry, WorkItem)
from .roles import DeliveryRole
from .states import DeliveryState as S
from .transitions import ALLOWED_TRANSITIONS, TRANSITION_ROLES
from .validators import history_payload, validate_work_item, work_item_contract_hash


class GovernanceError(ValueError):
    """A requested governance operation failed closed."""


DEV_ROLES = {DeliveryRole.BACKEND_DEVELOPER, DeliveryRole.DATA_QUANT_DEVELOPER,
             DeliveryRole.INTEGRATION_DEVELOPER, DeliveryRole.UI_DEVELOPER}

EVIDENCE_STATES = {
    EvidenceType.REQUIREMENT_EVIDENCE: {
        S.BACKLOG, S.BLOCKED_REQUIREMENT, S.REQUIREMENT_READY, S.DESIGN_READY,
        S.IN_DEVELOPMENT, S.FAILED_VERIFICATION, S.DEV_VERIFIED, S.QA_IN_PROGRESS,
        S.QA_FAILED, S.QA_PASSED, S.SENIOR_QA, S.UAT, S.UAT_FAILED,
        S.PRODUCT_ACCEPTED, S.RELEASE_BLOCKED, S.RELEASE_READY, S.PR_OPEN,
        S.CI_FAILED, S.CI_GREEN, S.MERGE_APPROVED,
    },
    EvidenceType.ARCHITECTURE_EVIDENCE: {S.REQUIREMENT_READY, S.DESIGN_READY},
    EvidenceType.DEV_TEST_EVIDENCE: {S.IN_DEVELOPMENT},
    EvidenceType.QA_EVIDENCE: {S.QA_IN_PROGRESS},
    EvidenceType.DEFECT_EVIDENCE: {S.QA_IN_PROGRESS, S.UAT},
    EvidenceType.QA_RETEST_EVIDENCE: {S.QA_IN_PROGRESS},
    EvidenceType.SENIOR_QA_EVIDENCE: {S.QA_PASSED, S.SENIOR_QA},
    EvidenceType.UAT_EVIDENCE: {S.UAT},
    EvidenceType.PRODUCT_ACCEPTANCE_EVIDENCE: {S.UAT},
    EvidenceType.CI_EVIDENCE: {S.PR_OPEN, S.CI_GREEN},
    EvidenceType.RELEASE_EVIDENCE: {S.PRODUCT_ACCEPTED, S.RELEASE_BLOCKED,
                                    S.RELEASE_READY, S.CI_GREEN, S.MERGE_APPROVED},
    EvidenceType.PRODUCTION_VERIFICATION_EVIDENCE: {S.MERGED, S.PRODUCTION_VERIFIED},
}


class DeliveryOrchestrator:
    def __init__(self, item: WorkItem):
        validate_work_item(item)
        self.item = item

    @property
    def contract_drift(self) -> bool:
        return bool(self.item.state_history and
                    self.item.state_history[-1].contract_hash != work_item_contract_hash(self.item))

    def add_evidence(self, evidence: Evidence) -> WorkItem:
        try:
            if evidence.work_item_id != self.item.work_item_id:
                raise GovernanceError("evidence belongs to a different work item")
            if not isinstance(evidence.evidence_type, EvidenceType) or not isinstance(evidence.status, EvidenceStatus):
                raise GovernanceError("unknown evidence type or status")
            if not isinstance(evidence.role, DeliveryRole):
                raise GovernanceError("unknown evidence role")
            if self.item.current_state not in EVIDENCE_STATES[evidence.evidence_type]:
                raise GovernanceError(f"{evidence.evidence_type.value} cannot be added in {self.item.current_state.value}")
            if any(e.evidence_id == evidence.evidence_id for e in self.item.evidence):
                raise GovernanceError("evidence IDs are append-only and must be unique")
            validate_timestamp(evidence.timestamp)
            if evidence.status == EvidenceStatus.NOT_APPLICABLE and (
                not evidence.summary.strip() or not evidence.references
            ):
                raise GovernanceError("N/A requires a reason and at least one reference")
            if not evidence.summary.strip() or not evidence.references:
                raise GovernanceError("evidence summary and at least one auditable reference are required")
            previous_hash = self.item.evidence[-1].content_hash if self.item.evidence else "0" * 64
            sealed = seal_evidence(evidence, work_item_contract_hash(self.item),
                                   len(self.item.evidence) + 1, previous_hash)
            candidate = replace(self.item, evidence=self.item.evidence + (sealed,))
            validate_work_item(candidate)
        except (ValueError, AttributeError, TypeError) as exc:
            raise GovernanceError(str(exc)) from exc
        self.item = candidate
        return candidate

    def add_defect(self, defect: Defect, *, actor_role: DeliveryRole, actor: str,
                   timestamp: str, reason: str) -> WorkItem:
        try:
            actor_role = DeliveryRole(actor_role)
        except (ValueError, TypeError) as exc:
            raise GovernanceError("unknown defect author role") from exc
        if not isinstance(actor, str):
            raise GovernanceError("defect author and reason are required")
        permitted = ((self.item.current_state == S.QA_IN_PROGRESS and actor_role == DeliveryRole.QA_ENGINEER)
                     or (self.item.current_state == S.UAT and actor_role == DeliveryRole.UAT_REVIEWER))
        if not permitted:
            raise GovernanceError("QA_ENGINEER may file defects in QA; UAT_REVIEWER may file defects in UAT")
        if not actor.strip() or not reason.strip():
            raise GovernanceError("defect author and reason are required")
        try:
            validate_timestamp(timestamp)
        except ValueError as exc:
            raise GovernanceError(str(exc)) from exc
        if defect.status.value != "OPEN" or defect.developer_fix_ref or defect.qa_retest_ref or defect.regression_result:
            raise GovernanceError("new QA defects must start OPEN with no fix or retest claims")
        try:
            validate_defect(defect, self.item.work_item_id)
        except ValueError as exc:
            raise GovernanceError(str(exc)) from exc
        evidence_by_id = {e.evidence_id: e for e in self.item.evidence}
        if not set(defect.evidence) <= evidence_by_id.keys():
            raise GovernanceError("defect evidence reference is unknown")
        if not any(evidence_by_id[ref].evidence_type == EvidenceType.DEFECT_EVIDENCE
                   and evidence_by_id[ref].role == actor_role and evidence_by_id[ref].author == actor
                   and evidence_by_id[ref].status == EvidenceStatus.PASS for ref in defect.evidence):
            raise GovernanceError("defect requires authored, passing DEFECT_EVIDENCE")
        if any(e.author == actor and e.evidence_type == EvidenceType.DEV_TEST_EVIDENCE
               for e in self.item.evidence):
            raise GovernanceError("developer cannot file an independent QA/UAT defect against their own work")
        if any(d.defect_id == defect.defect_id for d in self.item.defects):
            raise GovernanceError("defect IDs are append-only and must be unique")
        entry = self._defect_event(defect.defect_id, "NONE", "OPEN", actor_role, actor,
                                   timestamp, reason,
                                   next(ref for ref in defect.evidence
                                        if evidence_by_id[ref].evidence_type == EvidenceType.DEFECT_EVIDENCE), "")
        candidate = replace(self.item, defects=self.item.defects + (defect,),
                             defect_history=self.item.defect_history + (entry,))
        validate_work_item(candidate)
        self.item = candidate
        return candidate

    def advance_defect(self, defect_id: str, target, *, actor_role: DeliveryRole,
                       actor: str, timestamp: str, reason: str, evidence_ref: str = "",
                       regression_result: str = "") -> WorkItem:
        from .defects import advance_defect
        from .models import DefectStatus
        try:
            target = DefectStatus(target)
            actor_role = DeliveryRole(actor_role)
        except (TypeError, ValueError) as exc:
            raise GovernanceError("unknown defect status or role") from exc
        try:
            validate_timestamp(timestamp)
        except ValueError as exc:
            raise GovernanceError(str(exc)) from exc
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise GovernanceError("defect actor and reason are required")
        if target.value in {"FIX_IN_PROGRESS", "READY_FOR_RETEST"} and self.item.current_state != S.IN_DEVELOPMENT:
            raise GovernanceError("developer defect work is allowed only in IN_DEVELOPMENT")
        if target.value in {"RETEST_FAILED", "RETEST_PASSED", "CLOSED"} and self.item.current_state != S.QA_IN_PROGRESS:
            raise GovernanceError("defect retest and closure are allowed only in QA_IN_PROGRESS")
        defects = list(self.item.defects)
        for index, defect in enumerate(defects):
            if defect.defect_id != defect_id:
                continue
            if target.value in {"FIX_IN_PROGRESS", "READY_FOR_RETEST"} and actor_role not in DEV_ROLES:
                raise GovernanceError("developer role required for defect fix")
            if target.value in {"RETEST_FAILED", "RETEST_PASSED", "CLOSED"} and actor_role != DeliveryRole.QA_ENGINEER:
                raise GovernanceError("QA_ENGINEER role required for retest and closure")
            if evidence_ref and evidence_ref not in {e.evidence_id for e in self.item.evidence}:
                raise GovernanceError("unknown defect evidence reference")
            evidence = next((e for e in self.item.evidence if e.evidence_id == evidence_ref), None)
            if evidence is not None and evidence.author != actor:
                raise GovernanceError("defect action actor must match referenced evidence author")
            if target.value == "READY_FOR_RETEST" and (evidence is None or
                    evidence.evidence_type != EvidenceType.DEV_TEST_EVIDENCE or evidence.role not in DEV_ROLES):
                raise GovernanceError("developer fix must reference passing developer test evidence")
            if target.value in {"RETEST_FAILED", "RETEST_PASSED"} and (evidence is None or
                    evidence.evidence_type != EvidenceType.QA_RETEST_EVIDENCE or
                    evidence.role != DeliveryRole.QA_ENGINEER):
                raise GovernanceError("QA retest must reference QA_RETEST_EVIDENCE")
            if target.value in {"RETEST_FAILED", "RETEST_PASSED"} and any(
                e.author == actor and e.evidence_type == EvidenceType.DEV_TEST_EVIDENCE
                for e in self.item.evidence
            ):
                raise GovernanceError("developer cannot independently retest their own fix")
            try:
                updated = advance_defect(defect, target, reference=evidence_ref,
                                         regression_result=regression_result)
                entry = self._defect_event(defect_id, defect.status.value, target.value,
                                           actor_role, actor, timestamp, reason, evidence_ref,
                                           regression_result)
                defects[index] = updated
                candidate = replace(self.item, defects=tuple(defects),
                                    defect_history=self.item.defect_history + (entry,))
                validate_work_item(candidate)
            except ValueError as exc:
                raise GovernanceError(str(exc)) from exc
            self.item = candidate
            return candidate
        raise GovernanceError(f"unknown defect ID: {defect_id}")

    def _defect_event(self, defect_id, source, target, role, actor, timestamp, reason, evidence_ref, regression):
        previous_hash = self.item.defect_history[-1].entry_hash if self.item.defect_history else "0" * 64
        payload = {"defect_id": defect_id, "from_status": source, "to_status": target,
                   "acting_role": role.value, "actor": actor, "timestamp": timestamp,
                   "reason": reason, "evidence_ref": evidence_ref,
                   "regression_result": regression, "previous_hash": previous_hash}
        return DefectHistoryEntry(**payload, entry_hash=sha256_json(payload))

    def allowed_next_states(self) -> tuple[str, ...]:
        allowed = set(ALLOWED_TRANSITIONS.get(self.item.current_state, set()))
        if self.contract_drift:
            allowed &= {S.BLOCKED_REQUIREMENT}
        if self.item.current_state == S.CI_GREEN:
            gaps, _ = self._lifecycle_gaps(include_ci=True)
            if gaps or unresolved_required(self.item.defects):
                allowed.discard(S.MERGE_APPROVED)
        return tuple(sorted(s.value for s in allowed))

    def readiness(self) -> dict:
        missing, invalid = self._lifecycle_gaps()
        if self.contract_drift:
            invalid.append("contract_drift_requires_requirement_block")
        blockers = sorted({g for g in missing} | {g for g in invalid})
        return {"ready": not blockers and not unresolved_required(self.item.defects),
                "blocking_gates": blockers,
                "gate_results": self.gate_results(),
                "missing_evidence": missing,
                "unresolved_defects": [d.defect_id for d in unresolved_required(self.item.defects)],
                "invalid_role_approvals": invalid,
                "contract_drift": self.contract_drift,
                "current_state": self.item.current_state.value,
                "allowed_next_states": self.allowed_next_states()}

    def gate_results(self) -> list[dict]:
        current_contract = work_item_contract_hash(self.item)
        all_evidence = tuple(e for e in self.item.evidence if e.work_item_hash == current_contract)
        cycle = self._current_cycle_evidence()
        results = []
        for gate in GateName:
            if gate == GateName.G8_MERGE:
                event = next((entry for entry in reversed(self.item.state_history)
                              if entry.to_state == S.MERGE_APPROVED.value), None)
                results.append({"gate": gate.value,
                                "status": GateStatus.PASS.value if event else GateStatus.BLOCKED.value,
                                "reason": "merge approval recorded" if event else "merge approval transition not recorded",
                                "evidence_ids": list(event.evidence_ids) if event else []})
                continue
            proof = all_evidence if gate in {GateName.G0_REQUIREMENT, GateName.G1_ARCHITECTURE} else cycle
            result = evaluate_gate(gate, proof, self.item.required_ci_checks)
            results.append({"gate": result.gate, "status": result.status.value,
                            "reason": result.reason, "evidence_ids": list(result.evidence_ids)})
        return results

    def transition(self, target: DeliveryState | str, *, acting_role: DeliveryRole | str,
                   actor: str, timestamp: str, reason: str,
                   evidence_ids: Iterable[str] = ()) -> WorkItem:
        try:
            source, target_state = self.item.current_state, DeliveryState(target)
            role = DeliveryRole(acting_role)
        except (ValueError, TypeError) as exc:
            raise GovernanceError("unknown workflow state or role") from exc
        if target_state not in ALLOWED_TRANSITIONS.get(source, set()):
            raise GovernanceError(f"invalid transition {source.value} -> {target_state.value}")
        if self.contract_drift and target_state != S.BLOCKED_REQUIREMENT:
            raise GovernanceError("work-item contract changed; transition to BLOCKED_REQUIREMENT before proceeding")
        if role not in TRANSITION_ROLES.get((source, target_state), set()):
            raise GovernanceError("acting role is not authorized for this transition")
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise GovernanceError("actor and reason are required")
        try:
            validate_timestamp(timestamp)
            selected = self._selected_evidence(tuple(evidence_ids))
            self._validate_transition(source, target_state, role, actor, timestamp, selected)
            previous_hash = self.item.state_history[-1].entry_hash if self.item.state_history else "0" * 64
            provisional = StateHistoryEntry(source.value, target_state.value, role.value, actor,
                                            timestamp, reason, tuple(e.evidence_id for e in selected),
                                            work_item_contract_hash(self.item), previous_hash, "")
            entry_hash = sha256_json(history_payload(provisional))
            entry = replace(provisional, entry_hash=entry_hash)
            candidate = replace(self.item, current_state=target_state, acting_role=role.value,
                                state_history=self.item.state_history + (entry,))
            validate_work_item(candidate)
        except GovernanceError:
            raise
        except (ValueError, TypeError, AttributeError) as exc:
            raise GovernanceError(str(exc)) from exc
        self.item = candidate
        return candidate

    def _selected_evidence(self, ids: tuple[str, ...]) -> tuple[Evidence, ...]:
        if len(ids) != len(set(ids)):
            raise GovernanceError("duplicate evidence reference")
        by_id = {e.evidence_id: e for e in self.item.evidence}
        if not set(ids) <= by_id.keys():
            raise GovernanceError("unknown evidence reference")
        return tuple(by_id[i] for i in ids)

    @staticmethod
    def _require(selected: tuple[Evidence, ...], kind: EvidenceType,
                status: EvidenceStatus = EvidenceStatus.PASS,
                roles: set[DeliveryRole] | None = None) -> Evidence:
        for evidence in reversed(selected):
            if (evidence.evidence_type == kind and evidence.status == status
                    and (roles is None or evidence.role in roles)):
                return evidence
        raise GovernanceError(f"required {kind.value} with status {status.value} missing")

    def _validate_transition(self, source: S, target: S, role: DeliveryRole,
                             actor: str, transition_time: str,
                             selected: tuple[Evidence, ...]) -> None:
        byid = {e.evidence_id: e for e in self.item.evidence}
        if any(e.role == role and e.author != actor for e in selected):
            raise GovernanceError("acting actor must match evidence authored in the acting role")
        current_contract = work_item_contract_hash(self.item)
        if any(e.work_item_hash != current_contract for e in selected):
            raise GovernanceError("transition cannot use evidence from a superseded work-item contract")
        latest_by_type_role = {}
        for proof in self.item.evidence:
            latest_by_type_role[(proof.evidence_type, proof.role)] = proof
        for proof in selected:
            latest = latest_by_type_role[(proof.evidence_type, proof.role)]
            if proof.evidence_id != latest.evidence_id:
                raise GovernanceError("transition cannot use superseded evidence for the same role and type")
        for evidence in selected:
            if _time(evidence.timestamp) > _time(transition_time):
                raise GovernanceError("transition cannot cite evidence from the future")
        after_dev = {S.QA_IN_PROGRESS, S.QA_FAILED, S.QA_PASSED, S.SENIOR_QA, S.UAT,
                     S.UAT_FAILED, S.PRODUCT_ACCEPTED, S.RELEASE_READY, S.RELEASE_BLOCKED,
                     S.PR_OPEN, S.CI_GREEN, S.CI_FAILED, S.MERGE_APPROVED}
        if target in after_dev:
            dev_starts = [entry.timestamp for entry in self.item.state_history
                          if entry.to_state == S.IN_DEVELOPMENT.value]
            if dev_starts:
                min_time = _time(dev_starts[-1])
                if any(_time(e.timestamp) < min_time for e in selected
                       if e.evidence_type in {EvidenceType.QA_EVIDENCE, EvidenceType.QA_RETEST_EVIDENCE,
                                              EvidenceType.SENIOR_QA_EVIDENCE, EvidenceType.UAT_EVIDENCE,
                                              EvidenceType.PRODUCT_ACCEPTANCE_EVIDENCE,
                                              EvidenceType.RELEASE_EVIDENCE, EvidenceType.CI_EVIDENCE}):
                    raise GovernanceError("stale lifecycle evidence predates the current development cycle")
        freshness_state = {
            S.RELEASE_READY: S.PRODUCT_ACCEPTED,
            S.PR_OPEN: S.RELEASE_READY,
            S.CI_GREEN: S.PR_OPEN,
            S.CI_FAILED: S.PR_OPEN,
            S.MERGED: S.MERGE_APPROVED,
            S.PRODUCTION_VERIFIED: S.MERGED,
        }.get(target)
        if freshness_state is not None:
            prior_events = [entry.timestamp for entry in self.item.state_history
                            if entry.to_state == freshness_state.value]
            if prior_events:
                entered_at = _time(prior_events[-1])
                relevant = [e for e in selected if e.evidence_type in {
                    EvidenceType.RELEASE_EVIDENCE, EvidenceType.CI_EVIDENCE,
                    EvidenceType.PRODUCTION_VERIFICATION_EVIDENCE}]
                if relevant and any(_time(e.timestamp) < entered_at for e in relevant):
                    raise GovernanceError(f"transition evidence predates {freshness_state.value}")
        req_roles = {DeliveryRole.BUSINESS_ANALYST}
        arch_roles = {DeliveryRole.SOLUTION_ARCHITECT, DeliveryRole.SYSTEM_ARCHITECT,
                      DeliveryRole.QUANT_RESEARCH_ARCHITECT}
        if (source, target) in {(S.BACKLOG, S.REQUIREMENT_READY),
                                (S.BLOCKED_REQUIREMENT, S.REQUIREMENT_READY)}:
            self._require(selected, EvidenceType.REQUIREMENT_EVIDENCE, roles=req_roles)
            try:
                validate_work_item(self.item, complete=True)
            except ValueError as exc:
                raise GovernanceError(f"definition of ready incomplete: {exc}") from exc
        elif (source, target) == (S.REQUIREMENT_READY, S.DESIGN_READY):
            arch = self._require(selected, EvidenceType.ARCHITECTURE_EVIDENCE, roles=arch_roles)
            po = self._require(selected, EvidenceType.REQUIREMENT_EVIDENCE,
                               roles={DeliveryRole.PRODUCT_OWNER})
            ba = self._require(selected, EvidenceType.REQUIREMENT_EVIDENCE,
                               roles={DeliveryRole.BUSINESS_ANALYST})
            if po.author == ba.author or arch.author == ba.author:
                raise GovernanceError("Product Owner and Architecture must independently review BA requirements")
        elif (source, target) == (S.IN_DEVELOPMENT, S.DEV_VERIFIED):
            self._require(selected, EvidenceType.DEV_TEST_EVIDENCE, roles=DEV_ROLES)
        elif (source, target) == (S.QA_IN_PROGRESS, S.QA_FAILED):
            qa = self._require(selected, EvidenceType.QA_EVIDENCE, EvidenceStatus.FAIL,
                               {DeliveryRole.QA_ENGINEER})
            dev_authors = {e.author for e in self.item.evidence
                           if e.evidence_type == EvidenceType.DEV_TEST_EVIDENCE}
            if qa.author in dev_authors:
                raise GovernanceError("developer cannot perform independent QA")
            if not any(d.status.value != "CLOSED" for d in self.item.defects):
                self._require(selected, EvidenceType.DEFECT_EVIDENCE, EvidenceStatus.PASS,
                              {DeliveryRole.QA_ENGINEER})
        elif (source, target) == (S.QA_IN_PROGRESS, S.QA_PASSED):
            qa = self._require(selected, EvidenceType.QA_EVIDENCE, roles={DeliveryRole.QA_ENGINEER})
            if unresolved_required(self.item.defects):
                raise GovernanceError("unresolved S1/S2 defects block QA_PASSED")
            dev_authors = {e.author for e in self.item.evidence if e.evidence_type == EvidenceType.DEV_TEST_EVIDENCE}
            if qa.author in dev_authors:
                raise GovernanceError("developer cannot self-approve QA")
            self._validate_retests(qa, byid)
        elif (source, target) == (S.QA_FAILED, S.IN_DEVELOPMENT) or (source, target) == (S.UAT_FAILED, S.IN_DEVELOPMENT):
            if not any(d.status.value != "CLOSED" for d in self.item.defects):
                raise GovernanceError("defect evidence is required to return to development")
        elif (source, target) == (S.QA_PASSED, S.SENIOR_QA):
            senior = self._require(selected, EvidenceType.SENIOR_QA_EVIDENCE, roles={DeliveryRole.SENIOR_QA})
            qa = next((e for e in reversed(self.item.evidence)
                       if e.evidence_type == EvidenceType.QA_EVIDENCE
                       and e.status == EvidenceStatus.PASS), None)
            if qa and senior.author == qa.author:
                raise GovernanceError("Senior QA must independently review QA work")
        elif (source, target) == (S.SENIOR_QA, S.UAT):
            self._require(selected, EvidenceType.SENIOR_QA_EVIDENCE, roles={DeliveryRole.SENIOR_QA})
        elif (source, target) == (S.UAT, S.UAT_FAILED):
            self._require(selected, EvidenceType.UAT_EVIDENCE, EvidenceStatus.FAIL,
                          {DeliveryRole.UAT_REVIEWER})
            if not any(d.status.value != "CLOSED" for d in self.item.defects):
                raise GovernanceError("UAT failure must include at least one tracked defect")
        elif (source, target) == (S.UAT, S.PRODUCT_ACCEPTED):
            uat = next((e for e in reversed(selected) if e.evidence_type == EvidenceType.UAT_EVIDENCE
                        and e.role == DeliveryRole.UAT_REVIEWER
                        and e.status in {EvidenceStatus.PASS, EvidenceStatus.NOT_APPLICABLE}), None)
            if uat is None:
                raise GovernanceError("UAT pass or documented valid N/A evidence is required")
            self._require(selected, EvidenceType.PRODUCT_ACCEPTANCE_EVIDENCE,
                          roles={DeliveryRole.PRODUCT_OWNER})
            qa = next((e for e in reversed(self.item.evidence)
                       if e.evidence_type == EvidenceType.QA_EVIDENCE
                       and e.status == EvidenceStatus.PASS), None)
            if (any(e.evidence_type == EvidenceType.DEV_TEST_EVIDENCE and e.author == actor
                    for e in self.item.evidence) or (qa and qa.author == actor)):
                raise GovernanceError("Product Owner cannot accept their own development or QA work")
        elif (source, target) in {(S.PRODUCT_ACCEPTED, S.RELEASE_READY),
                                  (S.RELEASE_BLOCKED, S.RELEASE_READY),
                                  (S.RELEASE_READY, S.PR_OPEN)}:
            self._require(selected, EvidenceType.RELEASE_EVIDENCE,
                          roles={DeliveryRole.RELEASE_MANAGER})
            gaps, invalid = self._lifecycle_gaps()
            if gaps or invalid:
                raise GovernanceError(f"release gates blocked: {sorted(set(gaps + invalid))}")
            if unresolved_required(self.item.defects):
                raise GovernanceError("unresolved severe defects block release")
        elif (source, target) == (S.PRODUCT_ACCEPTED, S.RELEASE_BLOCKED):
            if not reason_has_release_blocker(selected):
                raise GovernanceError("release block requires explicit failed/blocked RELEASE_EVIDENCE")
        elif (source, target) == (S.RELEASE_READY, S.RELEASE_BLOCKED):
            if not reason_has_release_blocker(selected):
                raise GovernanceError("release block requires explicit failed/blocked RELEASE_EVIDENCE")
        elif (source, target) in {(S.PR_OPEN, S.CI_GREEN), (S.PR_OPEN, S.CI_FAILED),
                                  (S.CI_GREEN, S.CI_FAILED)}:
            ci = self._require(selected, EvidenceType.CI_EVIDENCE,
                               EvidenceStatus.PASS if target == S.CI_GREEN else EvidenceStatus.FAIL,
                               {DeliveryRole.RELEASE_MANAGER})
            latest_ci = next((e for e in reversed(self.item.evidence)
                              if e.evidence_type == EvidenceType.CI_EVIDENCE), None)
            if latest_ci is None or latest_ci.evidence_id != ci.evidence_id:
                raise GovernanceError("CI evidence is not the latest CI result")
            result = evaluate_gate(GateName.G6_CI, (ci,), self.item.required_ci_checks)
            if target == S.CI_GREEN and result.status != GateStatus.PASS:
                raise GovernanceError(f"CI gate not green: {result.reason}")
        elif (source, target) == (S.CI_GREEN, S.MERGE_APPROVED):
            self._require(selected, EvidenceType.RELEASE_EVIDENCE,
                          roles={DeliveryRole.RELEASE_MANAGER})
            gaps, invalid = self._lifecycle_gaps(include_ci=True)
            if gaps or invalid:
                raise GovernanceError(f"merge gates blocked: {sorted(set(gaps + invalid))}")
            if unresolved_required(self.item.defects):
                raise GovernanceError("unresolved severe defects block merge approval")
        elif (source, target) == (S.MERGE_APPROVED, S.MERGED):
            ev = self._require(selected, EvidenceType.RELEASE_EVIDENCE,
                               roles={DeliveryRole.RELEASE_MANAGER})
            if not ev.references:
                raise GovernanceError("MERGED requires explicit repository merge reference")
        elif (source, target) == (S.MERGED, S.PRODUCTION_VERIFIED):
            production = self._require(selected, EvidenceType.PRODUCTION_VERIFICATION_EVIDENCE,
                                       roles={DeliveryRole.PRODUCTION_SRE})
            release = next((e for e in reversed(self.item.evidence)
                            if e.evidence_type == EvidenceType.RELEASE_EVIDENCE
                            and e.status == EvidenceStatus.PASS), None)
            if release and production.author == release.author:
                raise GovernanceError("Production/SRE verification must be independent from release ownership")
        elif (source, target) == (S.PRODUCTION_VERIFIED, S.DONE):
            self._require(selected, EvidenceType.PRODUCTION_VERIFICATION_EVIDENCE,
                          roles={DeliveryRole.PRODUCTION_SRE})
        elif target == S.BLOCKED_REQUIREMENT:
            self._require(selected, EvidenceType.REQUIREMENT_EVIDENCE,
                          EvidenceStatus.BLOCKED, req_roles)
        elif source in {S.BLOCKED_DATA, S.BLOCKED_RESEARCH} and target == S.BACKLOG:
            if not selected or all(e.status != EvidenceStatus.PASS for e in selected):
                raise GovernanceError("unblocking requires explicit passing resolution evidence")
        elif target in {S.BLOCKED_DATA, S.BLOCKED_RESEARCH, S.FAILED_VERIFICATION}:
            if not selected or all(e.status not in {EvidenceStatus.BLOCKED, EvidenceStatus.FAIL} for e in selected):
                raise GovernanceError("blocking/failure transition requires FAIL or BLOCKED evidence")
        elif source == S.CI_FAILED and target == S.PR_OPEN:
            self._require(selected, EvidenceType.RELEASE_EVIDENCE, roles={DeliveryRole.RELEASE_MANAGER})

    def _validate_retests(self, qa: Evidence, byid: dict[str, Evidence]) -> None:
        fixed = [d for d in self.item.defects if d.developer_fix_ref]
        for defect in fixed:
            retest = byid.get(defect.qa_retest_ref)
            if retest is None or retest.evidence_type != EvidenceType.QA_RETEST_EVIDENCE or retest.status != EvidenceStatus.PASS:
                raise GovernanceError(f"passing QA retest required for defect {defect.defect_id}")
            if retest.evidence_id not in qa.references:
                raise GovernanceError("new adversarial QA evidence must reference the passing retest")
            if _time(qa.timestamp) <= _time(retest.timestamp):
                raise GovernanceError("adversarial QA pass must occur after the retest")
            if defect.status.value != "CLOSED":
                raise GovernanceError(f"fixed defect {defect.defect_id} must be closed after retest")

    def _lifecycle_gaps(self, include_ci: bool = False) -> tuple[list[str], list[str]]:
        evidence = self._current_cycle_evidence()
        current_contract = work_item_contract_hash(self.item)
        contract_evidence = tuple(e for e in self.item.evidence if e.work_item_hash == current_contract)
        missing, invalid = [], []
        requirements = [GateName.G0_REQUIREMENT, GateName.G1_ARCHITECTURE]
        # Analysis/design evidence remains valid across an implementation cycle;
        # development, QA, acceptance, and release evidence must be from the
        # current implementation cycle.
        requirements.extend([GateName.G2_DEVELOPMENT, GateName.G3_QA,
                             GateName.G4_UAT, GateName.G5_PRODUCT, GateName.G7_RELEASE])
        if include_ci:
            requirements.append(GateName.G6_CI)
        for name in requirements:
            proof = contract_evidence if name in {GateName.G0_REQUIREMENT, GateName.G1_ARCHITECTURE} else evidence
            result = evaluate_gate(name, proof, self.item.required_ci_checks)
            if result.status not in {GateStatus.PASS, GateStatus.NOT_APPLICABLE}:
                missing.append(f"{name.value}:{result.status.value}")
        def latest_author(kind, statuses=(EvidenceStatus.PASS,)):
            candidates = [e for e in evidence if e.evidence_type == kind and e.status in statuses]
            return candidates[-1].author if candidates else None
        dev_authors = {e.author for e in evidence if e.evidence_type == EvidenceType.DEV_TEST_EVIDENCE}
        arch_author = latest_author(EvidenceType.ARCHITECTURE_EVIDENCE)
        qa_author = latest_author(EvidenceType.QA_EVIDENCE)
        senior_author = latest_author(EvidenceType.SENIOR_QA_EVIDENCE)
        uat_author = latest_author(EvidenceType.UAT_EVIDENCE,
                                   (EvidenceStatus.PASS, EvidenceStatus.NOT_APPLICABLE))
        product_author = latest_author(EvidenceType.PRODUCT_ACCEPTANCE_EVIDENCE)
        release_author = latest_author(EvidenceType.RELEASE_EVIDENCE)
        production_author = latest_author(EvidenceType.PRODUCTION_VERIFICATION_EVIDENCE)
        if qa_author and qa_author in dev_authors:
            invalid.append("developer_self_approval_as_QA")
        if arch_author and arch_author in dev_authors:
            invalid.append("architecture_self_certified_implementation")
        if senior_author and senior_author == qa_author:
            invalid.append("QA_self_approval_as_Senior_QA")
        if uat_author and (uat_author in dev_authors or uat_author == qa_author):
            invalid.append("developer_or_QA_self_approval_as_UAT")
        if product_author and (product_author in dev_authors or product_author in {qa_author, uat_author}):
            invalid.append("delivery_author_self_approval_as_Product_Owner")
        if release_author and (release_author in dev_authors or release_author in {qa_author, senior_author}):
            invalid.append("delivery_author_self_approval_as_Release_Manager")
        if production_author and (production_author == release_author or production_author in dev_authors
                                  or production_author in {qa_author, senior_author}):
            invalid.append("delivery_author_self_approval_as_Production_SRE")
        for e in evidence:
            if e.status == EvidenceStatus.NOT_APPLICABLE and (not e.summary.strip() or not e.references):
                invalid.append(f"unjustified_NA:{e.evidence_id}")
        return missing, invalid

    def _current_cycle_evidence(self) -> tuple[Evidence, ...]:
        start_time = None
        for entry in self.item.state_history:
            if entry.to_state == S.IN_DEVELOPMENT.value:
                start_time = _time(entry.timestamp)
        result = []
        current_contract = work_item_contract_hash(self.item)
        for evidence in self.item.evidence:
            if (evidence.work_item_hash == current_contract
                    and (start_time is None or _time(evidence.timestamp) > start_time)):
                result.append(evidence)
        return tuple(result)


def _time(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def reason_has_release_blocker(evidence: tuple[Evidence, ...]) -> bool:
    return any(e.evidence_type == EvidenceType.RELEASE_EVIDENCE
               and e.status in {EvidenceStatus.FAIL, EvidenceStatus.BLOCKED} for e in evidence)
