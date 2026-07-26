from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

_ROOT_ID_RE = re.compile(r"^[A-Z0-9_]+$")
_SOURCE_SUFFIXES = {
    ".arrow",
    ".csv",
    ".feather",
    ".json",
    ".jsonl",
    ".npy",
    ".npz",
    ".parquet",
    ".pickle",
    ".pkl",
    ".zip",
}
_SOURCE_TOKENS = (
    "candidate",
    "dataset",
    "execution_entry_trace",
    "inventory",
    "ledger",
    "manifest",
    "market_data",
    "option_tick",
    "replay",
    "signal",
    "source",
    "strategy_validation",
)
_DENIED_PATH_TOKENS = (
    "outcome",
    "realized_pnl",
    "pnl",
    "profit",
    "loss",
    "future_return",
    "forward_return",
    "trade_result",
    "holdout",
    "post_trade",
)
EXCLUDED_DIRECTORY_NAMES = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
)
_EXCLUDED_DIRECTORY_NAME_SET = frozenset(EXCLUDED_DIRECTORY_NAMES)
_NOT_OPENED_DIGEST = "NOT_OPENED_BY_POLICY"


class LocalRootScanError(RuntimeError):
    """Base error for exhaustive declared-root inspection."""


class InvalidRootSpecError(LocalRootScanError):
    """A root identifier/path binding is malformed."""


class RootMissingError(LocalRootScanError):
    """A declared root is absent or is not a directory."""


class DuplicateResolvedRootError(LocalRootScanError):
    """Two root identifiers point to the same physical directory."""


class OverlappingResolvedRootError(LocalRootScanError):
    """Nested roots would double-count the same filesystem subtree."""


class UnsupportedFilesystemEntryError(LocalRootScanError):
    """A symlink or non-regular filesystem entry prevents exhaustive proof."""


class RootPermissionError(LocalRootScanError):
    """A declared root cannot be read exhaustively."""


@dataclass(frozen=True)
class RootSpec:
    root_id: str
    path: Path


def parse_root_spec(value: str) -> RootSpec:
    root_id, separator, raw_path = value.partition("=")
    if not separator or not root_id or not raw_path:
        raise InvalidRootSpecError("root spec must use ROOT_ID=/absolute/or/relative/path")
    if not _ROOT_ID_RE.fullmatch(root_id):
        raise InvalidRootSpecError(f"invalid root_id:{root_id}")
    return RootSpec(root_id=root_id, path=Path(raw_path).expanduser())


def _normalized_path(value: str) -> str:
    return value.casefold().replace("-", "_").replace(" ", "_")


def is_outcome_or_pnl_path(relative_path: str) -> bool:
    normalized = _normalized_path(relative_path)
    return any(token in normalized for token in _DENIED_PATH_TOKENS)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except PermissionError as exc:
        raise RootPermissionError(f"candidate_unreadable:{path}") from exc
    return digest.hexdigest()


def classify_source_candidate(relative_path: str) -> str | None:
    lowered = _normalized_path(relative_path)
    suffix = Path(lowered).suffix
    if lowered.endswith("execution_entry_trace.jsonl"):
        return "EXECUTION_TRACE"
    if "signal" in lowered or "ledger" in lowered:
        return "SIGNAL_OR_LEDGER_ARTIFACT"
    if "replay" in lowered or suffix == ".zip":
        return "REPLAY_ARCHIVE_OR_INPUT"
    if "manifest" in lowered or "inventory" in lowered or "source" in lowered:
        return "SOURCE_MANIFEST_OR_INVENTORY"
    if suffix in {".parquet", ".arrow", ".feather", ".npy", ".npz"}:
        return "DATA_ARTIFACT"
    if suffix in _SOURCE_SUFFIXES and any(token in lowered for token in _SOURCE_TOKENS):
        return "STRUCTURED_AUTHORITY_CANDIDATE"
    return None


