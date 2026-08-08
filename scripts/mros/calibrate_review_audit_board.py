#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mros"
CANDIDATE = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
ROUND = "R001"


def finding(fid: str, severity: str) -> dict:
    return {
        "finding_id": fid,
        "severity": severity,
        "requirement": "calibration requirement",
        "evidence": "controlled calibration evidence",
        "falsifier": "controlled opposite behavior",
        "recommended_repair_scope": "calibration only",
    }


def review(role: str, verdict: str = "PASS", findings: list[dict] | None = None, *, head: str | None = None, independent: bool = True) -> dict:
    fs = findings or []
    return {
        "artifact_id": f"CAL-{role}",
        "sprint": "S003",
        "round": ROUND,
        "candidate_head": head or CANDIDATE,
        "role": role,
        "independent_from_implementation": independent,
        "independent_from_review_aggregation": True,
        "verdict": verdict,
        "findings": fs,
        "critical": sum(x["severity"] == "CRITICAL" for x in fs),
        "major": sum(x["severity"] == "MAJOR" for x in fs),
        "minor": sum(x["severity"] == "MINOR" for x in fs),
        "unknown": sum(x["severity"] == "UNKNOWN" for x in fs),
        "evidence_refs": ["CALIBRATION-CONTROL"],
    }


def audit(role: str, verdict: str = "PASS", findings: list[dict] | None = None, *, head: str | None = None, independent: bool = True) -> dict:
    fs = findings or []
    return {
        "artifact_id": f"CAL-{role}",
        "sprint": "S003",
        "round": "A001",
        "candidate_head": head or CANDIDATE,
        "role": role,
        "independent_from_implementation": independent,
        "independent_from_review_aggregation": True,
        "verdict": verdict,
        "findings": fs,
        "critical": sum(x["severity"] == "CRITICAL" for x in fs),
        "major": sum(x["severity"] == "MAJOR" for x in fs),
        "minor": sum(x["severity"] == "MINOR" for x in fs),
        "unknown": sum(x["severity"] == "UNKNOWN" for x in fs),
        "evidence_refs": ["CALIBRATION-CONTROL"],
        "audited_review_round": ROUND,
        "audited_native_validation": "CALIBRATION-NATIVE",
        "audited_acceptance_criteria": ["CAL-AC-001"],
        "audit_scope": ["calibration machinery"],
    }


