"""Fail-closed admission of local agent requests against committed work items.

This is a local CLI guard, not a universal platform intake hook. The supplied
work-item reference is untrusted: the item must be tracked at HEAD, unchanged
in the working tree, structurally valid, and bound to the request's title,
scope, and path permissions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any, Mapping

from core.delivery.validators import validate_work_item, work_item_from_dict


_WORK_ITEM_ROOT = "governance/evidence/work_items/"
_REQUEST_REF_KEY = "delivery_work_item"


@dataclass(frozen=True)
class AdmissionDecision:
    accepted: bool
    state: str
    work_item_id: str | None
    work_item_sha256: str | None
    blockers: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["blockers"] = list(self.blockers)
        result["metadata"] = dict(self.metadata)
        return result


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise ValueError("WORK_ITEM_GIT_LOOKUP_FAILED")
    return completed.stdout


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("WORK_ITEM_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _safe_item_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("WORK_ITEM_PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("WORK_ITEM_PATH_INVALID")
    normalized = path.as_posix()
    if not normalized.startswith(_WORK_ITEM_ROOT) or not normalized.endswith(".json"):
        raise ValueError("WORK_ITEM_PATH_OUTSIDE_CANONICAL_ROOT")
    return normalized


def _path_is_covered(path: str, allowed: str) -> bool:
    candidate = PurePosixPath(path.rstrip("/"))
    scope = PurePosixPath(allowed.rstrip("/"))
    if allowed.endswith("/") or allowed.endswith("/**"):
        scope_text = allowed[:-3] if allowed.endswith("/**") else allowed.rstrip("/")
        return path == scope_text or path.startswith(scope_text + "/")
    return candidate == scope


def _path_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        return ()
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            return ()
        path = entry.strip()
        if "\\" in path or ":" in path:
            return ()
        pure = PurePosixPath(path)
        if pure.is_absolute() or any(part in {".", ".."} for part in path.split("/")):
            return ()
        result.append(pure.as_posix())
    return tuple(result)


def _pattern_covers(required: str, supplied: str) -> bool:
    """Whether a supplied forbidden path blocks at least a required scope."""
    def base(value: str) -> str:
        return value[:-3].rstrip("/") if value.endswith("/**") else value.rstrip("/")

    required_base = base(required)
    supplied_base = base(supplied)
    return required_base == supplied_base or required_base.startswith(supplied_base + "/")


def _task_contract_matches(item: Any, payload: Mapping[str, Any], reference: Mapping[str, Any]) -> bool:
    contracts = item.extensions.get("agent_task_contracts", [])
    contract_id = reference.get("task_contract_id")
    if not isinstance(contracts, list):
        return False
    matches = [contract for contract in contracts
               if isinstance(contract, Mapping) and contract.get("task_contract_id") == contract_id]
    if len(matches) != 1:
        return False
    match = matches[0]
    fields = (
        "source_agent", "action", "title", "scope", "requested_paths", "allowed_paths",
        "forbidden_paths", "expected_tests", "acceptance_proof",
    )
    for field in fields:
        expected = match.get(field)
        actual = payload.get(field)
        if isinstance(expected, list):
            if not isinstance(actual, (list, tuple)) or list(actual) != expected:
                return False
        elif actual != expected:
            return False
    return True


def _load_committed_item(root: Path, reference: Mapping[str, Any]) -> tuple[Any, bytes]:
    rel_path = _safe_item_path(reference.get("path"))
    expected_id = reference.get("work_item_id")
    expected_hash = reference.get("sha256")
    if not isinstance(expected_id, str) or not expected_id.strip():
        raise ValueError("WORK_ITEM_ID_MISSING")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(
        char not in "0123456789abcdef" for char in expected_hash
    ):
        raise ValueError("WORK_ITEM_SHA256_INVALID")

    # Refuse symlinks in every path component so a tracked link cannot point
    # outside the canonical repository evidence directory.
    current = root
    for part in PurePosixPath(rel_path).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("WORK_ITEM_SYMLINK_BLOCKED")
    if not current.is_file():
        raise ValueError("WORK_ITEM_MISSING")

    tracked = _git(root, "ls-files", "--error-unmatch", "--", rel_path)
    if tracked.decode("utf-8", "replace").strip() != rel_path:
        raise ValueError("WORK_ITEM_NOT_TRACKED")
    status = _git(root, "status", "--porcelain=v1", "--", rel_path)
    if status:
        raise ValueError("WORK_ITEM_DIRTY")
    committed = _git(root, "show", f"HEAD:{rel_path}")
    try:
        current_bytes = (root / rel_path).read_bytes()
    except OSError as exc:
        raise ValueError("WORK_ITEM_MISSING") from exc
    if current_bytes != committed:
        raise ValueError("WORK_ITEM_STALE")
    actual_hash = hashlib.sha256(committed).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError("WORK_ITEM_HASH_MISMATCH")

    try:
        decoded = json.loads(committed.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(decoded, dict):
            raise ValueError("WORK_ITEM_NOT_OBJECT")
        item = work_item_from_dict(decoded)
        validate_work_item(item, complete=True)
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("WORK_ITEM_"):
            raise
        raise ValueError("WORK_ITEM_INVALID") from exc
    if item.work_item_id != expected_id:
        raise ValueError("WORK_ITEM_ID_MISMATCH")
    if PurePosixPath(rel_path).stem != item.work_item_id:
        raise ValueError("WORK_ITEM_PATH_ID_MISMATCH")
    return item, committed


def admit_agent_work(payload: Mapping[str, Any], *, repository_root: str | Path) -> AdmissionDecision:
    """Validate one local request against its exact committed canonical item."""

    blockers: list[str] = []
    reference = payload.get("metadata", {}).get(_REQUEST_REF_KEY) if isinstance(
        payload.get("metadata"), Mapping
    ) else None
    if not isinstance(reference, Mapping):
        return AdmissionDecision(False, "BLOCKED", None, None, ("WORK_ITEM_REFERENCE_REQUIRED",), {})

    try:
        root = Path(repository_root).resolve(strict=True)
        top = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve(strict=True)
        if top != root:
            raise ValueError("REPOSITORY_ROOT_MISMATCH")
        item, item_bytes = _load_committed_item(root, reference)
        if not _task_contract_matches(item, payload, reference):
            blockers.append("WORK_ITEM_TASK_CONTRACT_MISMATCH")

        requested = _path_list(payload.get("requested_paths"))
        allowed = _path_list(payload.get("allowed_paths"))
        item_allowed = tuple(item.allowed_paths)
        if not requested or not allowed:
            blockers.append("WORK_ITEM_REQUEST_PATHS_INVALID")
        elif any(not any(_path_is_covered(path, scope) for scope in item_allowed) for path in requested):
            blockers.append("WORK_ITEM_REQUESTED_PATH_OUTSIDE_SCOPE")
        elif any(not any(_path_is_covered(scope, item_scope) for item_scope in item_allowed) for scope in allowed):
            blockers.append("WORK_ITEM_ALLOWED_PATH_OUTSIDE_SCOPE")

        request_forbidden = _path_list(payload.get("forbidden_paths"))
        if any(not any(_pattern_covers(path, denied) for denied in request_forbidden)
               for path in item.forbidden_paths):
            blockers.append("WORK_ITEM_FORBIDDEN_PATHS_DROPPED")

        sha256 = hashlib.sha256(item_bytes).hexdigest()
        return AdmissionDecision(
            not blockers,
            "ADMITTED" if not blockers else "BLOCKED",
            item.work_item_id,
            sha256,
            tuple(sorted(set(blockers))),
            {"repository_head": _git(root, "rev-parse", "HEAD").decode().strip(),
             "work_item_path": str(reference.get("path")),
             "work_item_contract_hash": _contract_hash(item)},
        )
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "WORK_ITEM_ADMISSION_FAILED"
        return AdmissionDecision(False, "BLOCKED", None, None, (reason,), {})


def _contract_hash(item: Any) -> str:
    from core.delivery.validators import work_item_contract_hash

    return work_item_contract_hash(item)
