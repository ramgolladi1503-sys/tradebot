"""Contract normalization, policy validation, and worktree preflight."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Mapping, Sequence

from core.agent_supervisor_git import _run_git
from core.agent_supervisor_types import (
    AGENT_SUPERVISOR_SCHEMA_VERSION,
    _ALLOWED_EXECUTABLES,
    _ALLOWED_PYTHON_MODULES,
    _BLOCKED_ARGUMENTS,
    _BLOCKED_SCRIPT_BASENAMES,
    _READ_ONLY_GIT_COMMANDS,
    _TASK_ID_RE,
    AcceptanceCommand,
    SupervisorContract,
    SupervisorResult,
    SupervisorState,
    _bool,
    _normalize_rel_path,
    _path_matches,
    _paths_overlap,
    _result,
    _stable_hash,
    _text,
    _tuple_text,
    _unsafe_rel_path,
)


def load_contract_file(path: str | Path) -> dict[str, Any]:
    contract_path = Path(path).expanduser()
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed_to_load_contract:{type(exc).__name__}:{exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("contract_must_be_json_object")
    return dict(payload)


def normalize_supervisor_contract(payload: Mapping[str, Any]) -> SupervisorContract:
    supervisor = payload.get("supervisor")
    supervisor_map = dict(supervisor) if isinstance(supervisor, Mapping) else {}
    source_agent = _text(payload.get("source_agent")).lower().replace("-", "_").replace(" ", "_")
    task_id = _text(supervisor_map.get("task_id")).lower()
    if not task_id:
        task_id = f"task-{_stable_hash({'title': payload.get('title'), 'scope': payload.get('scope')})[:16]}"

    commands: list[AcceptanceCommand] = []
    raw_commands = supervisor_map.get("acceptance_commands")
    if isinstance(raw_commands, Sequence) and not isinstance(raw_commands, (str, bytes)):
        for index, item in enumerate(raw_commands):
            command_map = dict(item) if isinstance(item, Mapping) else {}
            argv = _tuple_text(command_map.get("argv"))
            timeout = command_map.get("timeout_seconds", 900)
            try:
                timeout_seconds = int(timeout)
            except Exception:
                timeout_seconds = 0
            commands.append(
                AcceptanceCommand(
                    name=_text(command_map.get("name")) or f"command-{index + 1}",
                    argv=argv,
                    timeout_seconds=timeout_seconds,
                )
            )

    requested_paths = tuple(_normalize_rel_path(path) for path in _tuple_text(payload.get("requested_paths")))
    allowed_paths = tuple(_normalize_rel_path(path) for path in _tuple_text(payload.get("allowed_paths")))
    prohibited_paths = tuple(_normalize_rel_path(path) for path in _tuple_text(payload.get("forbidden_paths")))
    ownership_paths = tuple(
        _normalize_rel_path(path)
        for path in (_tuple_text(supervisor_map.get("ownership_paths")) or requested_paths)
    )

    metadata = supervisor_map.get("metadata")
    return SupervisorContract(
        schema_version=int(supervisor_map.get("schema_version") or AGENT_SUPERVISOR_SCHEMA_VERSION),
        task_id=task_id,
        objective=_text(supervisor_map.get("objective")) or _text(payload.get("scope")),
        implementer=_text(supervisor_map.get("implementer")) or source_agent,
        reviewer=_text(supervisor_map.get("reviewer")),
        worktree_path=str(Path(_text(supervisor_map.get("worktree_path"))).expanduser()),
        branch=_text(supervisor_map.get("branch")),
        base_ref=_text(supervisor_map.get("base_ref")) or "main",
        requested_paths=requested_paths,
        allowed_paths=allowed_paths,
        prohibited_paths=prohibited_paths,
        ownership_paths=ownership_paths,
        frozen_paths=tuple(_normalize_rel_path(path) for path in _tuple_text(supervisor_map.get("frozen_paths"))),
        acceptance_commands=tuple(commands),
        required_artifacts=tuple(
            _normalize_rel_path(path) for path in _tuple_text(supervisor_map.get("required_artifacts"))
        ),
        require_clean_worktree=_bool(supervisor_map.get("require_clean_worktree"), default=True),
        require_committed_head=_bool(supervisor_map.get("require_committed_head"), default=True),
        work_payload=dict(payload),
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


def _command_policy_blockers(command: AcceptanceCommand) -> list[str]:
    blockers: list[str] = []
    if not command.name:
        blockers.append("ACCEPTANCE_COMMAND_NAME_MISSING")
    if not command.argv:
        blockers.append("ACCEPTANCE_COMMAND_ARGV_MISSING")
        return blockers
    if command.timeout_seconds < 1 or command.timeout_seconds > 7200:
        blockers.append("ACCEPTANCE_COMMAND_TIMEOUT_INVALID")

    executable_token = command.argv[0]
    executable = Path(executable_token).name.lower()
    if executable_token != executable:
        blockers.append("ACCEPTANCE_COMMAND_EXECUTABLE_PATH_BLOCKED")
    if executable not in _ALLOWED_EXECUTABLES:
        blockers.append("ACCEPTANCE_COMMAND_EXECUTABLE_NOT_ALLOWED")

    lowered = tuple(arg.lower() for arg in command.argv)
    if any(arg in _BLOCKED_ARGUMENTS for arg in lowered):
        blockers.append("ACCEPTANCE_COMMAND_TRADING_ACTION_BLOCKED")
    if any(Path(arg).name.lower() in _BLOCKED_SCRIPT_BASENAMES for arg in command.argv[1:]):
        blockers.append("ACCEPTANCE_COMMAND_LIVE_SCRIPT_BLOCKED")
    if executable in {"python", "python3"}:
        if len(lowered) < 3 or lowered[1] != "-m":
            blockers.append("ACCEPTANCE_COMMAND_DIRECT_PYTHON_BLOCKED")
        elif lowered[2] not in _ALLOWED_PYTHON_MODULES:
            blockers.append("ACCEPTANCE_COMMAND_PYTHON_MODULE_NOT_ALLOWED")
    if executable == "git":
        if len(lowered) < 2 or lowered[1] not in _READ_ONLY_GIT_COMMANDS:
            blockers.append("ACCEPTANCE_COMMAND_GIT_MUTATION_BLOCKED")
    return blockers


def validate_contract_shape(contract: SupervisorContract) -> tuple[tuple[str, ...], tuple[str, ...]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if contract.schema_version != AGENT_SUPERVISOR_SCHEMA_VERSION:
        blockers.append("SUPERVISOR_SCHEMA_VERSION_UNSUPPORTED")
    if not _TASK_ID_RE.fullmatch(contract.task_id):
        blockers.append("TASK_ID_INVALID")
    if not contract.objective:
        blockers.append("OBJECTIVE_MISSING")
    if not contract.implementer:
        blockers.append("IMPLEMENTER_MISSING")
    if not contract.reviewer:
        blockers.append("REVIEWER_MISSING")
    elif contract.reviewer.casefold() == contract.implementer.casefold():
        blockers.append("REVIEWER_MUST_BE_INDEPENDENT")
    if not contract.worktree_path:
        blockers.append("WORKTREE_PATH_MISSING")
    elif not Path(contract.worktree_path).is_absolute():
        blockers.append("WORKTREE_PATH_MUST_BE_ABSOLUTE")
    if not contract.branch:
        blockers.append("BRANCH_MISSING")
    elif contract.branch in {"main", "master"}:
        blockers.append("ISOLATED_BRANCH_REQUIRED")
    if not contract.base_ref:
        blockers.append("BASE_REF_MISSING")
    if not contract.requested_paths:
        blockers.append("REQUESTED_PATHS_MISSING")
    if not contract.allowed_paths:
        blockers.append("ALLOWED_PATHS_MISSING")
    if not contract.ownership_paths:
        blockers.append("OWNERSHIP_PATHS_MISSING")
    if not contract.acceptance_commands:
        blockers.append("ACCEPTANCE_COMMANDS_MISSING")

    groups = {
        "REQUESTED": contract.requested_paths,
        "ALLOWED": contract.allowed_paths,
        "PROHIBITED": contract.prohibited_paths,
        "OWNERSHIP": contract.ownership_paths,
        "FROZEN": contract.frozen_paths,
        "ARTIFACT": contract.required_artifacts,
    }
    for label, paths in groups.items():
        for path in paths:
            if _unsafe_rel_path(path):
                blockers.append(f"{label}_PATH_UNSAFE")

    for path in contract.requested_paths:
        if not any(_path_matches(path, allowed) for allowed in contract.allowed_paths):
            blockers.append("REQUESTED_PATH_OUTSIDE_ALLOWED_PATHS")
        if any(_paths_overlap(path, prohibited) for prohibited in contract.prohibited_paths):
            blockers.append("REQUESTED_PATH_PROHIBITED")
        if any(_paths_overlap(path, frozen) for frozen in contract.frozen_paths):
            blockers.append("REQUESTED_PATH_FROZEN")

    for path in contract.ownership_paths:
        if not any(_path_matches(path, allowed) for allowed in contract.allowed_paths):
            blockers.append("OWNERSHIP_PATH_OUTSIDE_ALLOWED_PATHS")
        if any(_paths_overlap(path, prohibited) for prohibited in contract.prohibited_paths):
            blockers.append("OWNERSHIP_PATH_PROHIBITED")

    for command in contract.acceptance_commands:
        blockers.extend(_command_policy_blockers(command))

    if not contract.frozen_paths:
        warnings.append("FROZEN_PATHS_EMPTY")
    if not contract.required_artifacts:
        warnings.append("REQUIRED_ARTIFACTS_EMPTY")
    return (
        tuple(sorted(set(blockers))),
        tuple(sorted(set(warnings))),
    )


def _tradebot_guard_details(
    payload: Mapping[str, Any],
    *,
    human_approved: bool,
    approved_by: str | None,
) -> tuple[list[str], list[str], dict[str, Any]]:
    try:
        from core.agent_approval import approve_agent_scope
        from core.agent_scope_guard import assess_agent_scope
        from core.agent_work_contract import normalize_agent_work_request, validate_agent_work_contract

        request = normalize_agent_work_request(payload)
        contract_decision = validate_agent_work_contract(request)
        scope_decision = assess_agent_scope(request, contract_decision=contract_decision)
        approval_decision = approve_agent_scope(
            scope_decision,
            human_approved=human_approved,
            approved_by=approved_by,
        )
        blockers = list(contract_decision.blockers) + list(scope_decision.blockers)
        warnings = list(contract_decision.warnings) + list(scope_decision.warnings)
        if not approval_decision.approved:
            blockers.extend(approval_decision.blockers)
            warnings.extend(approval_decision.warnings)
        return blockers, warnings, {
            "work_request": request.to_dict(),
            "contract_decision": contract_decision.to_dict(),
            "scope_decision": scope_decision.to_dict(),
            "approval_decision": approval_decision.to_dict(),
        }
    except Exception as exc:
        return ["TRADEBOT_SCOPE_GUARD_UNAVAILABLE"], [], {
            "scope_guard_error": f"{type(exc).__name__}:{exc}"
        }


def preflight_contract(
    contract: SupervisorContract,
    *,
    human_approved: bool = False,
    approved_by: str | None = None,
    enforce_tradebot_guard: bool = True,
) -> SupervisorResult:
    blockers, warnings = map(list, validate_contract_shape(contract))
    details: dict[str, Any] = {"contract": contract.to_dict()}

    if enforce_tradebot_guard:
        guard_blockers, guard_warnings, guard_details = _tradebot_guard_details(
            contract.work_payload,
            human_approved=human_approved,
            approved_by=approved_by,
        )
        blockers.extend(guard_blockers)
        warnings.extend(guard_warnings)
        details["tradebot_guard"] = guard_details

    worktree = Path(contract.worktree_path)
    if not worktree.exists() or not worktree.is_dir():
        blockers.append("WORKTREE_NOT_FOUND")
    else:
        try:
            top_level = Path(_run_git(worktree, "rev-parse", "--show-toplevel")).resolve()
            branch = _run_git(worktree, "branch", "--show-current")
            head_commit = _run_git(worktree, "rev-parse", "HEAD")
            base_commit = _run_git(worktree, "rev-parse", contract.base_ref)
            status = _run_git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
            details["git"] = {
                "top_level": str(top_level),
                "branch": branch,
                "head_commit": head_commit,
                "base_ref": contract.base_ref,
                "base_commit": base_commit,
                "clean": not bool(status),
                "status_porcelain": status.splitlines(),
            }
            if top_level != worktree.resolve():
                blockers.append("WORKTREE_PATH_NOT_REPOSITORY_ROOT")
            if branch != contract.branch:
                blockers.append("WORKTREE_BRANCH_MISMATCH")
            if contract.require_clean_worktree and status:
                blockers.append("WORKTREE_NOT_CLEAN")
        except Exception as exc:
            blockers.append("WORKTREE_GIT_PREFLIGHT_FAILED")
            details["git_error"] = f"{type(exc).__name__}:{exc}"

    accepted = not blockers
    return _result(
        state=SupervisorState.PREFLIGHT_READY if accepted else SupervisorState.PREFLIGHT_BLOCKED,
        accepted=accepted,
        task_id=contract.task_id,
        blockers=blockers,
        warnings=warnings,
        details=details,
    )
