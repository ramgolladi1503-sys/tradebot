#!/usr/bin/env python3
"""Offline evidence verifier with report-only and staged enforcement modes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.delivery.evidence_standard import (
    GATES,
    validate_claim_registry,
    validate_source_registry,
    validate_subject_commit,
)
from core.delivery.validators import work_item_from_dict
from core.delivery.validators import validate_work_item, work_item_contract_hash
from core.delivery.orchestrator import DeliveryOrchestrator


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# Candidate policy may add governed paths, but it may not remove these minimum
# material roots. The trusted-base CI integration must still run this verifier
# from protected code before this invariant can resist a PR changing this file.
REQUIRED_MATERIAL_PATH_PREFIXES = frozenset({
    "core/", "strategies/", "research/", "scripts/research/", "config/", "data/",
    "governance/evidence/", "tests/governance/", "tools/verify_evidence.py",
    "docs/tradebot_delivery/", ".agents/workflows/tradebot-delivery-orchestrator.md",
    ".github/workflows/evidence-gates.yml",
})


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {value}")))


def _git(*args: str, cwd: Path = ROOT) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)
    if proc.returncode:
        raise ValueError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _candidate_file_matches(candidate_ref: str, rel_path: str, local_path: Path, *, cwd: Path) -> bool:
    """Require parsed report inputs to be byte-identical to the candidate tree."""
    proc = subprocess.run(["git", "cat-file", "blob", f"{candidate_ref}:{rel_path}"],
                          cwd=cwd, check=False, capture_output=True)
    return proc.returncode == 0 and proc.stdout == local_path.read_bytes()


def _loaded_delivery_module_paths(root: Path) -> list[str]:
    """Return loaded in-repository delivery code that can affect this report."""
    paths: set[str] = set()
    for module in tuple(sys.modules.values()):
        module_path = getattr(module, "__file__", None)
        if not module_path or not str(module_path).endswith(".py"):
            continue
        try:
            rel = Path(module_path).resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        if rel.startswith("core/delivery/"):
            paths.add(rel)
    return sorted(paths)


def changed_paths(base_ref: str, candidate_ref: str, *, cwd: Path = ROOT) -> list[str]:
    return sorted({line.strip() for line in _git(
        "diff", "--name-only", f"{base_ref}...{candidate_ref}", cwd=cwd
    ).splitlines() if line.strip()})


def _is_material(path: str, prefixes: list[str]) -> bool:
    clean = _normalize_repo_path(path)
    return clean is not None and any(_path_matches(clean, [prefix]) for prefix in prefixes)


def _normalize_repo_path(path: str) -> str | None:
    clean = path.replace("\\", "/")
    parts = clean.split("/")
    if clean.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        return None
    return clean


def _local_source_exists(root: Path, locator: str) -> bool:
    if locator.startswith(("https://", "http://")):
        return True  # URL is recorded, but this offline check does not authenticate it.
    rel = Path(locator)
    if rel.is_absolute() or ".." in rel.parts:
        return False
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return False
    return target.is_file() and not (root / rel).is_symlink()


def _path_matches(path: str, assessed_paths: list[str]) -> bool:
    normalized = _normalize_repo_path(path)
    if normalized is None:
        return False
    for raw_prefix in assessed_paths:
        prefix = _normalize_repo_path(raw_prefix.rstrip("/"))
        if prefix is None:
            continue
        if raw_prefix.endswith("/"):
            if normalized.startswith(prefix + "/"):
                return True
        elif normalized == prefix:
            return True
    return False


def _prefixes_overlap(first: str, second: str) -> bool:
    a = _normalize_repo_path(first.rstrip("/"))
    b = _normalize_repo_path(second.rstrip("/"))
    if a is None or b is None:
        return False
    a_dir, b_dir = first.endswith("/"), second.endswith("/")
    return (a == b or (a_dir and b.startswith(a + "/"))
            or (b_dir and a.startswith(b + "/")))


def build_report(*, base_ref: str, candidate_ref: str, candidate_sha: str,
                 root: Path = ROOT) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def finding(code: str, severity: str, detail: str, path: str = "") -> None:
        findings.append({"code": code, "severity": severity, "detail": detail, "path": path})

    if not SHA_RE.fullmatch(candidate_sha):
        finding("INVALID_CANDIDATE_SHA", "ERROR", "candidate SHA must be 40 lowercase hex characters")
    try:
        actual_sha = _git("rev-parse", candidate_ref, cwd=root)
        if actual_sha != candidate_sha:
            finding("CANDIDATE_SHA_MISMATCH", "ERROR",
                    f"candidate_ref resolves to {actual_sha}, supplied SHA is {candidate_sha}")
    except ValueError as exc:
        finding("CANDIDATE_REF_UNRESOLVED", "ERROR", str(exc))

    verifier_rel = "tools/verify_evidence.py"
    try:
        if not _candidate_file_matches(candidate_ref, verifier_rel, root / verifier_rel, cwd=root):
            finding("VERIFIER_NOT_AT_CANDIDATE", "ERROR",
                    "running verifier bytes do not match the candidate commit", verifier_rel)
    except OSError as exc:
        finding("VERIFIER_NOT_AT_CANDIDATE", "ERROR", str(exc), verifier_rel)
    for rel_path in _loaded_delivery_module_paths(root):
        try:
            if not _candidate_file_matches(candidate_ref, rel_path, root / rel_path, cwd=root):
                finding("VERIFIER_DEPENDENCY_NOT_AT_CANDIDATE", "ERROR",
                        "loaded delivery validation code does not match the candidate commit", rel_path)
        except OSError as exc:
            finding("VERIFIER_DEPENDENCY_NOT_AT_CANDIDATE", "ERROR", str(exc), rel_path)

    sources: dict[str, dict[str, Any]] = {}
    claims: dict[str, dict[str, Any]] = {}
    configured_enforcement_stage = "UNKNOWN"
    try:
        source_registry_path = "governance/evidence/SOURCE_REGISTRY.json"
        if not _candidate_file_matches(candidate_ref, source_registry_path, root / source_registry_path, cwd=root):
            finding("EVIDENCE_INPUT_NOT_AT_CANDIDATE", "ERROR",
                    "source registry bytes do not match the candidate commit", source_registry_path)
        source_registry = _read_json(root / source_registry_path)
        sources = validate_source_registry(source_registry)
        for source_id, source in sources.items():
            locator = source["locator"]
            if not _local_source_exists(root, locator):
                finding("SOURCE_LOCATOR_INVALID", "ERROR", f"source {source_id} has unsafe or missing locator {locator}")
            elif locator.startswith(("https://", "http://")):
                finding("EXTERNAL_SOURCE_NOT_AUTHENTICATED", "UNVERIFIED",
                        f"offline validation cannot authenticate external source {source_id}")
            elif not _candidate_file_matches(candidate_ref, locator, root / locator, cwd=root):
                finding("SOURCE_NOT_AT_CANDIDATE", "ERROR",
                        f"source {source_id} bytes do not match the candidate commit", locator)
    except (OSError, ValueError, TypeError) as exc:
        finding("SOURCE_REGISTRY_INVALID", "ERROR", str(exc))
    try:
        claims_path = "governance/evidence/CLAIM_REGISTRY.json"
        if not _candidate_file_matches(candidate_ref, claims_path, root / claims_path, cwd=root):
            finding("EVIDENCE_INPUT_NOT_AT_CANDIDATE", "ERROR",
                    "claim registry bytes do not match the candidate commit", claims_path)
        claims = validate_claim_registry(
            _read_json(root / claims_path), sources
        )
    except (OSError, ValueError, TypeError) as exc:
        finding("CLAIM_REGISTRY_INVALID", "ERROR", str(exc))
    try:
        matrix_path = "governance/evidence/VERIFICATION_MATRIX.json"
        if not _candidate_file_matches(candidate_ref, matrix_path, root / matrix_path, cwd=root):
            finding("EVIDENCE_INPUT_NOT_AT_CANDIDATE", "ERROR",
                    "verification matrix bytes do not match the candidate commit", matrix_path)
        matrix = _read_json(root / matrix_path)
        if not isinstance(matrix, dict) or matrix.get("schema_version") != 1:
            raise ValueError("verification matrix must have schema_version=1")
        if matrix.get("enforcement_stage") not in {"REPORT_ONLY", "BLOCK_NEW_MATERIAL"}:
            raise ValueError("verification matrix enforcement_stage is unsupported")
        expected_report_only = matrix["enforcement_stage"] == "REPORT_ONLY"
        if not isinstance(matrix.get("report_only"), bool) or matrix["report_only"] != expected_report_only:
            raise ValueError("verification matrix report_only must be true exactly when enforcement_stage is REPORT_ONLY")
        configured_enforcement_stage = matrix["enforcement_stage"]
        prefixes = matrix.get("material_path_prefixes")
        if not isinstance(prefixes, list) or not prefixes or any(not isinstance(x, str) or not x for x in prefixes):
            raise ValueError("verification matrix material_path_prefixes must be non-empty strings")
        missing_prefixes = REQUIRED_MATERIAL_PATH_PREFIXES - set(prefixes)
        if missing_prefixes:
            raise ValueError("verification matrix removes required material path prefixes: "
                             + ", ".join(sorted(missing_prefixes)))
        matrix_gates = matrix.get("gates")
        expected_gates = {
            name: {"evidence_type": evidence_type.value,
                   "allowed_roles": sorted(role.value for role in roles)}
            for name, (evidence_type, roles) in GATES.items()
        }
        normalized_gates = {
            name: {"evidence_type": data.get("evidence_type"),
                   "allowed_roles": sorted(data.get("allowed_roles", []))}
            for name, data in matrix_gates.items()
        } if isinstance(matrix_gates, dict) else None
        if normalized_gates != expected_gates:
            raise ValueError("verification matrix gates drift from the core.delivery evidence contract")
    except (OSError, ValueError, TypeError) as exc:
        prefixes = []
        finding("VERIFICATION_MATRIX_INVALID", "ERROR", str(exc))

    try:
        changed = changed_paths(base_ref, candidate_ref, cwd=root)
    except ValueError as exc:
        changed = []
        finding("DIFF_UNAVAILABLE", "ERROR", str(exc))
    material = [path for path in changed if _is_material(path, prefixes)]
    record_paths = sorted((root / "governance/evidence/work_items").glob("*.json"))
    records: list[tuple[str, Any, dict[str, Any]]] = []
    work_item_proofs: list[dict[str, Any]] = []
    changed_set = set(changed)
    for path in record_paths:
        rel = path.relative_to(root).as_posix()
        try:
            if not _candidate_file_matches(candidate_ref, rel, path, cwd=root):
                finding("EVIDENCE_INPUT_NOT_AT_CANDIDATE", "ERROR",
                        "work-item record bytes do not match the candidate commit", rel)
            payload = _read_json(path)
            item = work_item_from_dict(payload)
            standard = item.extensions.get("evidence_standard")
            if not isinstance(standard, dict):
                raise ValueError("work item is missing extensions.evidence_standard")
            record_is_current = rel in changed_set or standard.get("subject_commit_sha") == candidate_sha
            try:
                validate_subject_commit(standard, candidate_sha)
            except ValueError as exc:
                finding("SUBJECT_SHA_INVALID", "ERROR", str(exc), rel)
            if record_is_current:
                try:
                    validate_work_item(item, complete=True)
                except ValueError as exc:
                    finding("WORK_ITEM_DOR_INCOMPLETE", "ERROR",
                            f"current material work item fails Definition of Ready validation: {exc}", rel)
                if item.current_state.value not in {"RELEASE_READY", "PR_OPEN", "CI_GREEN"}:
                    finding("WORK_ITEM_LIFECYCLE_STATE_INCOMPLETE", "ERROR",
                            "current material work item must reach RELEASE_READY or a later pre-merge state; "
                            f"found {item.current_state.value}", rel)
                required_lifecycle_states = {
                    "REQUIREMENT_READY", "DESIGN_READY", "IN_DEVELOPMENT", "DEV_VERIFIED",
                    "QA_IN_PROGRESS", "QA_PASSED", "SENIOR_QA", "UAT", "PRODUCT_ACCEPTED",
                    "RELEASE_READY",
                }
                traversed_states = {entry.to_state for entry in item.state_history}
                missing_states = sorted(required_lifecycle_states - traversed_states)
                if missing_states:
                    finding("WORK_ITEM_LIFECYCLE_HISTORY_INCOMPLETE", "ERROR",
                            "current material work item state history does not traverse required lifecycle states: "
                            + ", ".join(missing_states), rel)
                try:
                    lifecycle_missing, lifecycle_invalid = DeliveryOrchestrator(item)._lifecycle_gaps(
                        include_ci=False
                    )
                    if lifecycle_missing:
                        finding("WORK_ITEM_LIFECYCLE_INCOMPLETE", "ERROR",
                                "current work item is missing required lifecycle evidence: "
                                + ", ".join(lifecycle_missing), rel)
                    if lifecycle_invalid:
                        finding("WORK_ITEM_ROLE_COVERAGE_INVALID", "ERROR",
                                "current work item has invalid role separation/evidence: "
                                + ", ".join(lifecycle_invalid), rel)
                except (ValueError, TypeError, AttributeError) as exc:
                    finding("WORK_ITEM_LIFECYCLE_INVALID", "ERROR",
                            f"cannot validate current work-item lifecycle evidence: {exc}", rel)
            records.append((rel, item, standard))
            work_item_proofs.append({
                "work_item_id": item.work_item_id,
                "record_path": rel,
                "record_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "work_item_contract_sha256": work_item_contract_hash(item),
                "evidence_hashes": [e.content_hash for e in item.evidence],
                "assessed_paths": standard.get("assessed_paths", []),
                "claim_assessments": [
                    {"claim_id": claim.get("claim_id"),
                     "declared_status": claim.get("status", "UNVERIFIED"),
                     "assessment_status": ("UNVERIFIED" if claim.get("status") == "VERIFIED"
                                           else claim.get("status", "UNVERIFIED")),
                     "verification_level": "STRUCTURAL_ONLY"}
                    for claim in standard.get("claims", [])
                ],
                "current_for_candidate": record_is_current,
                "candidate_sha": candidate_sha,
            })
            for claim_record in standard.get("claims", []):
                claim_id = claim_record.get("claim_id")
                registry_claim = claims.get(claim_id)
                if registry_claim is None:
                    finding("CLAIM_NOT_REGISTERED", "ERROR", f"work item references unknown claim {claim_id}", rel)
                    continue
                if claim_record.get("claim_kind") != registry_claim.get("claim_kind"):
                    finding("CLAIM_KIND_MISMATCH", "ERROR", f"claim {claim_id} kind conflicts with registry", rel)
                if claim_record.get("statement") != registry_claim.get("statement"):
                    finding("CLAIM_STATEMENT_MISMATCH", "ERROR", f"claim {claim_id} statement conflicts with registry", rel)
                if claim_record.get("status") != registry_claim.get("status"):
                    finding("CLAIM_STATUS_MISMATCH", "ERROR", f"claim {claim_id} status conflicts with registry", rel)
                registered_sources = set(registry_claim.get("source_ids", []))
                if not registered_sources <= set(claim_record.get("source_ids", [])):
                    finding("CLAIM_REQUIRED_SOURCE_MISSING", "ERROR",
                            f"claim {claim_id} omits a registered source", rel)
                assessed = standard.get("assessed_paths", [])
                if not any(_prefixes_overlap(scope, assessed_path)
                           for scope in registry_claim.get("scope_paths", [])
                           for assessed_path in assessed):
                    finding("CLAIM_SCOPE_MISMATCH", "ERROR",
                            f"claim {claim_id} assessed_paths do not cover its registered scope", rel)
                unknown_sources = set(claim_record.get("source_ids", [])) - sources.keys()
                if unknown_sources:
                    finding("CLAIM_SOURCE_UNKNOWN", "ERROR",
                            f"claim {claim_id} references unknown sources: {sorted(unknown_sources)}", rel)
                for assumption in claim_record.get("assumptions", []):
                    unknown_assumptions = set(assumption.get("source_ids", [])) - sources.keys()
                    if unknown_assumptions:
                        finding("ASSUMPTION_SOURCE_UNKNOWN", "ERROR",
                                f"claim {claim_id} assumption {assumption.get('assumption_id')} references unknown sources: {sorted(unknown_assumptions)}", rel)
                if claim_record.get("status") == "UNVERIFIED" and record_is_current:
                    finding("CLAIM_UNVERIFIED", "UNVERIFIED", f"claim {claim_id} remains unverified", rel)
                elif claim_record.get("status") == "VERIFIED":
                    finding("CLAIM_REQUIRES_HUMAN_REVIEW", "UNVERIFIED",
                            f"claim {claim_id} is only a declared status; artifact digests and reviewer identity are not authenticated", rel)
                elif claim_record.get("status") == "CONTRADICTED":
                    finding("CLAIM_CONTRADICTED", "ERROR", f"claim {claim_id} has contradictory evidence", rel)
                if claim_record.get("status") == "VERIFIED":
                    for source_id in claim_record.get("source_ids", []):
                        source = sources.get(source_id, {})
                        if source.get("status") != "VERIFIED" or source.get("locator", "").startswith(("http://", "https://")):
                            finding("VERIFIED_CLAIM_SOURCE_UNVERIFIED", "ERROR",
                                    f"claim {claim_id} depends on unverified or unauthenticated source {source_id}", rel)
                    g1_id = claim_record.get("gate_evidence", {}).get("G1_SOURCE")
                    g1 = next((e for e in item.evidence if e.evidence_id == g1_id), None)
                    if g1 is None or any(source_id not in g1.references
                                         for source_id in claim_record.get("source_ids", [])):
                        finding("G1_SOURCE_LINK_MISSING", "ERROR",
                                f"verified claim {claim_id} does not link every source in G1 evidence", rel)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            finding("WORK_ITEM_INVALID", "ERROR", str(exc), rel)

    for path in material:
        covering = []
        for row in records:
            rel, _, standard = row
            if not _path_matches(path, standard.get("assessed_paths", [])):
                continue
            if not (rel in changed_set or standard.get("subject_commit_sha") == candidate_sha):
                continue
            claim_scopes = [scope for claim_record in standard.get("claims", [])
                            for scope in claims.get(claim_record.get("claim_id"), {}).get("scope_paths", [])]
            if any(_path_matches(path, [scope]) for scope in claim_scopes):
                covering.append(row)
        if not covering:
            finding("MATERIAL_CHANGE_WITHOUT_RECORD", "BLOCKING",
                    "material change has no current work item evidence record covering this path", path)

    findings.sort(key=lambda row: (row["severity"], row["code"], row["path"], row["detail"]))
    report = {
        "schema_version": 1,
        "mode": "REPORT_ONLY",
        "enforcement_stage": configured_enforcement_stage,
        "candidate_sha": candidate_sha,
        "base_ref": base_ref,
        "candidate_ref": candidate_ref,
        "changed_path_count": len(changed),
        "material_path_count": len(material),
        "material_paths": material,
        "legacy_inventory": [
            {"claim_id": claim_id, "status": claim["status"],
             "scope_paths": claim["scope_paths"], "limitation": claim["limitation"]}
            for claim_id, claim in sorted(claims.items())
        ],
        "work_items": sorted(work_item_proofs, key=lambda row: row["work_item_id"]),
        "finding_count": len(findings),
        "findings": findings,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "authority": "evidence coverage validation only; not merge approval, research certification, or runtime readiness",
    }
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    report["report_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return report


def render_summary(report: dict[str, Any]) -> str:
    """Render evidence findings and enforcement outcome without implying readiness."""
    blocking_count = report.get("blocking_finding_count", 0)
    mode = report.get("mode", "REPORT_ONLY")
    label = {"ENFORCE_NEW_MATERIAL": "blocking enforcement",
             "STRICT": "strict enforcement"}.get(mode, "informational, report only")
    count_label = "Potential blocking findings" if mode == "REPORT_ONLY" else "Blocking findings"
    lines = [f"## Evidence coverage report ({label})", "",
             f"Candidate: `{report['candidate_sha']}`  ",
             f"Changed material paths: {report['material_path_count']}  ",
             f"Findings: {report['finding_count']} ({count_label.lower()}: {blocking_count})  ",
             "Passing this evidence check does not establish merge, research, or runtime readiness.", ""]
    findings = report.get("findings", [])
    if findings:
        lines.extend(["| Severity | Code | Path | Detail |", "|---|---|---|---|"])
        for row in findings:
            escape = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
            lines.append("| " + " | ".join(escape(row.get(key, ""))
                                               for key in ("severity", "code", "path", "detail")) + " |")
    else:
        lines.append("No findings were emitted for this candidate.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--candidate-ref", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path,
                        help="append a Markdown findings summary to this file")
    parser.add_argument("--mode", choices=("report-only", "enforce-new-material", "strict"), default="report-only")
    args = parser.parse_args(argv)
    report = build_report(base_ref=args.base_ref, candidate_ref=args.candidate_ref,
                          candidate_sha=args.candidate_sha)
    report["mode"] = {"report-only": "REPORT_ONLY",
                      "enforce-new-material": "ENFORCE_NEW_MATERIAL",
                      "strict": "STRICT"}[args.mode]
    if (args.mode == "enforce-new-material"
            and report.get("enforcement_stage") != "BLOCK_NEW_MATERIAL"):
        report["findings"].append({
            "severity": "ERROR",
            "code": "ENFORCEMENT_STAGE_MISMATCH",
            "path": "governance/evidence/VERIFICATION_MATRIX.json",
            "detail": "enforce-new-material mode requires candidate matrix enforcement_stage=BLOCK_NEW_MATERIAL",
        })
        report["finding_count"] = len(report["findings"])
    if args.mode == "strict":
        blocking = list(report["findings"])
    else:
        blocking = [finding for finding in report["findings"]
                    if finding["severity"] in {"ERROR", "BLOCKING"}]
    report["blocking_finding_count"] = len(blocking)
    report.pop("report_sha256", None)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    report["report_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    try:
        if args.output:
            args.output.write_text(serialized, encoding="utf-8")
        else:
            sys.stdout.write(serialized)
        if args.summary_output:
            with args.summary_output.open("a", encoding="utf-8") as summary_file:
                summary_file.write(render_summary(report))
    except OSError as exc:
        print(f"cannot write evidence report: {exc}", file=sys.stderr)
        return 2
    errors = [finding for finding in report["findings"] if finding["severity"] == "ERROR"]
    if args.mode == "strict" and report["findings"]:
        return 1
    if args.mode in {"enforce-new-material", "strict"} and blocking:
        return 1
    # Report-only suppresses all policy findings. Enforcement blocks structural
    # errors and uncovered material changes while preserving UNVERIFIED claims.
    print(f"Evidence report: candidate={report['candidate_sha']} findings={report['finding_count']} errors={len(errors)} mode={report['mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
