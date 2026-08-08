#!/usr/bin/env python3
"""Deterministic controller-owned transport identity for MROS review/audit artifacts.

Reviewer/auditor models own substantive verdicts and findings. The controller owns
transport identity: candidate, sprint, round, execution role/job id, and frozen
packet/output/receipt paths. Raw model artifacts remain preserved in Git history;
these helpers only build the canonical payload used for aggregation.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

CONTROLLER_FIELDS = (
    "candidate_head",
    "sprint",
    "round",
    "execution_role_id",
    "execution_job_id",
    "packet_path",
    "output_path",
)


def _repo_relative(value: Any, repo: Path) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    p = Path(value)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            return os.path.normpath(value)
    return Path(os.path.normpath(value)).as_posix()


def canonicalize_artifact(
    artifact: dict[str, Any],
    *,
    member: dict[str, Any],
    manifest: dict[str, Any],
    receipt: dict[str, Any],
    queue_repo: Path,
) -> dict[str, Any]:
    """Overlay only controller-owned identity; never change findings or verdict."""
    out = copy.deepcopy(artifact)
    job = receipt.get("job") if isinstance(receipt, dict) else None
    job = job if isinstance(job, dict) else {}
    out["candidate_head"] = manifest.get("candidate_head")
    out["sprint"] = manifest.get("sprint")
    out["round"] = manifest.get("round")
    out["execution_role_id"] = member.get("execution_role_id")
    out["execution_job_id"] = job.get("job_id")
    out["packet_path"] = _repo_relative(member.get("packet_path"), queue_repo)
    out["output_path"] = _repo_relative(member.get("output_path"), queue_repo)
    return out


def member_for_output(manifest: dict[str, Any], output_path: str, queue_repo: Path) -> dict[str, Any] | None:
    wanted = _repo_relative(output_path, queue_repo)
    for member in manifest.get("members", []):
        if isinstance(member, dict) and _repo_relative(member.get("output_path"), queue_repo) == wanted:
            return member
    return None


def invalid_roles(aggregate: dict[str, Any], manifest: dict[str, Any], queue_repo: Path) -> list[str]:
    """Resolve only the roles whose artifacts remain invalid after canonical overlay."""
    allowed = {
        str(m.get("execution_role_id")): m
        for m in manifest.get("members", [])
        if isinstance(m, dict) and isinstance(m.get("execution_role_id"), str)
    }
    roles: list[str] = []
    for bad in aggregate.get("invalid", []):
        if not isinstance(bad, dict):
            continue
        member = member_for_output(manifest, str(bad.get("file") or ""), queue_repo)
        role = str(member.get("execution_role_id")) if member else ""
        if not role:
            obj = bad.get("review") if isinstance(bad.get("review"), dict) else bad.get("audit")
            candidate = str(obj.get("execution_role_id")) if isinstance(obj, dict) else ""
            if candidate in allowed:
                role = candidate
        if role and role not in roles:
            roles.append(role)
    return roles
