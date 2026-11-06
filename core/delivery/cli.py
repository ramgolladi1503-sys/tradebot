"""Offline JSON CLI; it never contacts GitHub, CI, or trading services."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path

from .evidence import canonical_json
from .models import (Defect, DefectSeverity, DefectStatus, Evidence, EvidenceStatus,
                     EvidenceType, WorkItem, WorkItemType)
from .orchestrator import DeliveryOrchestrator
from .roles import DeliveryRole
from .states import DeliveryState
from .validators import validate_work_item, work_item_from_dict, work_item_to_dict
from .research_request_capture import (CaptureError, TransientClockRefusal, append_event,
                                       locked_sidecar, make_event, persist_work_item,
                                       read_only_work_item_snapshot, research_status,
                                       _read_canonical, transient_refusal,
                                       work_item_path_for_id)


_WORK_ITEM_ID_RE = re.compile(r"^[A-Z][A-Z0-9-]{0,79}$")
_MAX_WORK_ITEM_BYTES = 16 * 1024 * 1024
_MAX_CONTRACT_BYTES = 65_536
_CONTRACT_KEYS = {
    "priority", "business_goal", "current_behavior", "expected_behavior", "in_scope",
    "out_of_scope", "dependencies", "acceptance_criteria", "safety_constraints",
    "architecture_impact", "allowed_paths", "forbidden_paths", "expected_tests",
    "qa_attack_plan", "uat_criteria", "release_gates", "rollback_plan",
    "required_ci_checks", "extensions",
}
_CONTRACT_TEXT_FIELDS = {
    "priority", "business_goal", "current_behavior", "expected_behavior",
    "architecture_impact", "rollback_plan",
}
_CONTRACT_LIST_FIELDS = {
    "in_scope", "out_of_scope", "dependencies", "acceptance_criteria", "safety_constraints",
    "allowed_paths", "forbidden_paths", "expected_tests", "qa_attack_plan", "uat_criteria",
    "release_gates", "required_ci_checks",
}
_EVIDENCE_STANDARD_KEYS = {
    "schema_version", "enforcement_mode", "applicability", "applicability_reason",
    "evidence_refs", "assessed_paths", "subject_commit_sha", "claims",
}
_EVIDENCE_CLAIM_KEYS = {
    "claim_id", "statement", "claim_kind", "status", "source_ids", "evidence_refs",
    "assumptions", "gate_evidence", "limitation",
}
_EVIDENCE_ASSUMPTION_KEYS = {"assumption_id", "statement", "classification", "source_ids"}


def _strict_contract_json(raw: bytes) -> dict:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"invalid JSON number: {value}")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("JSON number is not finite")
        return parsed

    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(text, object_pairs_hook=unique_object,
                             parse_constant=reject_constant, parse_float=finite_float)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("contract input must be strict UTF-8 JSON without trailing data") from exc
    if not isinstance(payload, dict):
        raise ValueError("contract input must be a JSON object")
    unknown = set(payload) - _CONTRACT_KEYS
    if unknown:
        raise ValueError(f"contract input contains unknown or forbidden keys: {', '.join(sorted(unknown))}")
    for name in _CONTRACT_TEXT_FIELDS:
        if name in payload and not isinstance(payload[name], str):
            raise ValueError(f"contract field {name} must be a string")
    for name in _CONTRACT_LIST_FIELDS:
        if name in payload and (not isinstance(payload[name], list)
                                or any(not isinstance(value, str) for value in payload[name])):
            raise ValueError(f"contract field {name} must be an array of strings")
    if "extensions" in payload:
        extensions = payload["extensions"]
        if not isinstance(extensions, dict) or set(extensions) - {"evidence_standard"}:
            raise ValueError("extensions may contain only evidence_standard")
        standard = extensions.get("evidence_standard")
        if "evidence_standard" in extensions:
            if not isinstance(standard, dict) or set(standard) - _EVIDENCE_STANDARD_KEYS:
                raise ValueError("evidence_standard contains unknown keys or is not an object")
            if "schema_version" in standard and type(standard["schema_version"]) is not int:
                raise ValueError("evidence_standard schema_version must be an integer")
            for name in ("applicability_reason",):
                if name in standard and not isinstance(standard[name], str):
                    raise ValueError(f"evidence_standard {name} must be a string")
            for name in ("evidence_refs", "assessed_paths"):
                if name in standard and (not isinstance(standard[name], list)
                                         or any(not isinstance(value, str) for value in standard[name])):
                    raise ValueError(f"evidence_standard {name} must be an array of strings")
            if "subject_commit_sha" in standard and standard["subject_commit_sha"] is not None \
                    and not isinstance(standard["subject_commit_sha"], str):
                raise ValueError("evidence_standard subject_commit_sha must be a string or null")
            claims = standard.get("claims", [])
            if not isinstance(claims, list):
                raise ValueError("evidence_standard claims must be an array")
            for claim in claims:
                if not isinstance(claim, dict) or set(claim) - _EVIDENCE_CLAIM_KEYS:
                    raise ValueError("evidence_standard claim contains unknown keys")
                for name in ("source_ids", "evidence_refs"):
                    if name in claim and (not isinstance(claim[name], list)
                                          or any(not isinstance(value, str) for value in claim[name])):
                        raise ValueError(f"evidence_standard claim {name} must be an array of strings")
                gates = claim.get("gate_evidence", {})
                if not isinstance(gates, dict) or any(not isinstance(value, str) for value in gates.values()):
                    raise ValueError("evidence_standard gate_evidence must map names to strings")
                assumptions = claim.get("assumptions", [])
                if not isinstance(assumptions, list):
                    raise ValueError("evidence_standard assumptions must be an array")
                for assumption in assumptions:
                    if (not isinstance(assumption, dict)
                            or set(assumption) - _EVIDENCE_ASSUMPTION_KEYS):
                        raise ValueError("evidence_standard assumption contains unknown keys")
                    sources = assumption.get("source_ids", [])
                    if not isinstance(sources, list) or any(not isinstance(value, str) for value in sources):
                        raise ValueError("evidence_standard assumption source_ids must be an array of strings")
    for name in ("allowed_paths", "forbidden_paths"):
        for value in payload.get(name, []):
            _validate_contract_path_entry(value)
    return payload


def _validate_relative_parts(value: str, *, label: str) -> tuple[str, ...]:
    if (not isinstance(value, str) or not value or value.startswith("/") or "\\" in value
            or value.startswith("~") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)):
        raise ValueError(f"{label} must be a repository-relative POSIX path")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} contains an empty, dot, or traversal component")
    return parts


def _validate_contract_path_entry(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("contract paths must be non-empty strings")
    directory_prefix = value.endswith("/**")
    candidate = value[:-3] if directory_prefix else value
    parts = _validate_relative_parts(candidate, label="contract path")
    if any("*" in part for part in parts):
        raise ValueError("contract paths allow no wildcard except a terminal literal /**")


def _same_file_identity(left, right) -> bool:
    return (left.st_dev, left.st_ino, left.st_size, left.st_mtime_ns, left.st_ctime_ns) == (
        right.st_dev, right.st_ino, right.st_size, right.st_mtime_ns, right.st_ctime_ns)


def _supports_contract_dirfd_operations() -> bool:
    return os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd


def _read_contract_input(relative_path: str, repository_root: Path) -> dict:
    parts = _validate_relative_parts(relative_path, label="--contract-json")
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(not hasattr(os, name) or getattr(os, name) == 0 for name in required_flags):
        raise ValueError("platform lacks required no-follow/non-blocking file-open flags")
    if not _supports_contract_dirfd_operations():
        raise ValueError("platform lacks required descriptor-relative file operations")

    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(repository_root, dir_flags)
    directory_fds = [root_fd]
    directory_links = []
    file_fd = None
    try:
        parent_fd = root_fd
        for component in parts[:-1]:
            before = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
                raise ValueError("contract path parent must be a non-symlink directory")
            child_fd = os.open(component, dir_flags, dir_fd=parent_fd)
            directory_fds.append(child_fd)
            opened = os.fstat(child_fd)
            if (not stat.S_ISDIR(opened.st_mode)
                    or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                raise ValueError("contract path parent changed while opening")
            directory_links.append((parent_fd, component, child_fd, opened.st_dev, opened.st_ino))
            parent_fd = child_fd

        final_name = parts[-1]
        before_path = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(before_path.st_mode) or not stat.S_ISREG(before_path.st_mode):
            raise ValueError("contract input must be a regular non-symlink file")
        file_fd = os.open(final_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=parent_fd)
        before_fd = os.fstat(file_fd)
        if not stat.S_ISREG(before_fd.st_mode) or not _same_file_identity(before_path, before_fd):
            raise ValueError("contract input changed while opening")
        chunks = []
        total = 0
        while True:
            chunk = os.read(file_fd, min(8192, _MAX_CONTRACT_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_CONTRACT_BYTES:
                raise ValueError(f"contract input exceeds {_MAX_CONTRACT_BYTES} bytes")
            chunks.append(chunk)
        after_fd = os.fstat(file_fd)
        if (not stat.S_ISREG(after_fd.st_mode)
                or not _same_file_identity(before_path, before_fd)
                or not _same_file_identity(before_fd, after_fd)):
            raise ValueError("contract input changed while being read")

        # Re-walk every parent from the pinned repository root to verify the path
        # still resolves through the same non-symlink directory chain.
        for parent, component, opened_fd, device, inode in directory_links:
            current = os.stat(component, dir_fd=parent, follow_symlinks=False)
            pinned = os.fstat(opened_fd)
            if (not stat.S_ISDIR(current.st_mode) or stat.S_ISLNK(current.st_mode)
                    or (current.st_dev, current.st_ino) != (device, inode)
                    or (pinned.st_dev, pinned.st_ino) != (device, inode)):
                raise ValueError("contract input parent path changed while being read")
        try:
            root_now = os.stat(repository_root, follow_symlinks=False)
            root_opened = os.fstat(root_fd)
        except OSError as exc:
            raise ValueError("repository root changed while reading contract input") from exc
        if ((root_now.st_dev, root_now.st_ino) != (root_opened.st_dev, root_opened.st_ino)
                or stat.S_ISLNK(root_now.st_mode)):
            raise ValueError("repository root changed while reading contract input")
        # This is deliberately the final filesystem identity check: a concurrent
        # replacement during parent revalidation must still be detected.
        final_fd = os.fstat(file_fd)
        final_path = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISREG(final_fd.st_mode) or not stat.S_ISREG(final_path.st_mode)
                or not _same_file_identity(before_path, final_fd)
                or not _same_file_identity(final_fd, final_path)):
            raise ValueError("contract input path changed before final validation")
        return _strict_contract_json(b"".join(chunks))
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for fd in reversed(directory_fds):
            os.close(fd)


def _read(path: Path) -> WorkItem:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"invalid JSON number: {value}")
    if path.is_symlink():
        raise ValueError("refusing to follow a symlinked work-item file")
    with path.open("r", encoding="utf-8") as stream:
        return work_item_from_dict(json.load(stream, object_pairs_hook=unique_object,
                                             parse_constant=reject_constant))


def _write_atomic(path: Path, item: WorkItem, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(work_item_to_dict(item)) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(name, path, follow_symlinks=False)
            os.unlink(name)
        else:
            os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _canonical_directory(path: Path, *, must_exist: bool) -> Path:
    absolute = Path(os.path.abspath(path))
    resolved = path.resolve(strict=must_exist)
    if absolute != resolved:
        raise ValueError("work-item directory must not contain symlinked or mismatched path components")
    if must_exist and not stat.S_ISDIR(path.stat().st_mode):
        raise ValueError("work-item directory is not a directory")
    return resolved


def _read_linked_parent(path: Path, expected_id: str) -> WorkItem:
    try:
        before_path = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValueError(f"linked parent does not exist: {expected_id}") from exc
    if stat.S_ISLNK(before_path.st_mode) or not stat.S_ISREG(before_path.st_mode):
        raise ValueError(f"linked parent must be a regular non-symlink file: {expected_id}")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before_fd = os.fstat(fd)
        if (not stat.S_ISREG(before_fd.st_mode)
                or (before_fd.st_dev, before_fd.st_ino) != (before_path.st_dev, before_path.st_ino)):
            raise ValueError(f"linked parent changed while opening: {expected_id}")
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_WORK_ITEM_BYTES:
                raise ValueError("linked parent work item exceeds bounded size")
            chunks.append(chunk)
        after_fd = os.fstat(fd)
        after_path = os.lstat(path)
        if ((before_fd.st_dev, before_fd.st_ino, before_fd.st_size, before_fd.st_mtime_ns)
                != (after_fd.st_dev, after_fd.st_ino, after_fd.st_size, after_fd.st_mtime_ns)
                or (after_fd.st_dev, after_fd.st_ino) != (after_path.st_dev, after_path.st_ino)
                or stat.S_ISLNK(after_path.st_mode)):
            raise ValueError(f"linked parent changed while being read: {expected_id}")
    finally:
        os.close(fd)

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in linked parent: {key}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"invalid JSON number in linked parent: {value}")

    try:
        raw = b"".join(chunks).decode("utf-8")
        item = work_item_from_dict(json.loads(raw, object_pairs_hook=unique_object,
                                              parse_constant=reject_constant))
        validate_work_item(item)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError) as exc:
        raise ValueError(f"linked parent JSON is invalid: {expected_id}") from exc
    if item.work_item_id != expected_id:
        raise ValueError(f"linked parent ID does not match its canonical filename: {expected_id}")
    return item


def _item_from_contract(args: argparse.Namespace, work_type: WorkItemType,
                        parent_epic: str, parent_feature: str,
                        repository_root: Path) -> WorkItem:
    payload = _read_contract_input(args.contract_json, repository_root)
    item = WorkItem(
        work_item_id=args.work_item_id, type=work_type, parent_epic=parent_epic,
        parent_feature=parent_feature, title=args.title,
        priority=payload.get("priority", ""),
        business_goal=payload.get("business_goal", ""),
        current_behavior=payload.get("current_behavior", ""),
        expected_behavior=payload.get("expected_behavior", ""),
        in_scope=tuple(payload.get("in_scope", ())),
        out_of_scope=tuple(payload.get("out_of_scope", ())),
        dependencies=tuple(payload.get("dependencies", ())),
        acceptance_criteria=tuple(payload.get("acceptance_criteria", ())),
        safety_constraints=tuple(payload.get("safety_constraints", ())),
        architecture_impact=payload.get("architecture_impact", ""),
        allowed_paths=tuple(payload.get("allowed_paths", ())),
        forbidden_paths=tuple(payload.get("forbidden_paths", ())),
        expected_tests=tuple(payload.get("expected_tests", ())),
        qa_attack_plan=tuple(payload.get("qa_attack_plan", ())),
        uat_criteria=tuple(payload.get("uat_criteria", ())),
        release_gates=tuple(payload.get("release_gates", ())),
        rollback_plan=payload.get("rollback_plan", ""),
        required_ci_checks=tuple(payload.get("required_ci_checks", ())),
        extensions=payload.get("extensions", {}),
    )
    try:
        validate_work_item(item, complete=True)
    except RecursionError as exc:
        raise ValueError("contract input nesting exceeds supported validation depth") from exc
    return item


def _create_work_item(args: argparse.Namespace) -> WorkItem:
    if not isinstance(args.work_item_id, str) or not _WORK_ITEM_ID_RE.fullmatch(args.work_item_id):
        raise ValueError("work_item_id must be a strict uppercase slug")
    if args.path.name != f"{args.work_item_id}.json":
        raise ValueError("destination filename must match work_item_id")

    work_type = WorkItemType(args.type)
    contract_json = getattr(args, "contract_json", None)
    if work_type in {WorkItemType.EPIC, WorkItemType.FEATURE}:
        if contract_json is not None:
            raise ValueError("--contract-json is only supported for linked STORY, BUG, and TASK")
    elif contract_json is None:
        raise ValueError(f"{work_type.value} requires --contract-json; see create --help for migration")
    parent_epic = args.parent_epic
    parent_feature = args.parent_feature
    if work_type == WorkItemType.EPIC:
        if parent_epic is not None or parent_feature is not None:
            raise ValueError("EPIC must not specify parent IDs")
        parent_epic = ""
        parent_feature = ""
    elif work_type == WorkItemType.FEATURE:
        if parent_epic is None or parent_feature is not None:
            raise ValueError("FEATURE requires --parent-epic and does not accept --parent-feature")
        parent_feature = ""
    else:
        if parent_epic is None or parent_feature is None:
            raise ValueError(f"{work_type.value} requires --parent-epic and --parent-feature")

    for name, value in (("parent_epic", parent_epic), ("parent_feature", parent_feature)):
        if value not in (None, "") and (not isinstance(value, str) or not _WORK_ITEM_ID_RE.fullmatch(value)):
            raise ValueError(f"{name} must be a strict uppercase slug")

    repository_root = Path.cwd().resolve(strict=True)
    expected_directory = (repository_root / "governance" / "evidence" / "work_items")
    directory = _canonical_directory(expected_directory, must_exist=False)
    supplied_path = Path(os.path.abspath(args.path))
    expected_path = work_item_path_for_id(args.work_item_id, root=repository_root)
    if supplied_path != expected_path or directory != expected_directory:
        raise ValueError("destination must be the canonical repository work-items path")
    if contract_json is not None:
        if not isinstance(contract_json, str):
            raise ValueError("--contract-json must be a repository-relative path")
        item = _item_from_contract(args, work_type, parent_epic, parent_feature, repository_root)
    else:
        item = WorkItem(work_item_id=args.work_item_id, type=work_type,
                        parent_epic=parent_epic, parent_feature=parent_feature, title=args.title)

    # Validate the new linked skeleton before creating directories, locks, or files.
    if work_type != WorkItemType.EPIC:
        _canonical_directory(args.path.parent, must_exist=True)
    validate_work_item(item, complete=contract_json is not None)
    try:
        destination_info = os.lstat(args.path)
    except FileNotFoundError:
        destination_info = None
    if destination_info is not None:
        raise ValueError("refusing to overwrite an existing work-item path")
    return item


def _create_linked_item_with_parent_locks(args: argparse.Namespace, item: WorkItem) -> None:
    """Lock and revalidate parents through exclusive creation.

    This serializes cooperating CLI writers only. A same-user writer that
    directly replaces files while ignoring advisory locks remains out of scope.
    """
    root = Path.cwd().resolve(strict=True)
    destination = work_item_path_for_id(item.work_item_id, root=root)
    parent_ids = sorted({value for value in (item.parent_epic, item.parent_feature) if value})
    parent_paths = [work_item_path_for_id(parent_id, root=root) for parent_id in parent_ids]
    with ExitStack() as stack:
        for parent_path in parent_paths:
            lock_path = parent_path.with_name(parent_path.name + ".lock")
            stack.enter_context(locked_sidecar(lock_path, create=False))
        parents = {parent_id: _read_linked_parent(path, parent_id)
                   for parent_id, path in zip(parent_ids, parent_paths)}
        if item.type == WorkItemType.FEATURE:
            epic = parents[item.parent_epic]
            if epic.type != WorkItemType.EPIC or epic.parent_epic or epic.parent_feature:
                raise ValueError("parent_epic must identify a canonical EPIC")
        elif item.type != WorkItemType.EPIC:
            epic = parents[item.parent_epic]
            feature = parents[item.parent_feature]
            if (epic.type != WorkItemType.EPIC or epic.parent_epic or epic.parent_feature
                    or feature.type != WorkItemType.FEATURE or feature.parent_feature
                    or feature.parent_epic != item.parent_epic):
                raise ValueError("parent_feature must be a FEATURE linked to the selected EPIC")

        destination_lock = destination.with_name(destination.name + ".lock")
        with locked_sidecar(destination_lock, create=True):
            try:
                os.lstat(destination)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("refusing to overwrite an existing work-item path")
            _write_atomic(destination, item, exclusive=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tradebot-delivery")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser(
        "create", help="create an item under governance/evidence/work_items",
        description=("Create a linked item in the canonical repository directory. FEATURE requires "
                     "--parent-epic; STORY/BUG/TASK require both parent flags and --contract-json "
                     "with a complete bounded contract. EPIC/FEATURE keep no-contract behavior. "
                     "Creation validates structure only and does not grant approval or execution "
                     "authority. Existing parent .json.lock sidecars are required. Migrate legacy "
                     "items into the canonical directory and initialize their sidecars before linking."))
    create.add_argument("path", type=Path)
    create.add_argument("work_item_id")
    create.add_argument("type", choices=[x.value for x in WorkItemType])
    create.add_argument("title")
    create.add_argument("--parent-epic")
    create.add_argument("--parent-feature")
    create.add_argument("--contract-json", metavar="REPO_RELATIVE_PATH",
                        help=("strict UTF-8 contract JSON beneath the current repository root "
                              "(required for STORY/BUG/TASK; maximum 65,536 bytes)"))
    validate = sub.add_parser(
        "validate", help="structural validation; does not authorize research capture")
    validate.add_argument("path", type=Path)
    for name in ("readiness", "allowed-next-states"):
        p = sub.add_parser(name)
        p.add_argument("path", type=Path)
    status = sub.add_parser("research-status", help="read-only local research-capture status")
    status.add_argument("work_item_id")
    status.add_argument("--json", action="store_true", required=True)
    preflight = sub.add_parser("research-preflight", help="append a local route-preflight record")
    preflight.add_argument("path", type=Path)
    preflight.add_argument("route_ref")
    preflight.add_argument("request_scope", choices=("DOCS_ONLY", "CANDIDATE_METADATA"))
    preflight.add_argument("scope_ref")
    preflight.add_argument("route_class", choices=("STATIC_METADATA", "METADATA_API", "DATA_API", "PAYLOAD"))
    preflight.add_argument("result", choices=("PASS", "BLOCK"))
    preflight.add_argument("--evidence-ref", action="append", default=[])
    preflight.add_argument("--reason-code", default="NONE",
                           choices=("NONE", "UNVERIFIED", "INVALID_REFERENCE", "MISSING_EVIDENCE", "CONTRACT_DRIFT", "UNKNOWN"))
    prepare = sub.add_parser("research-prepare", help="append a local request-prepared record; makes no request")
    prepare.add_argument("path", type=Path)
    prepare.add_argument("request_id")
    prepare.add_argument("route_preflight_event_id")
    prepare.add_argument("request_scope", choices=("DOCS_ONLY", "CANDIDATE_METADATA"))
    prepare.add_argument("scope_ref")
    prepare.add_argument("request_class", choices=("STATIC_METADATA", "METADATA_API"))
    result = sub.add_parser("research-result", help="append a local result record; makes no request")
    result.add_argument("path", type=Path)
    result.add_argument("request_id")
    result.add_argument("prepared_event_id")
    result.add_argument("result_status", choices=("COMPLETED", "ABORTED", "UNKNOWN"))
    result.add_argument("access_category", choices=("NONE", "STATIC_METADATA", "METADATA_API", "DATA_API", "PAYLOAD", "UNKNOWN"))
    result.add_argument("--http-status", type=int)
    result.add_argument("--mime")
    result.add_argument("--bytes", type=int, dest="byte_count")
    result.add_argument("--redirect", choices=("true", "false"))
    transition = sub.add_parser("transition")
    transition.add_argument("path", type=Path)
    transition.add_argument("target", choices=[x.value for x in DeliveryState])
    transition.add_argument("--role", required=True, choices=[x.value for x in DeliveryRole])
    transition.add_argument("--actor", required=True)
    transition.add_argument("--timestamp", required=True, help="ISO-8601 with timezone")
    transition.add_argument("--reason", required=True)
    transition.add_argument("--evidence-id", action="append", default=[])
    evidence = sub.add_parser("add-evidence")
    evidence.add_argument("path", type=Path)
    evidence.add_argument("evidence_id")
    evidence.add_argument("evidence_type", choices=[x.value for x in EvidenceType])
    evidence.add_argument("--role", required=True, choices=[x.value for x in DeliveryRole])
    evidence.add_argument("--actor", required=True)
    evidence.add_argument("--timestamp", required=True)
    evidence.add_argument("--status", default="PASS", choices=[x.value for x in EvidenceStatus])
    evidence.add_argument("--summary", required=True)
    evidence.add_argument("--ref", action="append", required=True)
    evidence.add_argument("--check", action="append", default=[], metavar="NAME=STATUS")
    defect = sub.add_parser("add-defect")
    defect.add_argument("path", type=Path)
    defect.add_argument("defect_id")
    defect.add_argument("severity", choices=[x.value for x in DefectSeverity])
    defect.add_argument("title")
    defect.add_argument("--role", required=True,
                        choices=[DeliveryRole.QA_ENGINEER.value, DeliveryRole.UAT_REVIEWER.value])
    defect.add_argument("--actor", required=True)
    defect.add_argument("--timestamp", required=True)
    defect.add_argument("--reason", required=True)
    defect.add_argument("--step", action="append", required=True)
    defect.add_argument("--expected", required=True)
    defect.add_argument("--actual", required=True)
    defect.add_argument("--evidence-id", action="append", required=True)
    defect_update = sub.add_parser("advance-defect")
    defect_update.add_argument("path", type=Path)
    defect_update.add_argument("defect_id")
    defect_update.add_argument("target", choices=[x.value for x in DefectStatus])
    defect_update.add_argument("--role", required=True, choices=[x.value for x in DeliveryRole])
    defect_update.add_argument("--actor", required=True)
    defect_update.add_argument("--timestamp", required=True)
    defect_update.add_argument("--reason", required=True)
    defect_update.add_argument("--evidence-ref", default="")
    defect_update.add_argument("--regression-result", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "research-status":
            status_result, exit_code = research_status(args.work_item_id)
            print(json.dumps(status_result, sort_keys=True))
            return exit_code
        if args.command == "create":
            item = _create_work_item(args)
            expected_directory = Path.cwd() / "governance" / "evidence" / "work_items"
            if not expected_directory.is_dir():
                raise ValueError("canonical repository work-items directory must already exist")
            _create_linked_item_with_parent_locks(args, item)
            print(args.path)
            return 0
        if args.command in {"validate", "readiness", "allowed-next-states"}:
            _, item = read_only_work_item_snapshot(args.path)
            orchestrator = DeliveryOrchestrator(item)
            if args.command == "validate":
                drift = orchestrator.research_contract_drift
                print(json.dumps({"valid": not drift, "scope": "structural_only",
                                  "research_contract_drift": drift,
                                  "research_capture_authorized": False,
                                  "work_item_id": item.work_item_id,
                                  "state": item.current_state.value}, sort_keys=True))
                return 1 if drift else 0
            if args.command == "readiness":
                print(json.dumps(orchestrator.readiness(), sort_keys=True))
            else:
                print(json.dumps(orchestrator.allowed_next_states()))
            return 0
        # Serialize local writers so a stale concurrent reader cannot overwrite
        # an update. The lock protects only this CLI's cooperating processes.
        lock_path = args.path.with_name(args.path.name + ".lock")
        with locked_sidecar(lock_path, create=True) as lock_fd:
            raw, item, _ = _read_canonical(args.path)
            orchestrator = DeliveryOrchestrator(item)
            if args.command == "transition":
                updated = orchestrator.transition(args.target, acting_role=args.role, actor=args.actor,
                                                  timestamp=args.timestamp, reason=args.reason,
                                                  evidence_ids=args.evidence_id)
                persist_work_item(args.path, lock_fd, raw, item, updated, "LIFECYCLE_UPDATE")
                print(updated.current_state.value)
            elif args.command == "add-evidence":
                checks = []
                for pair in args.check:
                    if "=" not in pair:
                        raise ValueError("--check must use NAME=STATUS")
                    checks.append(tuple(pair.split("=", 1)))
                ev = Evidence(args.evidence_id, item.work_item_id, EvidenceType(args.evidence_type),
                              DeliveryRole(args.role), args.actor, args.timestamp,
                              EvidenceStatus(args.status), args.summary, tuple(args.ref),
                              check_results=tuple(checks))
                updated = orchestrator.add_evidence(ev)
                persist_work_item(args.path, lock_fd, raw, item, updated, "EVIDENCE_UPDATE")
                print(args.evidence_id)
            elif args.command == "add-defect":
                item_defect = Defect(args.defect_id, item.work_item_id,
                                     DefectSeverity(args.severity), args.title,
                                     tuple(args.step), args.expected, args.actual,
                                     tuple(args.evidence_id))
                updated = orchestrator.add_defect(item_defect, actor_role=DeliveryRole(args.role),
                                                   actor=args.actor, timestamp=args.timestamp,
                                                   reason=args.reason)
                persist_work_item(args.path, lock_fd, raw, item, updated, "DEFECT_UPDATE")
                print(args.defect_id)
            elif args.command == "advance-defect":
                updated = orchestrator.advance_defect(args.defect_id, DefectStatus(args.target),
                                                       actor_role=DeliveryRole(args.role), actor=args.actor,
                                                       timestamp=args.timestamp, reason=args.reason,
                                                       evidence_ref=args.evidence_ref,
                                                       regression_result=args.regression_result)
                persist_work_item(args.path, lock_fd, raw, item, updated, "HISTORY_UPDATE")
                print(args.target)
            elif args.command in {"research-preflight", "research-prepare", "research-result"}:
                if args.command == "research-preflight":
                    payload = {
                        "route_ref": args.route_ref, "request_scope": args.request_scope,
                        "scope_ref": args.scope_ref, "route_class": args.route_class,
                        "result": args.result, "evidence_refs": args.evidence_ref,
                        "reason_code": args.reason_code,
                    }
                    kind = "ROUTE_PREFLIGHT"
                elif args.command == "research-prepare":
                    payload = {
                        "request_id": args.request_id,
                        "route_preflight_event_id": args.route_preflight_event_id,
                        "request_scope": args.request_scope, "scope_ref": args.scope_ref,
                        "request_class": args.request_class,
                    }
                    kind = "REQUEST_PREPARED"
                else:
                    payload = {
                        "request_id": args.request_id, "prepared_event_id": args.prepared_event_id,
                        "result_status": args.result_status, "access_category": args.access_category,
                    }
                    if args.http_status is not None:
                        payload["http_status"] = args.http_status
                    if args.mime is not None:
                        payload["mime"] = args.mime
                    if args.byte_count is not None:
                        payload["bytes"] = args.byte_count
                    if args.redirect is not None:
                        payload["redirect"] = args.redirect == "true"
                    kind = "REQUEST_RESULT"
                try:
                    event = make_event(item, kind, payload)
                    updated = append_event(args.path, lock_fd, event)
                except TransientClockRefusal as refusal:
                    result_json = transient_refusal(item, refusal.reason_code)
                    print(json.dumps(result_json, sort_keys=True))
                    return 4
                print(updated.research_evidence[-1]["event_id"])
            return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"tradebot-delivery: blocked: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
