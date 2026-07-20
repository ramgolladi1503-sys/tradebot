"""Shared worktree ownership claim registry and lifecycle."""

from __future__ import annotations

import fcntl
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.agent_supervisor_contract import preflight_contract
from core.agent_supervisor_git import (
    _atomic_write_json,
    _claims_paths,
    _hash_path,
    _load_claim_store,
)
from core.agent_supervisor_types import (
    AGENT_SUPERVISOR_SCHEMA_VERSION,
    _CLAIM_HOLDING_STATES,
    SupervisorContract,
    SupervisorResult,
    SupervisorState,
    _paths_overlap,
    _result,
    _stable_hash,
    _text,
    _utc_now,
)

def _claims_conflict(new_paths: Sequence[str], existing_paths: Sequence[str]) -> bool:
    return any(_paths_overlap(left, right) for left in new_paths for right in existing_paths)


def claim_contract(
    contract: SupervisorContract,
    *,
    human_approved: bool = False,
    approved_by: str | None = None,
    enforce_tradebot_guard: bool = True,
) -> SupervisorResult:
    preflight = preflight_contract(
        contract,
        human_approved=human_approved,
        approved_by=approved_by,
        enforce_tradebot_guard=enforce_tradebot_guard,
    )
    if not preflight.accepted:
        return _result(
            state=SupervisorState.CLAIM_BLOCKED,
            accepted=False,
            task_id=contract.task_id,
            blockers=preflight.blockers,
            warnings=preflight.warnings,
            details={"preflight": preflight.to_dict()},
        )

    worktree = Path(contract.worktree_path)
    claims_path, lock_path = _claims_paths(worktree)
    warnings: list[str] = list(preflight.warnings)
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        store = _load_claim_store(claims_path)
        claims = dict(store["claims"])
        existing = claims.get(contract.task_id)
        if isinstance(existing, Mapping) and existing.get("state") in _CLAIM_HOLDING_STATES:
            same_identity = (
                existing.get("worktree_path") == str(worktree.resolve())
                and existing.get("branch") == contract.branch
                and existing.get("implementer") == contract.implementer
            )
            if same_identity:
                warnings.append("CLAIM_ALREADY_ACTIVE")
                return _result(
                    state=SupervisorState.CLAIMED,
                    accepted=True,
                    task_id=contract.task_id,
                    warnings=warnings,
                    details={"claim": dict(existing), "preflight": preflight.to_dict()},
                )
            return _result(
                state=SupervisorState.CLAIM_BLOCKED,
                accepted=False,
                task_id=contract.task_id,
                blockers=("TASK_ID_ALREADY_CLAIMED",),
                details={"existing_claim": dict(existing), "preflight": preflight.to_dict()},
            )

        conflicts: list[dict[str, Any]] = []
        for other_task_id, claim in claims.items():
            if not isinstance(claim, Mapping) or claim.get("state") not in _CLAIM_HOLDING_STATES:
                continue
            other_paths = tuple(str(path) for path in claim.get("ownership_paths", []))
            if _claims_conflict(contract.ownership_paths, other_paths):
                conflicts.append(
                    {
                        "task_id": other_task_id,
                        "implementer": claim.get("implementer"),
                        "branch": claim.get("branch"),
                        "ownership_paths": list(other_paths),
                    }
                )
        if conflicts:
            return _result(
                state=SupervisorState.CLAIM_BLOCKED,
                accepted=False,
                task_id=contract.task_id,
                blockers=("OWNERSHIP_CONFLICT",),
                details={"conflicts": conflicts, "preflight": preflight.to_dict()},
            )

        git_details = preflight.details["git"]
        claim = {
            "schema_version": AGENT_SUPERVISOR_SCHEMA_VERSION,
            "task_id": contract.task_id,
            "state": "ACTIVE",
            "created_at": _utc_now(),
            "implementer": contract.implementer,
            "reviewer": contract.reviewer,
            "worktree_path": str(worktree.resolve()),
            "branch": contract.branch,
            "base_ref": contract.base_ref,
            "base_commit": git_details["base_commit"],
            "initial_head_commit": git_details["head_commit"],
            "requested_paths": list(contract.requested_paths),
            "allowed_paths": list(contract.allowed_paths),
            "prohibited_paths": list(contract.prohibited_paths),
            "ownership_paths": list(contract.ownership_paths),
            "frozen_hashes": {
                path: _hash_path(worktree, path) for path in contract.frozen_paths
            },
            "contract_sha256": _stable_hash(contract.to_dict()),
        }
        claims[contract.task_id] = claim
        store["claims"] = claims
        _atomic_write_json(claims_path, store)

    return _result(
        state=SupervisorState.CLAIMED,
        accepted=True,
        task_id=contract.task_id,
        warnings=warnings,
        details={
            "claim": claim,
            "claim_store": str(claims_path),
            "preflight": preflight.to_dict(),
        },
    )


def _read_claim(contract: SupervisorContract) -> tuple[dict[str, Any] | None, Path, Path]:
    worktree = Path(contract.worktree_path)
    claims_path, lock_path = _claims_paths(worktree)
    store = _load_claim_store(claims_path)
    claim = store["claims"].get(contract.task_id)
    return (dict(claim) if isinstance(claim, Mapping) else None, claims_path, lock_path)


def _update_claim_state(
    contract: SupervisorContract,
    *,
    state: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    claim, claims_path, lock_path = _read_claim(contract)
    if claim is None:
        raise RuntimeError("claim_not_found")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        store = _load_claim_store(claims_path)
        current = dict(store["claims"].get(contract.task_id) or {})
        current["state"] = state
        current["updated_at"] = _utc_now()
        current.update(dict(extra or {}))
        claims = dict(store["claims"])
        claims[contract.task_id] = current
        store["claims"] = claims
        _atomic_write_json(claims_path, store)
        return current


def release_contract(contract: SupervisorContract, *, force: bool = False) -> SupervisorResult:
    claim, _, _ = _read_claim(contract)
    if claim is None:
        return _result(
            state=SupervisorState.RELEASE_BLOCKED,
            accepted=False,
            task_id=contract.task_id,
            blockers=("CLAIM_NOT_FOUND",),
        )
    if claim.get("state") != "REVIEW_APPROVED" and not force:
        return _result(
            state=SupervisorState.RELEASE_BLOCKED,
            accepted=False,
            task_id=contract.task_id,
            blockers=("REVIEW_APPROVAL_REQUIRED_BEFORE_RELEASE",),
            details={"claim": claim},
        )
    updated = _update_claim_state(
        contract,
        state="RELEASED",
        extra={"released_at": _utc_now(), "forced_release": bool(force)},
    )
    return _result(
        state=SupervisorState.RELEASED,
        accepted=True,
        task_id=contract.task_id,
        warnings=("FORCED_RELEASE",) if force else (),
        details={"claim": updated},
    )


def get_contract_status(contract: SupervisorContract) -> SupervisorResult:
    claim, claims_path, _ = _read_claim(contract)
    return _result(
        state=SupervisorState.STATUS,
        accepted=claim is not None,
        task_id=contract.task_id,
        blockers=() if claim is not None else ("CLAIM_NOT_FOUND",),
        details={"claim": claim, "claim_store": str(claims_path)},
    )
