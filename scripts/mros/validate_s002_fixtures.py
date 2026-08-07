#!/usr/bin/env python3
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "research/evidence/sprints/S002/S002_FIXTURES.json"
AUTH = ["Research / R", "Grade C", "Grade B", "Grade A", "Grade A+", "Rejected", "Unknown"]
STAGES = {"Research / R":0,"Grade C":1,"Grade B":2,"Grade A":3,"Grade A+":4}
KNOWLEDGE_CLASSES = {"OBSERVED_FACT", "INFERENCE", "HYPOTHESIS", "SPECULATION"}
VERDICTS = {"SUPPORTED", "REJECTED", "UNKNOWN", "INSUFFICIENT_EVIDENCE"}
STATUSES = {"PASS", "FAIL", "UNKNOWN", "INVALID_INPUT", "BLOCKED", "REVIEW_REQUIRED"}
OBSOLETE = re.compile(r"^A[0-5]$")

_UNSET = object()

def result(status, *, knowledge_class=_UNSET, can_promote=None, errors=None, rules=None):
    out={"status":status,"error_codes":errors or [],"violated_rules":rules or []}
    if knowledge_class is not _UNSET: out["knowledge_class"]=knowledge_class
    if can_promote is not None: out["can_promote"]=can_promote
    return out

def missing_required(inp, *fields):
    return [field for field in fields if field not in inp or inp[field] is None or inp[field] == ""]

def classify(inp):
    if missing_required(inp, "statement_text", "classification_signals"):
        return result("INVALID_INPUT",knowledge_class=None,errors=["MROS-S001-E001-MISSING_REQUIRED_FIELD"])
    sig=set(inp.get("classification_signals",[]))
    mapping={"DIRECT_MEASUREMENT":"OBSERVED_FACT","DERIVED_REASONING":"INFERENCE","FALSIFIABLE_UNVERIFIED":"HYPOTHESIS","UNSUPPORTED_CONJECTURE":"SPECULATION"}
    classes={mapping[x] for x in sig if x in mapping}
    if len(classes)!=1:
        return result("REVIEW_REQUIRED",knowledge_class=None,errors=["MROS-S001-E002-AMBIGUOUS_KNOWLEDGE_CLASS"])
    return result("PASS",knowledge_class=next(iter(classes)))

def promotion(inp):
    if missing_required(inp, "authority_current", "authority_requested"):
        return result("INVALID_INPUT",can_promote=False,errors=["MROS-S001-E001-MISSING_REQUIRED_FIELD"])
    cur, req=inp.get("authority_current"), inp.get("authority_requested")
    if (cur and OBSOLETE.match(cur)) or (req and OBSOLETE.match(req)):
        return result("INVALID_INPUT",can_promote=False,errors=["MROS-S001-E017-OBSOLETE_AUTHORITY_SCALE"])
    if cur not in AUTH or req not in AUTH:
        return result("INVALID_INPUT",can_promote=False,errors=["MROS-S001-E003-INVALID_AUTHORITY_GRADE"])
    if not inp.get("new_evidence_refs"):
        return result("FAIL",can_promote=False,errors=["MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION"],rules=["RC-002"])
    if inp.get("evidence_provenance_complete") is False:
        return result("INVALID_INPUT",can_promote=False,errors=["MROS-S001-E015-EVIDENCE_PROVENANCE_MISSING"])
    if inp.get("requires_independent_attack") and not inp.get("independent_attack_ref"):
        return result("REVIEW_REQUIRED",can_promote=False,errors=["MROS-S001-E006-INDEPENDENT_ATTACK_REQUIRED"],rules=["RC-004"])
    if inp.get("requires_calibration") and not inp.get("calibration_ref"):
        return result("BLOCKED",can_promote=False,errors=["MROS-S001-E010-CALIBRATION_REQUIRED"],rules=["RC-005"])
    if cur in STAGES and req in STAGES and STAGES[req] > STAGES[cur]+1:
        return result("FAIL",can_promote=False,errors=["MROS-S001-E004-AUTHORITY_STAGE_SKIP"],rules=["RC-002"])
    return result("PASS",can_promote=True)