def _validate_roots(root_specs: Sequence[RootSpec]) -> list[tuple[RootSpec, Path]]:
    if not root_specs:
        raise InvalidRootSpecError("at least one declared root is required")
    seen_ids: set[str] = set()
    seen_paths: dict[Path, str] = {}
    resolved: list[tuple[RootSpec, Path]] = []
    for spec in root_specs:
        if spec.root_id in seen_ids:
            raise InvalidRootSpecError(f"duplicate root_id:{spec.root_id}")
        seen_ids.add(spec.root_id)
        if spec.path.is_symlink() or not spec.path.is_dir():
            raise RootMissingError(f"root_absent_or_not_directory:{spec.root_id}")
        try:
            physical = spec.path.resolve(strict=True)
        except OSError as exc:
            raise RootMissingError(f"root_unresolvable:{spec.root_id}") from exc
        prior = seen_paths.get(physical)
        if prior is not None:
            raise DuplicateResolvedRootError(
                f"duplicate_resolved_root:{prior}:{spec.root_id}"
            )
        for existing_path, existing_id in seen_paths.items():
            if physical.is_relative_to(existing_path) or existing_path.is_relative_to(
                physical
            ):
                raise OverlappingResolvedRootError(
                    f"overlapping_resolved_roots:{existing_id}:{spec.root_id}"
                )
        seen_paths[physical] = spec.root_id
        resolved.append((spec, physical))
    return sorted(resolved, key=lambda item: item[0].root_id)


def _iter_entries(
    root_id: str, root: Path
) -> Iterable[tuple[str, os.DirEntry[str], bool]]:
    def walk(
        directory: Path, prefix: Path
    ) -> Iterable[tuple[str, os.DirEntry[str], bool]]:
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except PermissionError as exc:
            raise RootPermissionError(
                f"directory_unreadable:{root_id}:{prefix.as_posix()}"
            ) from exc
        for entry in entries:
            relative = (prefix / entry.name).as_posix()
            excluded_directory = False
            try:
                if entry.is_dir(follow_symlinks=False):
                    excluded_directory = entry.name in _EXCLUDED_DIRECTORY_NAME_SET
                    yield relative, entry, excluded_directory
                    if not excluded_directory:
                        yield from walk(Path(entry.path), prefix / entry.name)
                elif entry.is_symlink():
                    raise UnsupportedFilesystemEntryError(
                        f"symlink_prevents_exhaustive_scan:{root_id}:{relative}"
                    )
                elif entry.is_file(follow_symlinks=False):
                    yield relative, entry, False
                else:
                    raise UnsupportedFilesystemEntryError(
                        f"special_entry_prevents_exhaustive_scan:{root_id}:{relative}"
                    )
            except PermissionError as exc:
                raise RootPermissionError(
                    f"entry_unreadable:{root_id}:{relative}"
                ) from exc

    yield from walk(root, Path())


