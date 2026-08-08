#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_FILES = (
    ROOT / "research/evidence/sprints/S002/S002_FIXTURES.json",
    ROOT / "research/evidence/sprints/S002/S002_FIXTURES_V5_ADDENDUM.json",
    ROOT / "research/evidence/sprints/S002/S002_FIXTURES_V6_GATE_BINDING.json",
)
SUPERSEDED_CASE_IDS = {"S002-C033", "S002-C035", "S002-C037", "S002-C065"}
REQUIRED_V6_REPLACEMENTS = {"S002-C067", "S002-C070", "S002-C071", "S002-C072"}

AUTH = ["Research / R", "Grade C", "Grade B", "Grade A", "Grade A+", "Rejected", "Unknown"]
LEGAL_PROMOTIONS = {
    "Research / R": {"Grade C"},
    "Grade C": {"Grade B"},
    "Grade B": {"Grade A"},
    "Grade A": {"Grade A+"},
    "Grade A+": set(),
    "Rejected": set(),
    "Unknown": set(),
}
STRONG_GRADE_REQUIREMENTS = {
    "Grade B": ("independent_attack_ref", "calibration_ref"),
    "Grade A": ("independent_attack_ref", "calibration_ref", "scientific_certification_ref", "economic_certification_ref"),
    "Grade A+": ("independent_attack_ref", "calibration_ref", "live_forward_evidence_ref", "monitoring_ref"),
}
PROMOTION_GATE_REQUIREMENTS = {
    "Grade C": ("REPRODUCIBILITY",),
    "Grade B": ("INDEPENDENT_ATTACK", "CALIBRATION"),
    "Grade A": ("SCIENTIFIC_CERTIFICATION", "ECONOMIC_CERTIFICATION"),
    "Grade A+": ("LIVE_FORWARD_EVIDENCE", "MONITORING"),
}
KNOWLEDGE_CLASSES = {"OBSERVED_FACT", "INFERENCE", "HYPOTHESIS", "SPECULATION"}
VERDICTS = {"SUPPORTED", "REJECTED", "UNKNOWN", "INSUFFICIENT_EVIDENCE"}
STATUSES = {"PASS", "FAIL", "UNKNOWN", "INVALID_INPUT", "BLOCKED", "REVIEW_REQUIRED"}
OBSOLETE = re.compile(r"^A[0-5]$")
EVIDENCE_REF = re.compile(r"^EVID-[A-Z0-9][A-Z0-9-]*$")
DENOMINATOR_CONTRACT_FIELDS = {
    "denominator_definition", "exclusion_rule_refs", "population_identity", "horizon",
    "regimes", "symbols", "dates_ref", "search_family_id",
}
DENOMINATOR_TRIGGER_KEYS = {
    "confirmatory", "experiment_contract_ref", "frozen_denominator_contract",
    "current_denominator_contract", "outcomes_inspected", "analysis_mode",
    "original_result_preserved", "new_analysis_identity", "post_hoc_rationale",
    "multiplicity_accounted", "reduced_authority",
}
CONSTITUTIONAL_KEYS = {
    "decision_timestamp", "input_availability_timestamps", "confirmatory", "experiment_contract_ref",
    "frozen_denominator_contract", "current_denominator_contract", "outcomes_inspected", "analysis_mode",
    "original_result_preserved", "new_analysis_identity", "post_hoc_rationale", "multiplicity_accounted",
    "reduced_authority", "runtime_context", "runtime_attempts_authority_promotion", "material_claim",
    "destroyers", "completion_claim", "completion_evidence_refs", "supersedes", "supersession_decision_ref",
    "declared_scope", "attempted_scope",
}

_UNSET = object()


def result(status, *, knowledge_class=_UNSET, can_promote=None, errors=None, rules=None):
    out = {"status": status, "error_codes": errors or [], "violated_rules": rules or []}
    if knowledge_class is not _UNSET:
        out["knowledge_class"] = knowledge_class
    if can_promote is not None:
        out["can_promote"] = can_promote
    return out


def nonempty_str(value):
    return isinstance(value, str) and bool(value.strip())


def nonempty_str_list(value):
    return isinstance(value, list) and bool(value) and all(nonempty_str(x) for x in value)


def is_bool(value):
    return type(value) is bool


