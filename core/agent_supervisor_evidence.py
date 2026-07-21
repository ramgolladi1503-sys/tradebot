"""Implementation verification and independent review evidence gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.agent_supervisor_claims import _read_claim, _update_claim_state
from core.agent_supervisor_git import (
    _changed_paths,
    _credential_isolated_checkout,
    _evidence_dir,
    _hash_path,
    _manifest_hash_is_valid,
    _run_acceptance_command,
    _run_git,
    _write_hashed_manifest,
)
from core.agent_supervisor_types import (
    AGENT_SUPERVISOR_SCHEMA_VERSION,
    _ALLOWED_REVIEW_DECISIONS,
    _VERIFICATION_CLAIM_STATES,
    SupervisorContract,
    SupervisorResult,
    SupervisorState,
    _path_matches,
    _paths_overlap,
    _result,
    _safety,
    _stable_hash,
    _text,
    _tuple_text,
    _utc_now,
)


def verify_contract(contract: SupervisorContract) -> SupervisorResult:
    blockers: list[str] = []
    warnings: list[str] = []
    worktree = Path(contract.worktree_path)
    claim, claims_path, _ = _read_claim(contract)
    if claim is None:
        return _result(
            state=SupervisorState.VERIFICATION_FAILED,
            accepted=False,
            task_id=contract.task_id,
            blockers=("ACTIVE_CLAIM_REQUIRED",),
        )
    if claim.get("state") not in _VERIFICATION_CLAIM_STATES:
        blockers.append("CLAIM_NOT_VERIFIABLE")
    if claim.get("contract_sha256") != _stable_hash(contract.to_dict()):
        blockers.append("CONTRACT_CHANGED_AFTER_CLAIM")
    if claim.get("worktree_path") != str(worktree.resolve()):
        blockers.append("CLAIM_WORKTREE_MISMATCH")
    if claim.get("branch") != contract.branch:
        blockers.append("CLAIM_BRANCH_MISMATCH")

    try:
        branch = _run_git(worktree, "branch", "--show-current")
        head_commit = _run_git(worktree, "rev-parse", "HEAD")
        status = _run_git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    except Exception as exc:
        return _result(
            state=SupervisorState.VERIFICATION_FAILED,
            accepted=False,
            task_id=contract.task_id,
            blockers=("GIT_VERIFICATION_FAILED",),
            details={"error": f"{type(exc).__name__}:{exc}"},
        )

    base_commit = _text(claim.get("base_commit"))
    if branch != contract.branch:
        blockers.append("WORKTREE_BRANCH_MISMATCH")
    if contract.require_clean_worktree and status:
        blockers.append("WORKTREE_NOT_CLEAN")
    if contract.require_committed_head and head_commit == _text(claim.get("initial_head_commit")):
        blockers.append("NO_COMMITTED_CHANGE")

    changed_paths = _changed_paths(worktree, base_commit, head_commit)
    for path in changed_paths:
        if not any(_path_matches(path, allowed) for allowed in contract.allowed_paths):
            blockers.append("CHANGED_PATH_OUTSIDE_ALLOWED_PATHS")
        if any(_paths_overlap(path, prohibited) for prohibited in contract.prohibited_paths):
            blockers.append("PROHIBITED_PATH_CHANGED")

    frozen_current = {path: _hash_path(worktree, path) for path in contract.frozen_paths}
    frozen_initial = dict(claim.get("frozen_hashes") or {})
    frozen_violations = [
        path
        for path in contract.frozen_paths
        if frozen_current.get(path) != frozen_initial.get(path)
    ]
    if frozen_violations:
        blockers.append("FROZEN_PATH_CHANGED")

    command_results: list[dict[str, Any]] = []
    if not blockers:
        try:
            with _credential_isolated_checkout(worktree, head_commit) as (
                verification_root,
                isolated_home,
            ):
                for command in contract.acceptance_commands:
                    result = _run_acceptance_command(
                        verification_root,
                        isolated_home,
                        command,
                    )
                    command_results.append(result)
                    if result["timed_out"]:
                        blockers.append("ACCEPTANCE_COMMAND_TIMED_OUT")
                        break
                    if result["exit_code"] != 0:
                        blockers.append("ACCEPTANCE_COMMAND_FAILED")
                        break
        except Exception as exc:
            blockers.append("ACCEPTANCE_SANDBOX_FAILED")
            command_results.append(
                {
                    "name": "sandbox-setup",
                    "argv": [],
                    "timed_out": False,
                    "exit_code": None,
                    "error": f"{type(exc).__name__}:{exc}",
                    "execution_root": "credential_isolated_git_worktree",
                    "ignored_source_credentials_copied": False,
                    "network_sandboxed": False,
                }
            )

    artifact_hashes = {path: _hash_path(worktree, path) for path in contract.required_artifacts}
    missing_artifacts = [path for path, record in artifact_hashes.items() if record["kind"] == "missing"]
    if missing_artifacts:
        blockers.append("REQUIRED_ARTIFACT_MISSING")

    manifest_payload = {
        "schema_version": AGENT_SUPERVISOR_SCHEMA_VERSION,
        "task_id": contract.task_id,
        "state": "VERIFIED" if not blockers else "VERIFICATION_FAILED",
        "created_at": _utc_now(),
        "implementer": contract.implementer,
        "reviewer_required": contract.reviewer,
        "worktree_path": str(worktree.resolve()),
        "branch": branch,
        "base_commit": base_commit,
        "head_commit": head_commit,
        "worktree_clean": not bool(status),
        "changed_paths": list(changed_paths),
        "scope": {
            "requested_paths": list(contract.requested_paths),
            "allowed_paths": list(contract.allowed_paths),
            "prohibited_paths": list(contract.prohibited_paths),
            "ownership_paths": list(contract.ownership_paths),
            "scope_violations": sorted(
                set(blockers).intersection(
                    {
                        "CHANGED_PATH_OUTSIDE_ALLOWED_PATHS",
                        "PROHIBITED_PATH_CHANGED",
                        "FROZEN_PATH_CHANGED",
                    }
                )
            ),
        },
        "frozen_initial": frozen_initial,
        "frozen_current": frozen_current,
        "frozen_violations": frozen_violations,
        "acceptance_execution": {
            "credential_isolated_git_worktree": True,
            "ignored_source_credentials_copied": False,
            "user_home_isolated": True,
            "proxy_environment_forced_closed": True,
            "network_sandboxed": False,
        },
        "acceptance_commands": command_results,
        "required_artifacts": artifact_hashes,
        "missing_artifacts": missing_artifacts,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "safety": _safety(),
    }
    evidence_dir = _evidence_dir(worktree, contract.task_id)
    manifest_path = evidence_dir / "implementation_manifest.json"
    manifest = _write_hashed_manifest(manifest_path, manifest_payload)
    _update_claim_state(
        contract,
        state="VERIFIED" if not blockers else "ACTIVE",
        extra={
            "head_commit": head_commit,
            "implementation_manifest_path": str(manifest_path),
            "implementation_manifest_sha256": manifest["manifest_sha256"],
        },
    )

    return _result(
        state=SupervisorState.VERIFIED if not blockers else SupervisorState.VERIFICATION_FAILED,
        accepted=not blockers,
        task_id=contract.task_id,
        blockers=blockers,
        warnings=warnings,
        details={
            "manifest_path": str(manifest_path),
            "manifest": manifest,
            "claim_store": str(claims_path),
        },
    )


def _load_json_object(path: str | Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed_to_load_{label}:{type(exc).__name__}:{exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label}_must_be_json_object")
    return dict(payload)


def _validate_reproduction_results(
    expected_commands: Sequence[Mapping[str, Any]],
    reproduction_list: Sequence[Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if len(reproduction_list) != len(expected_commands):
        blockers.append("REVIEW_REPRODUCTION_COUNT_MISMATCH")
        return blockers
    for expected, reproduced in zip(expected_commands, reproduction_list):
        if _text(reproduced.get("name")) != _text(expected.get("name")):
            blockers.append("REVIEW_REPRODUCTION_COMMAND_MISMATCH")
        expected_argv = list(expected.get("argv") or [])
        reproduced_argv = list(reproduced.get("argv") or [])
        if reproduced_argv != expected_argv:
            blockers.append("REVIEW_REPRODUCTION_COMMAND_MISMATCH")
        try:
            exit_code = int(reproduced.get("exit_code", 1))
        except Exception:
            exit_code = 1
        if exit_code != 0:
            blockers.append("REVIEW_REPRODUCTION_FAILED")
    return blockers


def record_independent_review(
    contract: SupervisorContract,
    review_payload: Mapping[str, Any],
) -> SupervisorResult:
    blockers: list[str] = []
    warnings: list[str] = []
    worktree = Path(contract.worktree_path)
    claim, _, _ = _read_claim(contract)
    if claim is None:
        return _result(
            state=SupervisorState.REVIEW_BLOCKED,
            accepted=False,
            task_id=contract.task_id,
            blockers=("CLAIM_REQUIRED",),
        )
    if claim.get("state") != "VERIFIED":
        blockers.append("VERIFIED_IMPLEMENTATION_REQUIRED")

    manifest_path = Path(_text(claim.get("implementation_manifest_path")))
    if not manifest_path.exists():
        blockers.append("IMPLEMENTATION_MANIFEST_MISSING")
        implementation_manifest: dict[str, Any] = {}
    else:
        implementation_manifest = _load_json_object(manifest_path, label="implementation_manifest")
        if not _manifest_hash_is_valid(implementation_manifest):
            blockers.append("IMPLEMENTATION_MANIFEST_HASH_INVALID")

    reviewer = _text(review_payload.get("reviewer"))
    decision = _text(review_payload.get("decision")).upper().replace("-", "_").replace(" ", "_")
    summary = _text(review_payload.get("summary"))
    reproduction_results = review_payload.get("reproduction_results")
    reproduction_list = (
        [dict(item) for item in reproduction_results if isinstance(item, Mapping)]
        if isinstance(reproduction_results, Sequence) and not isinstance(reproduction_results, (str, bytes))
        else []
    )

    if int(review_payload.get("schema_version") or 0) != AGENT_SUPERVISOR_SCHEMA_VERSION:
        blockers.append("REVIEW_SCHEMA_VERSION_UNSUPPORTED")
    if _text(review_payload.get("task_id")) != contract.task_id:
        blockers.append("REVIEW_TASK_ID_MISMATCH")
    if reviewer != contract.reviewer:
        blockers.append("REVIEWER_IDENTITY_MISMATCH")
    if reviewer.casefold() == contract.implementer.casefold():
        blockers.append("REVIEWER_NOT_INDEPENDENT")
    if decision not in _ALLOWED_REVIEW_DECISIONS:
        blockers.append("REVIEW_DECISION_UNKNOWN")
    if not summary:
        blockers.append("REVIEW_SUMMARY_MISSING")
    if _text(review_payload.get("base_commit")) != _text(implementation_manifest.get("base_commit")):
        blockers.append("REVIEW_BASE_COMMIT_MISMATCH")
    if _text(review_payload.get("head_commit")) != _text(implementation_manifest.get("head_commit")):
        blockers.append("REVIEW_HEAD_COMMIT_MISMATCH")
    if _text(review_payload.get("implementation_manifest_sha256")) != _text(
        implementation_manifest.get("manifest_sha256")
    ):
        blockers.append("REVIEW_MANIFEST_HASH_MISMATCH")

    expected_commands = [
        dict(item)
        for item in implementation_manifest.get("acceptance_commands", [])
        if isinstance(item, Mapping) and item.get("name") != "sandbox-setup"
    ]
    if expected_commands and not reproduction_list:
        blockers.append("REVIEW_REPRODUCTION_EVIDENCE_MISSING")
    elif reproduction_list:
        blockers.extend(_validate_reproduction_results(expected_commands, reproduction_list))

    review_manifest_payload = {
        "schema_version": AGENT_SUPERVISOR_SCHEMA_VERSION,
        "task_id": contract.task_id,
        "created_at": _utc_now(),
        "reviewer": reviewer,
        "implementer": contract.implementer,
        "decision": decision,
        "summary": summary,
        "findings": list(_tuple_text(review_payload.get("findings"))),
        "required_changes": list(_tuple_text(review_payload.get("required_changes"))),
        "base_commit": implementation_manifest.get("base_commit"),
        "head_commit": implementation_manifest.get("head_commit"),
        "implementation_manifest_sha256": implementation_manifest.get("manifest_sha256"),
        "reproduction_results": reproduction_list,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "safety": _safety(),
    }
    review_manifest_path = _evidence_dir(worktree, contract.task_id) / "review_manifest.json"
    review_manifest = _write_hashed_manifest(review_manifest_path, review_manifest_payload)

    if blockers:
        state = SupervisorState.REVIEW_BLOCKED
        claim_state = "VERIFIED"
        accepted = False
    elif decision == "APPROVE":
        state = SupervisorState.REVIEW_APPROVED
        claim_state = "REVIEW_APPROVED"
        accepted = True
    elif decision == "REWRITE":
        state = SupervisorState.REVIEW_REWRITE
        claim_state = "ACTIVE"
        accepted = False
    elif decision == "REJECT":
        state = SupervisorState.REVIEW_REJECTED
        claim_state = "REVIEW_REJECTED"
        accepted = False
    else:
        state = SupervisorState.REVIEW_NEEDS_HUMAN
        claim_state = "REVIEW_NEEDS_HUMAN"
        accepted = False

    _update_claim_state(
        contract,
        state=claim_state,
        extra={
            "review_manifest_path": str(review_manifest_path),
            "review_manifest_sha256": review_manifest["manifest_sha256"],
            "review_decision": decision,
        },
    )
    return _result(
        state=state,
        accepted=accepted,
        task_id=contract.task_id,
        blockers=blockers,
        warnings=warnings,
        details={
            "review_manifest_path": str(review_manifest_path),
            "review_manifest": review_manifest,
        },
    )