def scan_declared_roots(
    root_specs: Sequence[RootSpec],
    *,
    expected_root_count: int = 27,
) -> dict[str, Any]:
    if expected_root_count <= 0:
        raise ValueError("expected_root_count must be positive")
    resolved_roots = _validate_roots(root_specs)
    if len(resolved_roots) != expected_root_count:
        raise InvalidRootSpecError(
            f"declared_root_count_mismatch:expected={expected_root_count}:actual={len(resolved_roots)}"
        )

    root_records: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    all_file_manifest = hashlib.sha256()
    candidate_identity_manifest = hashlib.sha256()
    excluded_directory_manifest = hashlib.sha256()
    total_file_count = 0
    total_directory_count = 0
    excluded_directory_count = 0
    denied_candidate_count = 0

    for spec, physical in resolved_roots:
        root_file_count = 0
        root_directory_count = 0
        root_excluded_directory_count = 0
        root_candidate_count = 0
        root_denied_candidate_count = 0
        root_manifest = hashlib.sha256()
        for relative, entry, excluded_directory in _iter_entries(spec.root_id, physical):
            try:
                stat_result = entry.stat(follow_symlinks=False)
            except PermissionError as exc:
                raise RootPermissionError(
                    f"entry_stat_failed:{spec.root_id}:{relative}"
                ) from exc
            mode = stat_result.st_mode
            if stat.S_ISDIR(mode):
                root_directory_count += 1
                total_directory_count += 1
                if excluded_directory:
                    root_excluded_directory_count += 1
                    excluded_directory_count += 1
                    excluded_directory_manifest.update(
                        f"{spec.root_id}\0{relative}\n".encode("utf-8")
                    )
                continue
            if not stat.S_ISREG(mode):
                raise UnsupportedFilesystemEntryError(
                    f"non_regular_entry:{spec.root_id}:{relative}"
                )
            size = stat_result.st_size
            identity_line = f"{spec.root_id}\0{relative}\0{size}\n".encode("utf-8")
            root_manifest.update(identity_line)
            all_file_manifest.update(identity_line)
            root_file_count += 1
            total_file_count += 1
            candidate_class = classify_source_candidate(relative)
            if candidate_class is None:
                continue

            denied = is_outcome_or_pnl_path(relative)
            digest: str | None = None
            content_opened = False
            authority_status = "REQUIRES_HUMAN_AUTHORITY_REVIEW"
            if denied:
                denied_candidate_count += 1
                root_denied_candidate_count += 1
                authority_status = "OUTCOME_OR_PNL_METADATA_ONLY_REQUIRES_SEPARATE_REVIEW"
            else:
                digest = _sha256_file(physical / Path(relative))
                content_opened = True

            candidate = {
                "candidate_id": f"{spec.root_id}:{relative}",
                "root_id": spec.root_id,
                "relative_path": relative,
                "size_bytes": size,
                "sha256": digest,
                "candidate_class": candidate_class,
                "content_opened": content_opened,
                "denied_by_policy": denied,
                "authority_status": authority_status,
            }
            candidates.append(candidate)
            manifest_digest = digest if digest is not None else _NOT_OPENED_DIGEST
            candidate_identity_manifest.update(
                (
                    f"{candidate['candidate_id']}\0{manifest_digest}\0"
                    f"{candidate_class}\0{int(denied)}\n"
                ).encode("utf-8")
            )
            root_candidate_count += 1
        root_records.append(
            {
                "root_id": spec.root_id,
                "root_path_sha256": hashlib.sha256(
                    str(physical).encode("utf-8")
                ).hexdigest(),
                "file_count": root_file_count,
                "directory_count": root_directory_count,
                "excluded_directory_count": root_excluded_directory_count,
                "candidate_count": root_candidate_count,
                "denied_outcome_or_pnl_candidate_count": root_denied_candidate_count,
                "file_identity_manifest_sha256": root_manifest.hexdigest(),
                "scan_complete": True,
            }
        )

    candidates.sort(key=lambda item: item["candidate_id"])
    groups_by_sha: dict[str, list[str]] = {}
    for candidate in candidates:
        digest = candidate.get("sha256")
        if isinstance(digest, str) and digest:
            groups_by_sha.setdefault(digest, []).append(candidate["candidate_id"])
    exact_duplicate_groups = [
        {
            "sha256": digest,
            "candidate_ids": sorted(candidate_ids),
            "candidate_count": len(candidate_ids),
        }
        for digest, candidate_ids in sorted(groups_by_sha.items())
        if len(candidate_ids) > 1
    ]

    return {
        "schema_version": "local_unresolved_source_audit_v1",
        "expected_root_count": expected_root_count,
        "declared_root_count": len(root_records),
        "root_records": root_records,
        "total_file_count": total_file_count,
        "total_directory_count": total_directory_count,
        "excluded_directory_names": list(EXCLUDED_DIRECTORY_NAMES),
        "excluded_directory_count": excluded_directory_count,
        "excluded_directory_path_manifest_sha256": excluded_directory_manifest.hexdigest(),
        "source_candidate_count": len(candidates),
        "denied_outcome_or_pnl_candidate_count": denied_candidate_count,
        "source_candidates": candidates,
        "exact_duplicate_group_count": len(exact_duplicate_groups),
        "exact_duplicate_groups": exact_duplicate_groups,
        "all_file_identity_manifest_sha256": all_file_manifest.hexdigest(),
        "candidate_identity_manifest_sha256": candidate_identity_manifest.hexdigest(),
        "candidate_limit": None,
        "scan_complete": True,
        "absolute_paths_published": False,
        "canonical_signal_source_count": 0,
        "canonical_dataset_source_count": 0,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
