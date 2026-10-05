from __future__ import annotations

from datetime import datetime
from typing import Any

from .defects import validate_defect
from .evidence import canonical_json, sha256_json, validate_timestamp, verify_evidence_hash
from .models import (DeliveryState, Defect, DefectHistoryEntry, DefectSeverity, DefectStatus, Evidence,
                     EvidenceStatus, EvidenceType, StateHistoryEntry, WorkItem,
                     WorkItemType, WORK_ITEM_FIELDS)
from .roles import DeliveryRole


def _required_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def history_payload(entry: StateHistoryEntry) -> dict[str, Any]:
    return {"from_state": entry.from_state, "to_state": entry.to_state,
            "acting_role": entry.acting_role, "actor": entry.actor,
            "timestamp": entry.timestamp, "reason": entry.reason,
            "evidence_ids": list(entry.evidence_ids), "contract_hash": entry.contract_hash,
            "previous_hash": entry.previous_hash}


def defect_history_payload(entry: DefectHistoryEntry) -> dict[str, Any]:
    return {"defect_id": entry.defect_id, "from_status": entry.from_status,
            "to_status": entry.to_status, "acting_role": entry.acting_role,
            "actor": entry.actor, "timestamp": entry.timestamp, "reason": entry.reason,
            "evidence_ref": entry.evidence_ref, "regression_result": entry.regression_result,
            "previous_hash": entry.previous_hash}


def work_item_contract_hash(item: WorkItem) -> str:
    names = ("work_item_id", "type", "parent_epic", "parent_feature", "title", "schema_version", "priority",
             "business_goal", "current_behavior", "expected_behavior", "in_scope", "out_of_scope",
             "dependencies", "acceptance_criteria", "safety_constraints", "architecture_impact",
             "allowed_paths", "forbidden_paths", "expected_tests", "qa_attack_plan", "uat_criteria",
             "release_gates", "rollback_plan", "required_ci_checks", "extensions")
    return sha256_json({name: getattr(item, name) for name in names})


def validate_history(item: WorkItem) -> None:
    prior_hash = "0" * 64
    prior_state = DeliveryState.BACKLOG.value
    prior_time = None
    for entry in item.state_history:
        try:
            DeliveryState(entry.from_state)
            DeliveryState(entry.to_state)
            DeliveryRole(entry.acting_role)
        except ValueError as exc:
            raise ValueError("unknown state or role in state history") from exc
        validate_timestamp(entry.timestamp)
        moment = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))
        if prior_time is not None and moment <= prior_time:
            raise ValueError("state history timestamps must increase strictly")
        if entry.from_state != prior_state:
            raise ValueError("state history is discontinuous or corrupted")
        from .transitions import ALLOWED_TRANSITIONS, TRANSITION_ROLES
        source, target = DeliveryState(entry.from_state), DeliveryState(entry.to_state)
        if target not in ALLOWED_TRANSITIONS.get(source, set()):
            raise ValueError("state history contains a forbidden transition")
        if DeliveryRole(entry.acting_role) not in TRANSITION_ROLES.get((source, target), set()):
            raise ValueError("state history contains an unauthorized role")
        if not entry.actor.strip() or not entry.reason.strip():
            raise ValueError("state history actor and reason are required")
        if len(entry.contract_hash) != 64 or any(c not in "0123456789abcdef" for c in entry.contract_hash):
            raise ValueError("state history contract hash is malformed")
        if entry.previous_hash != prior_hash:
            raise ValueError("state history hash chain is corrupted")
        expected = sha256_json({**history_payload(entry)})
        if entry.entry_hash != expected:
            raise ValueError("state history entry hash is corrupted")
        prior_hash, prior_state, prior_time = entry.entry_hash, entry.to_state, moment
    if item.current_state.value != prior_state:
        raise ValueError("current state does not match state history")


