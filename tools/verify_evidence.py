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
MATRIX_PATH = "governance/evidence/VERIFICATION_MATRIX.json"


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


def _safe_candidate_path(root: Path, rel_path: str) -> Path | None:
    """Resolve a candidate path without following candidate-controlled symlinks."""
    normalized = _normalize_repo_path(rel_path)
    if normalized is None:
        return None
    root_resolved = root.resolve()
    current = root
    for part in normalized.split("/"):
        current = current / part
        if current.is_symlink():
            return None
    resolved = current.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return None
    return current


def _candidate_file_matches(candidate_ref: str, rel_path: str, local_path: Path, *, cwd: Path,
                            tree_root: Path | None = None) -> bool:
    """Require parsed report inputs to be byte-identical to the candidate tree."""
    safe_path = _safe_candidate_path(tree_root or cwd, rel_path)
    if safe_path is None or safe_path != local_path or not local_path.is_file():
        return False
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
    target = _safe_candidate_path(root, locator)
    return target is not None and target.is_file()


def _read_candidate_json(root: Path, rel_path: str) -> Any:
    path = _safe_candidate_path(root, rel_path)
    if path is None:
        raise ValueError(f"candidate input is unsafe or traverses a symlink: {rel_path}")
    return _read_json(path)


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


def _normalize_policy_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    is_directory = value.endswith("/")
    normalized = _normalize_repo_path(value.rstrip("/"))
    if normalized is None or any(character in normalized for character in "*?[]"):
        return None
    return normalized + ("/" if is_directory else "")