def run(cmd: list[str], *, expect: int | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if expect is not None and p.returncode != expect:
        raise AssertionError(f"unexpected exit {p.returncode} != {expect}: {' '.join(cmd)}\n{p.stdout}")
    return p.returncode, p.stdout


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def native_evidence(path: Path) -> None:
    write_json(path, {
        "repository": "ramgolladi1503-sys/tradebot",
        "branch": "research/mros-program-v1",
        "head": CANDIDATE,
        "validator": "scripts/mros/calibrate_review_audit_board.py",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "command": "python3 scripts/mros/calibrate_review_audit_board.py",
        "checks": 1,
        "passed": 1,
        "failed": 0,
        "exit_code": 0,
        "timestamp": "2026-08-08T00:00:00Z"
    })


def make_reviews(directory: Path, *, defect: str | None = None) -> None:
    roles = [
        "contract_compliance", "negative_control", "evidence_provenance", "authority_promotion", "causal_time",
        "denominator_search_integrity", "runtime_boundary", "qa_verification", "architecture_no_drift", "adversarial_red_team"
    ]
    for i, role in enumerate(roles, 1):
        fs: list[dict] = []
        verdict = "PASS"
        if i == 1 and defect == "major":
            fs = [finding("CAL-MAJOR", "MAJOR")]; verdict = "REPAIR_REQUIRED"
        elif i == 1 and defect == "critical":
            fs = [finding("CAL-CRITICAL", "CRITICAL")]; verdict = "FAIL"
        elif i == 1 and defect == "unknown":
            fs = [finding("CAL-UNKNOWN", "UNKNOWN")]; verdict = "UNKNOWN"
        elif i == 1 and defect == "minor":
            fs = [finding("CAL-MINOR", "MINOR")]; verdict = "PASS_WITH_MINOR_FINDINGS"
        write_json(directory / f"reviewer-{i:02d}.json", review(role, verdict, fs))


def make_audits(directory: Path, *, defect: str | None = None) -> None:
    roles = [
        "evidence_chain", "review_independence", "acceptance_criteria", "regression", "program_state",
        "scope_no_drift", "scientific_integrity", "reproducibility", "authority", "adversarial_acceptance"
    ]
    for i, role in enumerate(roles, 1):
        fs: list[dict] = []
        verdict = "PASS"
        if i == 1 and defect == "major":
            fs = [finding("CAL-A-MAJOR", "MAJOR")]; verdict = "REPAIR_REQUIRED"
        elif i == 1 and defect == "critical":
            fs = [finding("CAL-A-CRITICAL", "CRITICAL")]; verdict = "FAIL"
        elif i == 1 and defect == "unknown":
            fs = [finding("CAL-A-UNKNOWN", "UNKNOWN")]; verdict = "UNKNOWN"
        elif i == 1 and defect == "minor":
            fs = [finding("CAL-A-MINOR", "MINOR")]; verdict = "PASS_WITH_MINOR_FINDINGS"
        write_json(directory / f"auditor-{i:02d}.json", audit(role, verdict, fs))


def decision(output: str) -> str:
    return json.loads(output)["decision"]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))

    with tempfile.TemporaryDirectory(prefix="mros-board-cal-") as td:
        t = Path(td)
        native = t / "native.json"; native_evidence(native)

        # validator rejection controls
        rv = t / "review.json"
        write_json(rv, review("contract_compliance"))
        rc, _ = run([sys.executable, str(SCRIPTS / "validate_review.py"), str(rv), "--candidate-head", CANDIDATE])
        check("known_good_review_schema", rc == 0)
        write_json(rv, review("contract_compliance", head="0" * 40))
        rc, _ = run([sys.executable, str(SCRIPTS / "validate_review.py"), str(rv), "--candidate-head", CANDIDATE])
        check("stale_head_review_rejected", rc != 0)
        write_json(rv, review("contract_compliance", independent=False))
        rc, _ = run([sys.executable, str(SCRIPTS / "validate_review.py"), str(rv), "--candidate-head", CANDIDATE])
        check("fake_independent_review_rejected", rc != 0)
        malformed = review("contract_compliance"); malformed.pop("evidence_refs")
        write_json(rv, malformed)
        rc, _ = run([sys.executable, str(SCRIPTS / "validate_review.py"), str(rv), "--candidate-head", CANDIDATE])
        check("malformed_review_rejected", rc != 0)

        av = t / "audit.json"
        write_json(av, audit("evidence_chain"))
        rc, _ = run([sys.executable, str(SCRIPTS / "validate_audit.py"), str(av), "--candidate-head", CANDIDATE, "--review-round", ROUND])
        check("known_good_audit_schema", rc == 0)
        write_json(av, audit("evidence_chain", head="0" * 40))
        rc, _ = run([sys.executable, str(SCRIPTS / "validate_audit.py"), str(av), "--candidate-head", CANDIDATE, "--review-round", ROUND])
        check("stale_head_audit_rejected", rc != 0)
        write_json(av, audit("evidence_chain", independent=False))
        rc, _ = run([sys.executable, str(SCRIPTS / "validate_audit.py"), str(av), "--candidate-head", CANDIDATE, "--review-round", ROUND])
        check("fake_independent_audit_rejected", rc != 0)

        # review aggregation controls
        for defect, expected in [(None, "PASS"), ("minor", "PASS_WITH_MINOR_FINDINGS"), ("major", "REPAIR_REQUIRED"), ("unknown", "UNKNOWN"), ("critical", "REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION")]:
            d = t / f"reviews-{defect or 'good'}"; d.mkdir(); make_reviews(d, defect=defect)
            rc, out = run([sys.executable, str(SCRIPTS / "aggregate_reviews.py"), str(d), "--candidate-head", CANDIDATE, "--native-evidence", str(native)])
            check(f"review_aggregate_{defect or 'good'}", decision(out) == expected, out)
        d = t / "reviews-nine"; d.mkdir(); make_reviews(d)
        (d / "reviewer-10.json").unlink()
        _, out = run([sys.executable, str(SCRIPTS / "aggregate_reviews.py"), str(d), "--candidate-head", CANDIDATE, "--native-evidence", str(native)])
        check("review_quorum_10_enforced", decision(out) == "INSUFFICIENT_VALID_INDEPENDENT_REVIEWS", out)

        # canonical passing review aggregate for audit tests
        good_reviews = t / "reviews-pass"; good_reviews.mkdir(); make_reviews(good_reviews)
        _, review_out = run([sys.executable, str(SCRIPTS / "aggregate_reviews.py"), str(good_reviews), "--candidate-head", CANDIDATE, "--native-evidence", str(native)])
        review_aggregate = t / "review-aggregate.json"; review_aggregate.write_text(review_out, encoding="utf-8")
        for defect, expected in [(None, "PASS"), ("minor", "PASS_WITH_MINOR_FINDINGS"), ("major", "REPAIR_REQUIRED"), ("unknown", "UNKNOWN"), ("critical", "AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION")]:
            d = t / f"audits-{defect or 'good'}"; d.mkdir(); make_audits(d, defect=defect)
            rc, out = run([sys.executable, str(SCRIPTS / "aggregate_audits.py"), str(d), "--candidate-head", CANDIDATE, "--review-aggregate", str(review_aggregate), "--review-round", ROUND, "--native-evidence", str(native)])
            check(f"audit_aggregate_{defect or 'good'}", decision(out) == expected, out)
        d = t / "audits-nine"; d.mkdir(); make_audits(d)
        (d / "auditor-10.json").unlink()
        _, out = run([sys.executable, str(SCRIPTS / "aggregate_audits.py"), str(d), "--candidate-head", CANDIDATE, "--review-aggregate", str(review_aggregate), "--review-round", ROUND, "--native-evidence", str(native)])
        check("audit_quorum_10_enforced", decision(out) == "INSUFFICIENT_VALID_INDEPENDENT_AUDITS", out)

        # wrong native head must block both stages
        bad_native = t / "native-bad.json"; native_evidence(bad_native)
        n = json.loads(bad_native.read_text()); n["head"] = "0" * 40; write_json(bad_native, n)
        rc, out = run([sys.executable, str(SCRIPTS / "aggregate_reviews.py"), str(good_reviews), "--candidate-head", CANDIDATE, "--native-evidence", str(bad_native)])
        check("wrong_native_head_blocks_review", decision(out) == "REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED", out)

        # advancement must require review+audit and block M9 threshold S111+
        audit_pass = t / "audit-pass"; audit_pass.mkdir(); make_audits(audit_pass)
        _, audit_out = run([sys.executable, str(SCRIPTS / "aggregate_audits.py"), str(audit_pass), "--candidate-head", CANDIDATE, "--review-aggregate", str(review_aggregate), "--review-round", ROUND, "--native-evidence", str(native)])
        audit_aggregate = t / "audit-aggregate.json"; audit_aggregate.write_text(audit_out, encoding="utf-8")
        rc, out = run([sys.executable, str(SCRIPTS / "advance_program.py"), "--sprint", "S003", "--next-sprint", "S004", "--candidate-head", CANDIDATE, "--review-aggregate", str(review_aggregate), "--audit-aggregate", str(audit_aggregate), "--native-evidence", str(native), "--acceptance-criteria-satisfied"])
        check("legal_advancement_authorization", rc == 0 and '"advance": true' in out.lower(), out)
        rc, out = run([sys.executable, str(SCRIPTS / "advance_program.py"), "--sprint", "S110", "--next-sprint", "S111", "--candidate-head", CANDIDATE, "--review-aggregate", str(review_aggregate), "--audit-aggregate", str(audit_aggregate), "--native-evidence", str(native), "--acceptance-criteria-satisfied"])
        check("m9_hard_stop", rc != 0 and "M9_HARD_STOP" in out, out)
        check("runtime_authority_boundary", '"runtime_authority": "NONE"' in subprocess.run([sys.executable, str(SCRIPTS / "advance_program.py"), "--sprint", "S003", "--next-sprint", "S004", "--candidate-head", CANDIDATE, "--review-aggregate", str(review_aggregate), "--audit-aggregate", str(audit_aggregate), "--native-evidence", str(native), "--acceptance-criteria-satisfied"], cwd=ROOT, text=True, stdout=subprocess.PIPE).stdout)

    passed = sum(ok for _, ok, _ in checks)
    failed = len(checks) - passed
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} | {name}" + (f" | {detail.strip()}" if detail and not ok else ""))
    print(f"SUMMARY | checks={len(checks)} pass={passed} fail={failed}")
    print("S003_BOARD_DETERMINISTIC_CALIBRATION_PASS" if failed == 0 else "S003_BOARD_DETERMINISTIC_CALIBRATION_FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