def missing_required(inp, *fields):
    return [field for field in fields if field not in inp or inp[field] is None or inp[field] == "" or inp[field] == []]


def invalid_missing(*, knowledge_class=_UNSET, can_promote=None):
    return result("INVALID_INPUT", knowledge_class=knowledge_class, can_promote=can_promote,
                  errors=["MROS-S001-E001-MISSING_REQUIRED_FIELD"])


def invalid_schema(*, knowledge_class=_UNSET, can_promote=None):
    return result("INVALID_INPUT", knowledge_class=knowledge_class, can_promote=can_promote,
                  errors=["MROS-S002-E021-INVALID_SCHEMA_TYPE"])


def classify(inp):
    if not isinstance(inp, dict):
        return invalid_schema(knowledge_class=None)
    if missing_required(inp, "statement_text", "classification_signals"):
        return invalid_missing(knowledge_class=None)
    if not nonempty_str(inp["statement_text"]) or not nonempty_str_list(inp["classification_signals"]):
        return invalid_schema(knowledge_class=None)

    mapping = {
        "DIRECT_MEASUREMENT": "OBSERVED_FACT",
        "DERIVED_REASONING": "INFERENCE",
        "FALSIFIABLE_UNVERIFIED": "HYPOTHESIS",
        "UNSUPPORTED_CONJECTURE": "SPECULATION",
    }
    classes = {mapping[x] for x in set(inp["classification_signals"]) if x in mapping}
    if len(classes) != 1:
        return result("REVIEW_REQUIRED", knowledge_class=None,
                      errors=["MROS-S001-E002-AMBIGUOUS_KNOWLEDGE_CLASS"])

    knowledge_class = next(iter(classes))
    if knowledge_class in {"OBSERVED_FACT", "INFERENCE"} and not nonempty_str_list(inp.get("evidence_refs")):
        return result("INVALID_INPUT", knowledge_class=None,
                      errors=["MROS-S001-E015-EVIDENCE_PROVENANCE_MISSING"])
    return result("PASS", knowledge_class=knowledge_class)


def canonical_evidence_refs(value):
    if not isinstance(value, list) or not value:
        return None
    if any(not nonempty_str(x) or not EVIDENCE_REF.fullmatch(x.strip()) for x in value):
        return None
    canonical = [x.strip().upper() for x in value]
    if len(canonical) != len(set(canonical)):
        return None
    return canonical


def canonical_evidence_ref(value):
    if not nonempty_str(value):
        return None
    normalized = value.strip().upper()
    return normalized if EVIDENCE_REF.fullmatch(normalized) else None