def validate_defect_history(item: WorkItem) -> None:
    prior_hash, prior_time = "0" * 64, None
    statuses: dict[str, str] = {}
    evidence = {e.evidence_id: e for e in item.evidence}
    dev = {DeliveryRole.BACKEND_DEVELOPER, DeliveryRole.DATA_QUANT_DEVELOPER,
           DeliveryRole.INTEGRATION_DEVELOPER, DeliveryRole.UI_DEVELOPER}
    allowed = {
        ("NONE", "OPEN"): {DeliveryRole.QA_ENGINEER, DeliveryRole.UAT_REVIEWER},
        ("OPEN", "FIX_IN_PROGRESS"): dev,
        ("FIX_IN_PROGRESS", "READY_FOR_RETEST"): dev,
        ("READY_FOR_RETEST", "RETEST_FAILED"): {DeliveryRole.QA_ENGINEER},
        ("READY_FOR_RETEST", "RETEST_PASSED"): {DeliveryRole.QA_ENGINEER},
        ("RETEST_FAILED", "FIX_IN_PROGRESS"): dev,
        ("RETEST_PASSED", "CLOSED"): {DeliveryRole.QA_ENGINEER},
    }
    for event in item.defect_history:
        try:
            role = DeliveryRole(event.acting_role)
            DefectStatus(event.to_status)
        except ValueError as exc:
            raise ValueError("unknown role or status in defect history") from exc
        validate_timestamp(event.timestamp)
        moment = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        if prior_time is not None and moment <= prior_time:
            raise ValueError("defect history timestamps must increase strictly")
        if statuses.get(event.defect_id, "NONE") != event.from_status:
            raise ValueError("defect history is discontinuous")
        if role not in allowed.get((event.from_status, event.to_status), set()):
            raise ValueError("defect history contains an unauthorized transition")
        if not event.actor.strip() or not event.reason.strip() or event.previous_hash != prior_hash:
            raise ValueError("defect history actor, reason, or hash chain is invalid")
        proof = evidence.get(event.evidence_ref) if event.evidence_ref else None
        if event.evidence_ref and (proof is None or proof.author != event.actor or proof.role != role):
            raise ValueError("defect history references invalid or mismatched evidence")
        if proof is not None and datetime.fromisoformat(proof.timestamp.replace("Z", "+00:00")) > moment:
            raise ValueError("defect history cites evidence from the future")
        if event.to_status == DefectStatus.OPEN.value and (
            proof is None or proof.evidence_type != EvidenceType.DEFECT_EVIDENCE
            or proof.status != EvidenceStatus.PASS
        ):
            raise ValueError("new defect history requires authored passing defect evidence")
        if event.to_status == DefectStatus.READY_FOR_RETEST.value and (
            proof is None or proof.evidence_type != EvidenceType.DEV_TEST_EVIDENCE
            or proof.status != EvidenceStatus.PASS
        ):
            raise ValueError("defect history lacks passing developer fix evidence")
        if event.to_status in {DefectStatus.RETEST_FAILED.value, DefectStatus.RETEST_PASSED.value}:
            expected = EvidenceStatus.FAIL if event.to_status == DefectStatus.RETEST_FAILED.value else EvidenceStatus.PASS
            if proof is None or proof.evidence_type != EvidenceType.QA_RETEST_EVIDENCE or proof.status != expected:
                raise ValueError("defect history lacks matching QA retest evidence")
        if event.to_status == DefectStatus.CLOSED.value and not event.regression_result.strip():
            raise ValueError("defect closure lacks a regression result")
        if event.entry_hash != sha256_json(defect_history_payload(event)):
            raise ValueError("defect history hash is corrupted")
        statuses[event.defect_id] = event.to_status
        prior_hash, prior_time = event.entry_hash, moment
    current = {d.defect_id: d.status.value for d in item.defects}
    if statuses != current:
        raise ValueError("defect status does not match defect history")


