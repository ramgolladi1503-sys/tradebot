#!/usr/bin/env python3
"""Safe S003 launcher with deterministic controller-owned review transport identity.

The v1 cycle remains the authority for S003 state transitions. This wrapper fixes
only orchestration defects: stderr/stdout separation, controller-owned envelope
identity, transport-only retries, and exclusion of invalid artifacts from
candidate-repair findings.
"""
from __future__ import annotations

import copy
import json
import subprocess
import time
from pathlib import Path

import mros_autonomous_cycle as cycle
from mros_review_transport import canonicalize_artifact, invalid_roles, member_for_output

_ORIG_EXACT_POPULATION = cycle.exact_population
_ORIG_BLOCKING_FINDINGS = cycle.blocking_findings
_ORIG_RECORD_AGGREGATE = cycle.record_aggregate


def safe_run(cwd, *args: str, timeout: int = 1200, check: bool = True):
    p = subprocess.run(
        list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout, check=False,
    )
    if check and p.returncode != 0:
        detail = (p.stderr or p.stdout or "")[-4000:]
        raise cycle.CycleError(f"COMMAND_FAILED:{' '.join(args)}:{detail}")
    return p


def exact_population_v2(q: Path, manifest: dict):
    """Validate raw files/receipts, then overlay frozen controller-owned identity."""
    complete, payloads, receipts = _ORIG_EXACT_POPULATION(q, manifest)
    if not complete:
        return complete, payloads, receipts
    canonical = []
    for output_path, artifact in payloads:
        member = member_for_output(manifest, output_path, q)
        if not member:
            return False, [], {}
        receipt_path = member.get("receipt_path")
        if not isinstance(receipt_path, str):
            return False, [], {}
        receipt_file = q / receipt_path
        try:
            receipt = cycle.read_json(receipt_file)
        except Exception:
            return False, [], {}
        canonical.append((
            member["output_path"],
            canonicalize_artifact(
                artifact,
                member=member,
                manifest=manifest,
                receipt=receipt,
                queue_repo=q,
            ),
        ))
    return True, canonical, receipts


def blocking_findings_v2(aggregate: dict, kind: str):
    """Only valid artifacts may create implementation/audit repair work."""
    out = []
    plural = "reviews" if kind == "review" else "audits"
    for item in aggregate.get(plural, []):
        if isinstance(item, dict):
            out.extend(
                f for f in item.get("findings", [])
                if isinstance(f, dict) and f.get("severity") in {"CRITICAL", "MAJOR", "UNKNOWN"}
            )
    seen = set()
    deduped = []
    for finding in out:
        key = (finding.get("requirement"), finding.get("evidence"), finding.get("severity"))
        if key not in seen:
            seen.add(key)
            deduped.append(finding)
    return deduped


def _transport_invalid_old(old: dict, kind: str) -> bool:
    valid_key = "valid_reviews" if kind == "review" else "valid_audits"
    return (
        str(old.get("decision")) in {
            "INCOMPLETE_OR_UNDECLARED_REVIEW_POPULATION",
            "INCOMPLETE_OR_UNDECLARED_AUDIT_POPULATION",
        }
        and int(old.get(valid_key) or 0) == 0
        and bool(old.get("invalid"))
    )