def validate_enums(inp):
    if "knowledge_class" in inp and inp["knowledge_class"] not in KNOWLEDGE_CLASSES:
        return result("INVALID_INPUT",errors=["MROS-S002-E018-INVALID_KNOWLEDGE_CLASS_ENUM"])
    if "verdict" in inp and inp["verdict"] not in VERDICTS:
        return result("INVALID_INPUT",errors=["MROS-S002-E019-INVALID_VERDICT_ENUM"])
    if "status" in inp and inp["status"] not in STATUSES:
        return result("INVALID_INPUT",errors=["MROS-S002-E020-INVALID_STATUS_ENUM"])
    return result("PASS")

def constitutional(inp):
    if inp.get("decision_timestamp") and inp.get("input_availability_timestamps"):
        d=datetime.fromisoformat(inp["decision_timestamp"].replace("Z","+00:00"))
        if any(datetime.fromisoformat(x.replace("Z","+00:00"))>d for x in inp["input_availability_timestamps"]):
            return result("FAIL",errors=["MROS-S001-E007-CAUSAL_TIME_VIOLATION"],rules=["RC-008"])
    if inp.get("confirmatory") and inp.get("denominator_changed_after_outcome"):
        return result("FAIL",errors=["MROS-S001-E008-DENOMINATOR_CONTRACT_VIOLATION","MROS-S001-E009-POST_HOC_EXCLUSION_DETECTED"],rules=["RC-009"])
    if inp.get("runtime_context") and inp.get("runtime_attempts_authority_promotion"):
        return result("FAIL",errors=["MROS-S001-E011-RUNTIME_AUTHORITY_VIOLATION"],rules=["RC-010"])
    if inp.get("material_claim") and not inp.get("destroyers"):
        return result("FAIL",errors=["MROS-S001-E013-NON_FALSIFIABLE_CLAIM"],rules=["RC-007"])
    if inp.get("completion_claim") and not inp.get("completion_evidence_refs"):
        return result("FAIL",errors=["MROS-S001-E016-UNSUPPORTED_COMPLETION_CLAIM"])
    if inp.get("supersedes") and not inp.get("supersession_decision_ref"):
        return result("FAIL",errors=["MROS-S001-E012-UNRECORDED_SUPERSESSION"],rules=["RC-006"])
    if inp.get("declared_scope") and inp.get("attempted_scope") and inp["attempted_scope"] != inp["declared_scope"]:
        return result("FAIL",errors=["MROS-S001-E014-SCOPE_DRIFT"],rules=["RC-001"])
    return result("PASS")

def evaluate(case):
    op=case.get("operation"); inp=case.get("input",{})
    if not op:
        return result("INVALID_INPUT",errors=["MROS-S001-E001-MISSING_REQUIRED_FIELD"])
    if op=="CLASSIFY_STATEMENT": return classify(inp)
    if op=="VALIDATE_PROMOTION": return promotion(inp)
    if op=="VALIDATE_CONTRACT_ENUMS": return validate_enums(inp)
    if op=="VALIDATE_CONSTITUTIONAL_ACTION": return constitutional(inp)
    return result("INVALID_INPUT",errors=["MROS-S001-E001-MISSING_REQUIRED_FIELD"])

def main():
    payload=json.loads(FIXTURES.read_text())
    total=passed=0
    for case in payload["cases"]:
        total+=1; actual=evaluate(case); expected=case["expected"]
        ok=actual==expected
        passed+=int(ok)
        print(f"{'PASS' if ok else 'FAIL'} | {case['case_id']} | expected={json.dumps(expected,sort_keys=True)} | actual={json.dumps(actual,sort_keys=True)}")
    print(f"SUMMARY | checks={total} pass={passed} fail={total-passed}")
    if passed!=total: raise SystemExit(1)
    print("S002_TARGETED_VALIDATION_PASS")

if __name__=="__main__": main()