def validate_work_item(item: WorkItem, *, complete: bool = False) -> None:
    _required_text(item.work_item_id, "work_item_id")
    _required_text(item.title, "title")
    if not isinstance(item.type, WorkItemType) or not isinstance(item.current_state, DeliveryState):
        raise ValueError("unknown work-item type or state")
    if item.schema_version != 1:
        raise ValueError(f"unsupported work-item schema_version: {item.schema_version!r}")
    try:
        canonical_json(work_item_to_dict(item))
    except (TypeError, ValueError) as exc:
        raise ValueError("work item contains non-JSON or non-finite values") from exc
    evidence_ids: set[str] = set()
    prior_evidence_hash = "0" * 64
    for expected_sequence, e in enumerate(item.evidence, start=1):
        _required_text(e.evidence_id, "evidence_id")
        if e.work_item_id != item.work_item_id:
            raise ValueError("evidence belongs to a different work item")
        _required_text(e.author, "evidence author")
        _required_text(e.summary, "evidence summary")
        if not e.references or any(not isinstance(ref, str) or not ref.strip() for ref in e.references):
            raise ValueError("evidence requires non-empty auditable references")
        if e.evidence_id in evidence_ids:
            raise ValueError("duplicate evidence ID")
        evidence_ids.add(e.evidence_id)
        if not isinstance(e.evidence_type, EvidenceType) or not isinstance(e.status, EvidenceStatus):
            raise ValueError("unknown evidence type or status")
        try:
            DeliveryRole(e.role)
        except ValueError as exc:
            raise ValueError("unknown evidence role") from exc
        validate_timestamp(e.timestamp)
        if any(not isinstance(check, (tuple, list)) or len(check) != 2
               or not all(isinstance(part, str) and part.strip() for part in check)
               for check in e.check_results):
            raise ValueError("malformed CI check result")
        check_names = [check[0] for check in e.check_results]
        if len(check_names) != len(set(check_names)):
            raise ValueError("duplicate CI check result")
        if not verify_evidence_hash(e):
            raise ValueError(f"evidence hash missing or invalid: {e.evidence_id}")
        if (len(e.work_item_hash) != 64
                or any(c not in "0123456789abcdef" for c in e.work_item_hash)):
            raise ValueError(f"evidence contract hash is malformed: {e.evidence_id}")
        if e.sequence != expected_sequence or e.previous_hash != prior_evidence_hash:
            raise ValueError("evidence history sequence/hash chain is corrupted")
        prior_evidence_hash = e.content_hash
        if e.status.value == "NOT_APPLICABLE" and (not e.summary.strip() or not e.references):
            raise ValueError("N/A evidence requires justification and reference")
    validate_history(item)
    evidence_by_id = {e.evidence_id: e for e in item.evidence}
    if any(not set(entry.evidence_ids) <= evidence_ids for entry in item.state_history):
        raise ValueError("state history references unknown evidence")
    for event in item.state_history:
        for evidence_id in event.evidence_ids:
            proof = evidence_by_id[evidence_id]
            if proof.work_item_hash != event.contract_hash:
                raise ValueError("state history evidence is not bound to that contract revision")
            event_time = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
            proof_time = datetime.fromisoformat(proof.timestamp.replace("Z", "+00:00"))
            if proof_time > event_time:
                raise ValueError("state history cites evidence from the future")
            if proof.role == DeliveryRole(event.acting_role) and proof.author != event.actor:
                raise ValueError("state history actor does not match acting-role evidence author")
    validate_defect_history(item)
    defect_ids: set[str] = set()
    for defect in item.defects:
        if not isinstance(defect.severity, DefectSeverity) or not isinstance(defect.status, DefectStatus):
            raise ValueError("unknown defect severity or status")
        validate_defect(defect, item.work_item_id)
        if defect.defect_id in defect_ids:
            raise ValueError("duplicate defect ID")
        defect_ids.add(defect.defect_id)
        if not set(defect.evidence) <= evidence_ids:
            raise ValueError("defect references unknown evidence")
        for ref in (defect.developer_fix_ref, defect.qa_retest_ref):
            if ref and ref not in evidence_ids:
                raise ValueError("defect fix/retest references unknown evidence")
        by_id = {e.evidence_id: e for e in item.evidence}
        opening = next((event for event in item.defect_history
                        if event.defect_id == defect.defect_id and event.to_status == DefectStatus.OPEN.value), None)
        if opening is None or opening.evidence_ref not in defect.evidence:
            raise ValueError("defect record is missing its opening evidence link")
        if defect.developer_fix_ref:
            fix = by_id[defect.developer_fix_ref]
            if fix.evidence_type != EvidenceType.DEV_TEST_EVIDENCE or fix.status != EvidenceStatus.PASS:
                raise ValueError("defect fix reference must identify passing developer test evidence")
        if defect.qa_retest_ref:
            retest = by_id[defect.qa_retest_ref]
            expected = EvidenceStatus.FAIL if defect.status == DefectStatus.RETEST_FAILED else EvidenceStatus.PASS
            if (retest.evidence_type != EvidenceType.QA_RETEST_EVIDENCE
                    or retest.role != DeliveryRole.QA_ENGINEER or retest.status != expected):
                raise ValueError("defect retest reference must identify QA retest evidence")
            fix_time = datetime.fromisoformat(by_id[defect.developer_fix_ref].timestamp.replace("Z", "+00:00"))
            retest_time = datetime.fromisoformat(retest.timestamp.replace("Z", "+00:00"))
            if retest_time <= fix_time:
                raise ValueError("QA retest must occur after developer fix evidence")
        if defect.status == DefectStatus.CLOSED and (not defect.qa_retest_ref or not defect.developer_fix_ref):
            raise ValueError("closed defect requires developer fix and QA retest evidence")
    if (any(not isinstance(check, str) or not check.strip() for check in item.required_ci_checks)
            or len(item.required_ci_checks) != len(set(item.required_ci_checks))):
        raise ValueError("duplicate required CI check")
    if complete:
        fields_required = {"priority": item.priority, "business_goal": item.business_goal,
                           "current_behavior": item.current_behavior,
                           "expected_behavior": item.expected_behavior,
                           "architecture_impact": item.architecture_impact,
                           "rollback_plan": item.rollback_plan}
        for name, value in fields_required.items():
            _required_text(value, name)
        for name in ("in_scope", "out_of_scope", "acceptance_criteria", "safety_constraints",
                     "allowed_paths", "forbidden_paths", "expected_tests", "qa_attack_plan",
                     "uat_criteria", "release_gates"):
            if not getattr(item, name):
                raise ValueError(f"{name} must not be empty")
        if item.type not in {WorkItemType.EPIC} and not item.parent_epic.strip():
            raise ValueError("parent_epic is required for non-EPIC work")
        if item.type in {WorkItemType.STORY, WorkItemType.BUG, WorkItemType.TASK} and not item.parent_feature.strip():
            raise ValueError("parent_feature is required for STORY/BUG/TASK")