def _validate_prefixes(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list of repository paths")
    normalized: list[str] = []
    for raw in value:
        path = _normalize_policy_path(raw)
        if path is None:
            raise ValueError(f"{label} contains an invalid repository path: {raw!r}")
        if path in normalized:
            raise ValueError(f"{label} contains a duplicate repository path: {path}")
        normalized.append(path)
    return normalized


def _validate_trusted_exemptions(value: Any, protected_prefixes: list[str],
                                 material_prefixes: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("trusted_non_material_exemptions must be a list")
    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("trusted non-material exemptions must be objects")
        path = _normalize_policy_path(entry.get("path"))
        rationale = entry.get("rationale")
        owner = entry.get("owner")
        if path is None:
            raise ValueError("trusted non-material exemption path is invalid")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(f"trusted non-material exemption {path} requires a non-empty rationale")
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError(f"trusted non-material exemption {path} requires a non-empty owner")
        if path in seen:
            raise ValueError(f"duplicate trusted non-material exemption: {path}")
        if any(_prefixes_overlap(path, prefix)
               for prefix in [*protected_prefixes, *material_prefixes]):
            raise ValueError(f"trusted non-material exemption overlaps a protected material path: {path}")
        seen.add(path)
        validated.append({"path": path, "rationale": rationale.strip(), "owner": owner.strip()})
    return validated


def _trusted_material_policy(root: Path, candidate_matrix: dict[str, Any]
                             ) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """Load enforcement floors and exemptions only from the verifier checkout.

    In the trusted workflow, ``root`` is checked out at the protected PR base;
    ``candidate_matrix`` is read from the separately materialized PR tree.
    Candidate policy must preserve that base policy exactly.
    """
    trusted_matrix = _read_json(root / MATRIX_PATH)
    if not isinstance(trusted_matrix, dict):
        raise ValueError("verifier-base verification matrix must be an object")
    trusted_prefixes = _validate_prefixes(
        trusted_matrix.get("protected_material_path_prefixes"),
        "trusted protected_material_path_prefixes",
    )
    candidate_protected = _validate_prefixes(
        candidate_matrix.get("protected_material_path_prefixes"),
        "candidate protected_material_path_prefixes",
    )
    if candidate_protected != trusted_prefixes:
        raise ValueError("candidate protected_material_path_prefixes must exactly preserve verifier-base policy")

    material_prefixes = _validate_prefixes(
        candidate_matrix.get("material_path_prefixes"), "candidate material_path_prefixes"
    )
    missing = set(trusted_prefixes) - set(material_prefixes)
    if missing:
        raise ValueError("candidate matrix removes trusted protected material path prefixes: "
                         + ", ".join(sorted(missing)))

    trusted_exemptions = _validate_trusted_exemptions(
        trusted_matrix.get("trusted_non_material_exemptions"),
        trusted_prefixes, material_prefixes,
    )
    candidate_exemptions = candidate_matrix.get("trusted_non_material_exemptions")
    if candidate_exemptions != trusted_matrix.get("trusted_non_material_exemptions"):
        raise ValueError("candidate cannot add, remove, or change verifier-base non-material exemptions")
    return trusted_prefixes, material_prefixes, trusted_exemptions


def build_report(*, base_ref: str, candidate_ref: str, candidate_sha: str,
                 root: Path = ROOT, candidate_root: Path | None = None,
                 candidate_root_sha: str | None = None,
                 verifier_source_sha: str | None = None) -> dict[str, Any]:
    """Assess candidate-tree data with this checkout's verifier and delivery code.

    ``root`` is the verifier's git checkout. ``candidate_root`` is a separately
    materialized candidate tree whose files are read as data only; no Python
    from that tree is imported or executed. This supports protected-base
    verification without invoking Git checkout filters from candidate metadata.
    """
    candidate_tree = (candidate_root or root).resolve()
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

    if candidate_root is None:
        try:
            actual_candidate_root_sha = _git("rev-parse", "HEAD", cwd=candidate_tree)
        except ValueError as exc:
            actual_candidate_root_sha = ""
            finding("CANDIDATE_ROOT_UNRESOLVED", "ERROR", str(exc))
    else:
        actual_candidate_root_sha = candidate_root_sha or ""
        if candidate_root_sha is None:
            finding("CANDIDATE_ROOT_SHA_REQUIRED", "ERROR",
                    "a separate candidate root requires its verified source SHA")
        elif not SHA_RE.fullmatch(candidate_root_sha):
            finding("CANDIDATE_ROOT_SHA_INVALID", "ERROR",
                    "candidate root SHA must be 40 lowercase hex characters")
    if actual_candidate_root_sha and actual_candidate_root_sha != candidate_sha:
        finding("CANDIDATE_ROOT_SHA_MISMATCH", "ERROR",
                f"candidate root SHA is {actual_candidate_root_sha}, supplied candidate SHA is {candidate_sha}")
    if candidate_root is None and actual_candidate_root_sha and not SHA_RE.fullmatch(actual_candidate_root_sha):
        finding("CANDIDATE_ROOT_SHA_INVALID", "ERROR",
                "candidate root SHA must be 40 lowercase hex characters")
    if candidate_root is not None and verifier_source_sha is None:
        finding("VERIFIER_SOURCE_SHA_REQUIRED", "ERROR",
                "a separate candidate root requires an explicit verifier source SHA")

    try:
        actual_verifier_source_sha = _git("rev-parse", "HEAD", cwd=root)
        if verifier_source_sha is not None and not SHA_RE.fullmatch(verifier_source_sha):
            finding("VERIFIER_SOURCE_SHA_INVALID", "ERROR",
                    "verifier source SHA must be 40 lowercase hex characters")
        if verifier_source_sha is not None and actual_verifier_source_sha != verifier_source_sha:
            finding("VERIFIER_SOURCE_SHA_MISMATCH", "ERROR",
                    "verifier checkout HEAD does not match the declared verifier source SHA")
    except ValueError as exc:
        actual_verifier_source_sha = ""
        finding("VERIFIER_SOURCE_UNRESOLVED", "ERROR", str(exc))

    verifier_rel = "tools/verify_evidence.py"
    # Candidate-mode diagnostics compare executable source with candidate
    # bytes. Trusted-base mode deliberately runs protected code against
    # candidate data and never loads candidate Python modules.
    if candidate_root is None:
        try:
            if not _candidate_file_matches(candidate_ref, verifier_rel, root / verifier_rel,
                                           cwd=root, tree_root=root):
                finding("VERIFIER_NOT_AT_CANDIDATE", "ERROR",
                        "running verifier bytes do not match the candidate commit", verifier_rel)
        except OSError as exc:
            finding("VERIFIER_NOT_AT_CANDIDATE", "ERROR", str(exc), verifier_rel)
        for rel_path in _loaded_delivery_module_paths(root):
            try:
                if not _candidate_file_matches(candidate_ref, rel_path, root / rel_path,
                                               cwd=root, tree_root=root):
                    finding("VERIFIER_DEPENDENCY_NOT_AT_CANDIDATE", "ERROR",
                            "loaded delivery validation code does not match the candidate commit", rel_path)
            except OSError as exc:
                finding("VERIFIER_DEPENDENCY_NOT_AT_CANDIDATE", "ERROR", str(exc), rel_path)

    sources: dict[str, dict[str, Any]] = {}
    claims: dict[str, dict[str, Any]] = {}
    configured_enforcement_stage = "UNKNOWN"
    prefixes: list[str] = []
    trusted_exemptions: list[dict[str, str]] = []
    try:
        source_registry_path = "governance/evidence/SOURCE_REGISTRY.json"
        if not _candidate_file_matches(candidate_ref, source_registry_path,
                                       candidate_tree / source_registry_path,
                                       cwd=root, tree_root=candidate_tree):
            finding("EVIDENCE_INPUT_NOT_AT_CANDIDATE", "ERROR",
                    "source registry bytes do not match the candidate commit", source_registry_path)
        source_registry = _read_candidate_json(candidate_tree, source_registry_path)
        sources = validate_source_registry(source_registry)
        for source_id, source in sources.items():
            locator = source["locator"]
            if not _local_source_exists(candidate_tree, locator):
                finding("SOURCE_LOCATOR_INVALID", "ERROR", f"source {source_id} has unsafe or missing locator {locator}")
            elif locator.startswith(("https://", "http://")):
                finding("EXTERNAL_SOURCE_NOT_AUTHENTICATED", "UNVERIFIED",
                        f"offline validation cannot authenticate external source {source_id}")
            elif not _candidate_file_matches(candidate_ref, locator, candidate_tree / locator,
                                             cwd=root, tree_root=candidate_tree):
                finding("SOURCE_NOT_AT_CANDIDATE", "ERROR",
                        f"source {source_id} bytes do not match the candidate commit", locator)
    except (OSError, ValueError, TypeError) as exc:
        finding("SOURCE_REGISTRY_INVALID", "ERROR", str(exc))
    try:
        claims_path = "governance/evidence/CLAIM_REGISTRY.json"
        if not _candidate_file_matches(candidate_ref, claims_path, candidate_tree / claims_path,
                                       cwd=root, tree_root=candidate_tree):
            finding("EVIDENCE_INPUT_NOT_AT_CANDIDATE", "ERROR",
                    "claim registry bytes do not match the candidate commit", claims_path)
        claims = validate_claim_registry(
            _read_candidate_json(candidate_tree, claims_path), sources
        )
    except (OSError, ValueError, TypeError) as exc:
        finding("CLAIM_REGISTRY_INVALID", "ERROR", str(exc))
    try:
        matrix_path = MATRIX_PATH
        if not _candidate_file_matches(candidate_ref, matrix_path, candidate_tree / matrix_path,
                                       cwd=root, tree_root=candidate_tree):
            finding("EVIDENCE_INPUT_NOT_AT_CANDIDATE", "ERROR",
                    "verification matrix bytes do not match the candidate commit", matrix_path)
        matrix = _read_candidate_json(candidate_tree, matrix_path)
        if not isinstance(matrix, dict) or matrix.get("schema_version") != 1:
            raise ValueError("verification matrix must have schema_version=1")
        if matrix.get("enforcement_stage") not in {"REPORT_ONLY", "BLOCK_NEW_MATERIAL"}:
            raise ValueError("verification matrix enforcement_stage is unsupported")
        expected_report_only = matrix["enforcement_stage"] == "REPORT_ONLY"
        if not isinstance(matrix.get("report_only"), bool) or matrix["report_only"] != expected_report_only:
            raise ValueError("verification matrix report_only must be true exactly when enforcement_stage is REPORT_ONLY")
        configured_enforcement_stage = matrix["enforcement_stage"]
        _, prefixes, trusted_exemptions = _trusted_material_policy(root, matrix)
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
    exempted = [path for path in changed if any(
        _path_matches(path, [exemption["path"]]) for exemption in trusted_exemptions
    )]
    classified = set(material) | set(exempted)
    unclassified = [path for path in changed if path not in classified]
    for path in unclassified:
        finding("UNCLASSIFIED_CHANGED_PATH", "BLOCKING",
                "changed path is neither in candidate material scopes nor a verifier-base exemption; "
                "classify it as material or add a reviewed verifier-base exemption", path)
    records_dir = _safe_candidate_path(candidate_tree, "governance/evidence/work_items")
    if records_dir is None or not records_dir.is_dir():
        finding("WORK_ITEM_DIRECTORY_UNSAFE", "ERROR",
                "candidate work-item directory is missing or traverses a symlink",
                "governance/evidence/work_items")
        record_paths = []
    else:
        record_paths = sorted(records_dir.glob("*.json"))
    records: list[tuple[str, Any, dict[str, Any]]] = []
    work_item_proofs: list[dict[str, Any]] = []
    changed_set = set(changed)
    for path in record_paths:
        rel = path.relative_to(candidate_tree).as_posix()
        safe_path = _safe_candidate_path(candidate_tree, rel)
        if safe_path is None or safe_path != path:
            finding("WORK_ITEM_INVALID", "ERROR",
                    "candidate work-item record is unsafe or traverses a symlink", rel)
            continue
        try:
            if not _candidate_file_matches(candidate_ref, rel, path, cwd=root,
                                           tree_root=candidate_tree):
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
        "candidate_root_sha": actual_candidate_root_sha,
        "verifier_source_sha": actual_verifier_source_sha,
        "base_ref": base_ref,
        "candidate_ref": candidate_ref,
        "changed_path_count": len(changed),
        "material_path_count": len(material),
        "material_paths": material,
        "trusted_non_material_exemptions": trusted_exemptions,
        "exempted_paths": exempted,
        "unclassified_paths": unclassified,
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
        # Paths and details can originate in candidate-controlled evidence. Keep
        # those values in the explicit JSON report, not a GitHub step summary.
        lines.extend(["| Severity | Code |", "|---|---|"])
        for row in findings:
            lines.append(f"| {row.get('severity', '')} | {row.get('code', '')} |")
    else:
        lines.append("No findings were emitted for this candidate.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--candidate-ref", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--candidate-root", type=Path,
                        help="read candidate files from this checkout without importing or executing its code")
    parser.add_argument("--candidate-root-sha",
                        help="verified exact commit SHA used to materialize a separate candidate root")
    parser.add_argument("--verifier-source-sha",
                        help="require this checkout's HEAD to equal the declared trusted verifier source SHA")
    parser.add_argument("--output", type=Path,
                        help="write the full structured report here; stdout otherwise contains safe summary metadata")
    parser.add_argument("--summary-output", type=Path,
                        help="append a Markdown findings summary to this file")
    parser.add_argument("--mode", choices=("report-only", "enforce-new-material", "strict"), default="report-only")
    args = parser.parse_args(argv)
    report = build_report(base_ref=args.base_ref, candidate_ref=args.candidate_ref,
                          candidate_sha=args.candidate_sha, candidate_root=args.candidate_root,
                          candidate_root_sha=args.candidate_root_sha,
                          verifier_source_sha=args.verifier_source_sha)
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
            print("Full structured evidence report omitted; pass --output <path> to retain it.")
        if args.summary_output:
            with args.summary_output.open("a", encoding="utf-8") as summary_file:
                summary_file.write(render_summary(report))
    except OSError as exc:
        print(f"cannot write evidence report: {exc}", file=sys.stderr)
        return 2
    errors = [finding for finding in report["findings"] if finding["severity"] == "ERROR"]
    if args.mode == "strict" and report["findings"]:
        print(f"Evidence verification blocked: {report['blocking_finding_count']} finding(s).")
        for item in blocking:
            print(f"{item['severity']} {item['code']}")
        return 1
    if args.mode in {"enforce-new-material", "strict"} and blocking:
        print(f"Evidence verification blocked: {report['blocking_finding_count']} finding(s).")
        for item in blocking:
            print(f"{item['severity']} {item['code']}")
        return 1
    # Report-only suppresses all policy findings. Enforcement blocks structural
    # errors and uncovered material changes while preserving UNVERIFIED claims.
    print(f"Evidence report: candidate={report['candidate_sha']} findings={report['finding_count']} errors={len(errors)} mode={report['mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