def promotion(inp):
    if not isinstance(inp, dict):
        return invalid_schema(can_promote=False)
    if missing_required(inp, "authority_current", "authority_requested"):
        return invalid_missing(can_promote=False)

    cur, req = inp["authority_current"], inp["authority_requested"]
    if not isinstance(cur, str) or not isinstance(req, str):
        return invalid_schema(can_promote=False)
    if OBSOLETE.match(cur) or OBSOLETE.match(req):
        return result("INVALID_INPUT", can_promote=False,
                      errors=["MROS-S001-E017-OBSOLETE_AUTHORITY_SCALE"])
    if cur not in AUTH or req not in AUTH:
        return result("INVALID_INPUT", can_promote=False,
                      errors=["MROS-S001-E003-INVALID_AUTHORITY_GRADE"])

    for flag in ("requires_independent_attack", "requires_calibration", "evidence_provenance_complete"):
        if flag in inp and not is_bool(inp[flag]):
            return invalid_schema(can_promote=False)

    if "new_evidence_refs" not in inp:
        return result("FAIL", can_promote=False,
                      errors=["MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION"], rules=["RC-002"])
    new_refs = canonical_evidence_refs(inp["new_evidence_refs"])
    if new_refs is None:
        if inp["new_evidence_refs"] == []:
            return result("FAIL", can_promote=False,
                          errors=["MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION"], rules=["RC-002"])
        return invalid_schema(can_promote=False)

    if req not in LEGAL_PROMOTIONS.get(cur, set()):
        return result("FAIL", can_promote=False,
                      errors=["MROS-S001-E004-AUTHORITY_STAGE_SKIP"], rules=["RC-002"])

    if inp.get("requires_independent_attack") is True and not nonempty_str(inp.get("independent_attack_ref")):
        return result("REVIEW_REQUIRED", can_promote=False,
                      errors=["MROS-S001-E006-INDEPENDENT_ATTACK_REQUIRED"], rules=["RC-004"])
    if inp.get("requires_calibration") is True and not nonempty_str(inp.get("calibration_ref")):
        return result("BLOCKED", can_promote=False,
                      errors=["MROS-S001-E010-CALIBRATION_REQUIRED"], rules=["RC-005"])

    required_for_grade = STRONG_GRADE_REQUIREMENTS.get(req, ())
    if "independent_attack_ref" in required_for_grade and not nonempty_str(inp.get("independent_attack_ref")):
        return result("REVIEW_REQUIRED", can_promote=False,
                      errors=["MROS-S001-E006-INDEPENDENT_ATTACK_REQUIRED"], rules=["RC-004"])
    if "calibration_ref" in required_for_grade and not nonempty_str(inp.get("calibration_ref")):
        return result("BLOCKED", can_promote=False,
                      errors=["MROS-S001-E010-CALIBRATION_REQUIRED"], rules=["RC-005"])
    other_required = tuple(f for f in required_for_grade if f not in {"independent_attack_ref", "calibration_ref"})
    if other_required and any(not nonempty_str(inp.get(field)) for field in other_required):
        return invalid_missing(can_promote=False)

    if "evidence_refs" not in inp:
        return result("INVALID_INPUT", can_promote=False,
                      errors=["MROS-S001-E015-EVIDENCE_PROVENANCE_MISSING"])
    if inp["evidence_refs"] == []:
        if cur != "Research / R":
            return result("INVALID_INPUT", can_promote=False,
                          errors=["MROS-S001-E015-EVIDENCE_PROVENANCE_MISSING"])
        old_refs = []
    else:
        old_refs = canonical_evidence_refs(inp["evidence_refs"])
        if old_refs is None:
            return invalid_schema(can_promote=False)
    if inp.get("evidence_provenance_complete") is not True:
        return result("INVALID_INPUT", can_promote=False,
                      errors=["MROS-S001-E015-EVIDENCE_PROVENANCE_MISSING"])
    if set(old_refs).intersection(new_refs):
        return result("FAIL", can_promote=False,
                      errors=["MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION"], rules=["RC-002"])

    required_gates = PROMOTION_GATE_REQUIREMENTS.get(req, ())
    if "new_evidence_gate_bindings" not in inp:
        return invalid_missing(can_promote=False)
    bindings = inp["new_evidence_gate_bindings"]
    if not isinstance(bindings, dict):
        return invalid_schema(can_promote=False)
    if any(gate not in bindings for gate in required_gates):
        return invalid_missing(can_promote=False)
    allowed_gates = {g for gates in PROMOTION_GATE_REQUIREMENTS.values() for g in gates}
    if any(gate not in allowed_gates for gate in bindings):
        return invalid_schema(can_promote=False)
    for gate in required_gates:
        bound_ref = canonical_evidence_ref(bindings.get(gate))
        if bound_ref is None:
            return invalid_schema(can_promote=False)
        if bound_ref not in new_refs:
            return result("FAIL", can_promote=False,
                          errors=["MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION"], rules=["RC-002"])

    return result("PASS", can_promote=True)


def validate_enums(inp):
    if not isinstance(inp, dict):
        return invalid_schema()
    controlled = {"knowledge_class", "verdict", "status"}
    if not set(inp).intersection(controlled):
        return invalid_missing()
    if "knowledge_class" in inp and inp["knowledge_class"] not in KNOWLEDGE_CLASSES:
        return result("INVALID_INPUT", errors=["MROS-S002-E018-INVALID_KNOWLEDGE_CLASS_ENUM"])
    if "verdict" in inp and inp["verdict"] not in VERDICTS:
        return result("INVALID_INPUT", errors=["MROS-S002-E019-INVALID_VERDICT_ENUM"])
    if "status" in inp and inp["status"] not in STATUSES:
        return result("INVALID_INPUT", errors=["MROS-S002-E020-INVALID_STATUS_ENUM"])
    return result("PASS")