def record_aggregate_v2(auth: Path, aggregate: dict, kind: str, round_id: str, candidate: str):
    """Supersede the one historical transport-invalid aggregate without losing evidence."""
    ap = cycle.aggregate_path(kind, round_id)
    cp = cycle.contract_path(kind, round_id)
    current = auth / ap
    if current.is_file():
        old = cycle.read_json(current)
        if _transport_invalid_old(old, kind) and not aggregate.get("invalid"):
            archive = ap.with_name(ap.stem + "_TRANSPORT_INVALID_ARCHIVE.json")
            changed = []
            archive_file = auth / archive
            if not archive_file.is_file():
                archive_file.write_text(json.dumps(old, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                changed.append(archive)
            current.write_text(json.dumps(aggregate, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            changed.append(ap)
            decision = str(aggregate.get("decision"))
            state = (auth / cycle.STATE).read_text(encoding="utf-8")
            if decision not in cycle.PASS:
                contract = {
                    "schema_version": "mros-repair-contract-v2",
                    "sprint": "S003",
                    "failed_head": candidate,
                    "source_kind": kind,
                    "source_round": round_id,
                    "aggregate_decision": decision,
                    "blocking_findings": blocking_findings_v2(aggregate, kind),
                    "invalid_artifacts": [],
                    "superseded_transport_invalid_artifacts": old.get("invalid", []),
                    "root_cause_instruction": "Repair only findings from valid independent artifacts. Transport-invalid artifacts are historical evidence and cannot contribute implementation findings.",
                    "repair_scope": {
                        "allowed": ["scripts/mros/", "tests/mros/", "research/review_board/", "research/audit_board/"],
                        "forbidden": ["research/program/", "runtime/strategy/risk/execution/broker code", "weaken fixtures or acceptance criteria", "begin M9", "create runtime authority"],
                    },
                    "runtime_authority": "NONE",
                    "m9_status": "NOT_STARTED",
                }
                (auth / cp).write_text(json.dumps(contract, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                changed.append(cp)
                state = cycle.set_top(state, "active_sprint_status", f"BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_REPAIR_REQUIRED")
            else:
                state = cycle.set_top(state, "active_sprint_status", f"BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_PASS")
            (auth / cycle.STATE).write_text(state, encoding="utf-8")
            changed.append(cycle.STATE)
            cycle.commit_authority(
                auth,
                changed,
                f"mros(S003): supersede {round_id} transport-invalid {kind} aggregate with controller-normalized evidence [skip ci]",
            )
            return decision, (cp if decision not in cycle.PASS else None)
    return _ORIG_RECORD_AGGREGATE(auth, aggregate, kind, round_id, candidate)


def _retry_invalid_roles(q: Path, manifest: dict, roles: list[str], round_id: str, candidate: str):
    """Retry only roles that remain invalid after controller normalization."""
    changed = []
    members = {
        str(m.get("execution_role_id")): m
        for m in manifest.get("members", [])
        if isinstance(m, dict) and isinstance(m.get("execution_role_id"), str)
    }
    for role in roles:
        member = members.get(role)
        if not member:
            raise cycle.CycleError(f"TRANSPORT_RETRY_MEMBER_MISSING:{role}")
        output = Path(str(member["output_path"]))
        receipt = Path(str(member["receipt_path"]))
        request = cycle.ROOT / "requests" / output.name
        request_file = q / request
        if not request_file.is_file():
            raise cycle.CycleError(f"TRANSPORT_RETRY_REQUEST_MISSING:{role}")
        req = cycle.read_json(request_file)
        retry = int(req.get("transport_retry") or 0) + 1
        if retry > 3:
            raise cycle.CycleError(f"TRANSPORT_RETRY_LIMIT_EXCEEDED:{round_id}:{role}")
        req["transport_retry"] = retry
        req["request_id"] = f"S003-{round_id}-{role}-{candidate[:8]}-transport-retry{retry}"
        req["controller_transport"] = {
            "candidate_head": candidate,
            "sprint": manifest.get("sprint"),
            "round": manifest.get("round"),
            "execution_role_id": role,
            "packet_path": member.get("packet_path"),
            "output_path": member.get("output_path"),
            "receipt_path": member.get("receipt_path"),
        }
        request_file.write_text(json.dumps(req, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        changed.append(request)
        for rel in (output, receipt):
            path = q / rel
            if path.exists():
                path.unlink()
                changed.append(rel)
    cycle.queue_commit(q, changed, f"mros(S003): retry transport-invalid {round_id} roles {','.join(roles)} [skip ci]")


def process_review_v2(auth: Path, q: Path, state_root: Path, row):
    n, mp, manifest = row
    round_id = f"R{n:03d}"
    candidate = manifest.get("candidate_head")
    tier = str(manifest.get("assurance_tier") or "FAST")
    if not isinstance(candidate, str):
        raise cycle.CycleError("LATEST_REVIEW_CANDIDATE_INVALID")
    complete, payloads, receipts = exact_population_v2(q, manifest)
    if not complete:
        return {"action": "WAIT_REVIEW", "round": round_id, "candidate": candidate, "tier": tier}
    aggregate = cycle.load_mod(auth, "aggregate_reviews").aggregate_payloads(
        payloads, candidate_head=candidate, receipts=receipts, manifest=manifest
    )
    aggregate.update({
        "review_round": round_id,
        "population_manifest": str(mp.relative_to(q)),
        "assurance_tier": tier,
        "runtime_authority": "NONE",
    })
    if aggregate.get("invalid"):
        roles = invalid_roles(aggregate, manifest, q)
        if not roles:
            raise cycle.CycleError(f"TRANSPORT_INVALID_ROLES_UNRESOLVED:{round_id}")
        _retry_invalid_roles(q, manifest, roles, round_id, candidate)
        return {"action": "REVIEW_TRANSPORT_RETRY_QUEUED", "round": round_id, "candidate": candidate, "roles": roles}
    decision, cp = record_aggregate_v2(auth, aggregate, "review", round_id, candidate)
    cycle.sync(auth, q)
    if decision not in cycle.PASS:
        prior = cycle.repair_evidence_for_failed(auth, candidate)
        if prior:
            new = cycle.git(auth, "rev-parse", f"origin/{cycle.AUTH}").stdout.strip()
            cs, _ = cycle.calibration_status(q, new)
            if cs == "MISSING":
                cycle.queue_calibration(q, new)
            return {"action": "REPAIR_ALREADY_PUBLISHED", "round": round_id, "new_candidate": new, "calibration": cs}
        if cp is None:
            raise cycle.CycleError("REPAIR_CONTRACT_MISSING")
        repair = cycle.run_repair(auth, state_root, cp)
        cycle.sync(auth, q)
        cycle.queue_calibration(q, repair["candidate_head"])
        return {"action": "REPAIR_AND_CALIBRATE", "round": round_id, "decision": decision, "new_candidate": repair["candidate_head"], "generation": repair["generation"]}
    if tier != "FULL":
        fr = cycle.queue_review(q, candidate, full=True)
        return {"action": "FINAL_FULL_REVIEW_QUEUED", "from_round": round_id, "round": fr, "candidate": candidate}
    cycle.queue_audit(q, auth, candidate, round_id, aggregate, full=True)
    return {"action": "FINAL_FULL_AUDIT_QUEUED", "round": round_id, "candidate": candidate, "decision": decision}


def main() -> int:
    cycle.run = safe_run
    cycle.exact_population = exact_population_v2
    cycle.blocking_findings = blocking_findings_v2
    cycle.record_aggregate = record_aggregate_v2
    cycle.process_review = process_review_v2
    result = cycle.main()
    return 0 if result is None else int(result)


if __name__ == "__main__":
    raise SystemExit(main())