def work_item_to_dict(item: WorkItem) -> dict[str, Any]:
    from dataclasses import asdict
    from .evidence import _plain
    return _plain(asdict(item))


def work_item_from_dict(data: dict[str, Any]) -> WorkItem:
    if not isinstance(data, dict):
        raise ValueError("work item must be a JSON object")
    unknown = set(data) - WORK_ITEM_FIELDS
    missing = WORK_ITEM_FIELDS - set(data)
    if unknown or missing:
        raise ValueError(f"work item schema mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}")
    enum_fields = {"type": WorkItemType, "current_state": DeliveryState}
    converted: dict[str, Any] = dict(data)
    for key, enum_type in enum_fields.items():
        try:
            converted[key] = enum_type(converted[key])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"unknown {key}: {converted[key]!r}") from exc
    for raw in data["state_history"]:
        try:
            DeliveryRole(raw["acting_role"])
            DeliveryState(raw["from_state"]); DeliveryState(raw["to_state"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("unknown state/role in history") from exc
    converted["state_history"] = tuple(StateHistoryEntry(
        **{**h, "evidence_ids": tuple(h["evidence_ids"])}
    ) for h in data["state_history"])
    converted["defect_history"] = tuple(DefectHistoryEntry(**h) for h in data["defect_history"])
    evidence = []
    for raw in data["evidence"]:
        try:
            raw = dict(raw)
            raw["evidence_type"] = EvidenceType(raw["evidence_type"])
            raw["role"] = DeliveryRole(raw["role"])
            raw["status"] = EvidenceStatus(raw["status"])
            raw["references"] = tuple(raw["references"])
            raw["check_results"] = tuple(tuple(x) for x in raw["check_results"])
            evidence.append(Evidence(**raw))
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("malformed or unknown evidence record") from exc
    converted["evidence"] = tuple(evidence)
    defects = []
    for raw in data["defects"]:
        try:
            from .models import DefectSeverity, DefectStatus
            raw = dict(raw)
            raw["severity"] = DefectSeverity(raw["severity"])
            raw["status"] = DefectStatus(raw["status"])
            for key in ("reproduction_steps", "evidence"):
                raw[key] = tuple(raw[key])
            defects.append(Defect(**raw))
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("malformed or unknown defect record") from exc
    converted["defects"] = tuple(defects)
    for name in ("in_scope", "out_of_scope", "dependencies", "acceptance_criteria", "safety_constraints",
                 "allowed_paths", "forbidden_paths", "expected_tests", "qa_attack_plan", "uat_criteria",
                 "release_gates", "evidence_refs", "required_ci_checks"):
        converted[name] = tuple(converted[name])
    item = WorkItem(**converted)
    validate_work_item(item)
    return item