def denominator_contract_valid(contract):
    if not isinstance(contract, dict) or not DENOMINATOR_CONTRACT_FIELDS.issubset(contract):
        return False
    if not all(nonempty_str(contract[k]) for k in ("denominator_definition", "population_identity", "horizon", "dates_ref", "search_family_id")):
        return False
    if not isinstance(contract["exclusion_rule_refs"], list) or any(not nonempty_str(x) for x in contract["exclusion_rule_refs"]):
        return False
    if not nonempty_str_list(contract["regimes"]) or not nonempty_str_list(contract["symbols"]):
        return False
    return True


def validate_denominator_semantics(inp):
    if not set(inp).intersection(DENOMINATOR_TRIGGER_KEYS):
        return None

    confirmatory = inp.get("confirmatory", _UNSET)
    mode = inp.get("analysis_mode", _UNSET)
    if confirmatory is not _UNSET and not is_bool(confirmatory):
        return invalid_schema()
    if mode is not _UNSET and mode != "EXPLORATORY_POST_HOC":
        return invalid_schema()
    if confirmatory is True and mode is not _UNSET:
        return invalid_schema()
    if confirmatory is not True and mode != "EXPLORATORY_POST_HOC":
        return invalid_missing()

    required = ("experiment_contract_ref", "frozen_denominator_contract", "current_denominator_contract", "outcomes_inspected")
    if missing_required(inp, *required):
        return invalid_missing()
    if not nonempty_str(inp["experiment_contract_ref"]) or not is_bool(inp["outcomes_inspected"]):
        return invalid_schema()

    frozen, current = inp["frozen_denominator_contract"], inp["current_denominator_contract"]
    if not denominator_contract_valid(frozen) or not denominator_contract_valid(current):
        return invalid_schema()

    changed = frozen != current
    outcomes_inspected = inp["outcomes_inspected"]
    if confirmatory is True:
        if changed and outcomes_inspected:
            return result("FAIL", errors=["MROS-S001-E008-DENOMINATOR_CONTRACT_VIOLATION", "MROS-S001-E009-POST_HOC_EXCLUSION_DETECTED"], rules=["RC-009"])
        return None

    if mode == "EXPLORATORY_POST_HOC" and outcomes_inspected is not True:
        return invalid_schema()
    if mode == "EXPLORATORY_POST_HOC" and changed:
        if any(not nonempty_str(inp.get(f)) for f in ("new_analysis_identity", "post_hoc_rationale")):
            return result("FAIL", errors=["MROS-S001-E008-DENOMINATOR_CONTRACT_VIOLATION", "MROS-S001-E009-POST_HOC_EXCLUSION_DETECTED"], rules=["RC-009"])
        for flag in ("original_result_preserved", "multiplicity_accounted", "reduced_authority"):
            if flag in inp and not is_bool(inp[flag]):
                return invalid_schema()
        if not all(inp.get(flag) is True for flag in ("original_result_preserved", "multiplicity_accounted", "reduced_authority")):
            return result("FAIL", errors=["MROS-S001-E008-DENOMINATOR_CONTRACT_VIOLATION", "MROS-S001-E009-POST_HOC_EXCLUSION_DETECTED"], rules=["RC-009"])
    return None


def parse_timestamp(value):
    if not nonempty_str(value):
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def constitutional(inp):
    if not isinstance(inp, dict) or not set(inp).intersection(CONSTITUTIONAL_KEYS):
        return invalid_missing()

    dependencies = (
        ("destroyers", "material_claim"),
        ("completion_evidence_refs", "completion_claim"),
        ("supersession_decision_ref", "supersedes"),
    )
    for dependent, primary in dependencies:
        if dependent in inp and primary not in inp:
            return invalid_missing()

    if ("decision_timestamp" in inp) != ("input_availability_timestamps" in inp):
        return invalid_missing()
    if "decision_timestamp" in inp:
        if not nonempty_str(inp["decision_timestamp"]) or not nonempty_str_list(inp["input_availability_timestamps"]):
            return invalid_missing()
        try:
            decision = parse_timestamp(inp["decision_timestamp"])
            inputs = [parse_timestamp(x) for x in inp["input_availability_timestamps"]]
        except (TypeError, ValueError, OverflowError):
            return invalid_schema()
        if any(x > decision for x in inputs):
            return result("FAIL", errors=["MROS-S001-E007-CAUSAL_TIME_VIOLATION"], rules=["RC-008"])

    denominator_result = validate_denominator_semantics(inp)
    if denominator_result is not None:
        return denominator_result

    if ("runtime_context" in inp) != ("runtime_attempts_authority_promotion" in inp):
        return invalid_missing()
    if "runtime_context" in inp:
        if not is_bool(inp["runtime_context"]) or not is_bool(inp["runtime_attempts_authority_promotion"]):
            return invalid_schema()
        if inp["runtime_attempts_authority_promotion"] is True:
            if inp["runtime_context"] is True:
                return result("FAIL", errors=["MROS-S001-E011-RUNTIME_AUTHORITY_VIOLATION"], rules=["RC-010"])
            return invalid_schema()

    if "material_claim" in inp:
        if not is_bool(inp["material_claim"]):
            return invalid_schema()
        if inp["material_claim"] is True and not nonempty_str_list(inp.get("destroyers")):
            return result("FAIL", errors=["MROS-S001-E013-NON_FALSIFIABLE_CLAIM"], rules=["RC-007"])

    if "completion_claim" in inp:
        if not is_bool(inp["completion_claim"]):
            return invalid_schema()
        if inp["completion_claim"] is True and not nonempty_str_list(inp.get("completion_evidence_refs")):
            return result("FAIL", errors=["MROS-S001-E016-UNSUPPORTED_COMPLETION_CLAIM"])

    if "supersedes" in inp:
        if not nonempty_str(inp["supersedes"]):
            return invalid_missing()
        if not nonempty_str(inp.get("supersession_decision_ref")):
            return result("FAIL", errors=["MROS-S001-E012-UNRECORDED_SUPERSESSION"], rules=["RC-006"])

    if ("declared_scope" in inp) != ("attempted_scope" in inp):
        return invalid_missing()
    if "declared_scope" in inp:
        if not nonempty_str(inp["declared_scope"]) or not nonempty_str(inp["attempted_scope"]):
            return invalid_missing()
        if inp["attempted_scope"] != inp["declared_scope"]:
            return result("FAIL", errors=["MROS-S001-E014-SCOPE_DRIFT"], rules=["RC-001"])

    return result("PASS")


def evaluate(case):
    if not isinstance(case, dict):
        return invalid_schema()
    op = case.get("operation")
    inp = case.get("input", {})
    if not nonempty_str(op):
        return invalid_missing()
    if op == "CLASSIFY_STATEMENT":
        return classify(inp)
    if op == "VALIDATE_PROMOTION":
        return promotion(inp)
    if op == "VALIDATE_CONTRACT_ENUMS":
        return validate_enums(inp)
    if op == "VALIDATE_CONSTITUTIONAL_ACTION":
        return constitutional(inp)
    return invalid_missing()


def load_cases():
    cases = []
    for fixture_path in FIXTURE_FILES:
        try:
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FIXTURE_LOAD_FAIL | {fixture_path.name} | {exc}")
            raise SystemExit(2)
        if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
            print(f"FIXTURE_SCHEMA_FAIL | {fixture_path.name}")
            raise SystemExit(2)
        cases.extend(case for case in payload["cases"] if case.get("case_id") not in SUPERSEDED_CASE_IDS)
    ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)):
        print("FIXTURE_DUPLICATE_CASE_ID")
        raise SystemExit(2)
    if not REQUIRED_V6_REPLACEMENTS.issubset(set(ids)):
        print("FIXTURE_V6_REPLACEMENT_MISSING")
        raise SystemExit(2)
    return cases


def main():
    cases = load_cases()
    total = passed = 0
    for case in cases:
        total += 1
        try:
            actual = evaluate(case)
        except Exception as exc:
            actual = result("INVALID_INPUT", errors=["MROS-S002-E021-INVALID_SCHEMA_TYPE"])
            print(f"CONTROLLED_EXCEPTION | {case.get('case_id','UNKNOWN')} | {type(exc).__name__}: {exc}")
        expected = case.get("expected")
        ok = actual == expected
        passed += int(ok)
        print(f"{'PASS' if ok else 'FAIL'} | {case.get('case_id','UNKNOWN')} | expected={json.dumps(expected, sort_keys=True)} | actual={json.dumps(actual, sort_keys=True)}")
    print(f"SUMMARY | checks={total} pass={passed} fail={total-passed}")
    if passed != total:
        raise SystemExit(1)
    print("S002_TARGETED_VALIDATION_PASS")


if __name__ == "__main__":
    main()
