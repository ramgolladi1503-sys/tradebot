from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    OPERATIONAL_EXCLUSIONS,
    sha256_file,
    sha256_text,
)
from .parquet_metadata import classify_parquet, inspect_parquet_footer, option_name_hint

DENIED_TOKENS = (
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
MANIFEST_TOKENS = (
    "manifest",
    "inventory",
    "instrument",
    "contract",
    "mapping",
    "metadata",
)
MAX_ZIP_PARQUET_MEMBER_BYTES = 128 * 1024 * 1024
OPTION_CLASSES = {
    "RAW_OPTION_TICK_DATASET",
    "OPTION_CONTRACT_DATASET",
    "NORMALIZED_OPTION_REPLAY_DATASET",
}


@dataclass(frozen=True)
class RootBinding:
    root_id: str
    path: Path
    allowed_candidate_classes: tuple[str, ...]


class InventoryError(RuntimeError):
    pass


class UnsafePathError(InventoryError):
    pass


def _is_denied(value: str) -> bool:
    normalized = value.casefold().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in DENIED_TOKENS)


def _is_manifest(value: str) -> bool:
    lowered = value.casefold()
    return Path(lowered).suffix in {".json", ".jsonl", ".csv", ".gz"} and any(
        token in lowered for token in MANIFEST_TOKENS
    )


def _path_date(value: str) -> str | None:
    for part in PurePosixPath(value).parts:
        if len(part) == 8 and part.isdigit():
            try:
                return datetime.strptime(part, "%Y%m%d").date().isoformat()
            except ValueError:
                return None
    return None


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise UnsafePathError(f"unsafe_archive_member:{name!r}")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafePathError(f"unsafe_archive_member:{name!r}")
    return path.as_posix()


def _archive_metadata(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(path.parts and path.parts[0] == "__MACOSX")
        or path.name.startswith("._")
        or path.name == ".DS_Store"
    )


def load_root_bindings(machine_manifest: Path) -> list[RootBinding]:
    payload = json.loads(machine_manifest.read_text(encoding="utf-8"))
    roots: list[RootBinding] = []
    seen: set[str] = set()
    resolved: list[tuple[str, Path]] = []
    for row in payload.get("roots", []):
        root_id = str(row["current_root_id"])
        if root_id in seen:
            raise InventoryError(f"duplicate_root_id:{root_id}")
        seen.add(root_id)
        path = Path(row["absolute_path"])
        if path.is_symlink() or not path.is_dir():
            raise InventoryError(f"invalid_root:{root_id}")
        physical = path.resolve(strict=True)
        for prior_id, prior in resolved:
            if (
                physical == prior
                or physical.is_relative_to(prior)
                or prior.is_relative_to(physical)
            ):
                raise InventoryError(f"overlapping_roots:{prior_id}:{root_id}")
        resolved.append((root_id, physical))
        roots.append(
            RootBinding(
                root_id,
                physical,
                tuple(map(str, row.get("allowed_candidate_classes", []))),
            )
        )
    if not roots:
        raise InventoryError("no_roots_in_machine_manifest")
    return roots


def _walk(root: RootBinding) -> Iterable[tuple[Path, str]]:
    for directory, dirnames, filenames in os.walk(root.path, followlinks=False):
        dirnames.sort()
        filenames.sort()
        kept: list[str] = []
        for name in dirnames:
            child = Path(directory) / name
            if name in OPERATIONAL_EXCLUSIONS:
                continue
            if child.is_symlink():
                raise UnsafePathError(
                    f"symlink_directory:{root.root_id}:"
                    f"{child.relative_to(root.path).as_posix()}"
                )
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = Path(directory) / name
            relative = path.relative_to(root.path).as_posix()
            if path.is_symlink():
                raise UnsafePathError(f"symlink_file:{root.root_id}:{relative}")
            if stat.S_IFMT(path.lstat().st_mode) != stat.S_IFREG or not path.is_file():
                raise UnsafePathError(f"non_regular_file:{root.root_id}:{relative}")
            yield path, relative


def _session_dates(
    footer: dict[str, Any], path_hint: str
) -> tuple[list[str], str]:
    footer_dates = sorted(
        value
        for value in {footer.get("footer_date_min"), footer.get("footer_date_max")}
        if value
    )
    if len(footer_dates) == 1:
        return footer_dates, "PARQUET_FOOTER_STATISTICS"
    path_date = _path_date(path_hint)
    if path_date:
        return [path_date], "PATH_HINT_ONLY"
    return [], "NOT_ESTABLISHED"


def _parquet_candidate(
    root: RootBinding, path: Path, relative: str
) -> dict[str, Any] | None:
    try:
        footer = inspect_parquet_footer(path, path_hint=relative)
    except Exception as exc:
        return {
            "candidate_id": f"{root.root_id}:{relative}",
            "root_id": root.root_id,
            "relative_path": relative,
            "candidate_class": "REJECTED_MALFORMED_PARQUET",
            "size_bytes": path.stat().st_size,
            "physical_sha256": sha256_file(path),
            "metadata_status": f"PARQUET_FOOTER_REJECTED:{type(exc).__name__}",
            "session_dates": [],
            "session_date_evidence": "NOT_ESTABLISHED",
            "allowed_class_filter_applied": False,
            "authority_status": "REJECTED",
        }
    candidate_class = footer.get("candidate_class")
    if candidate_class not in OPTION_CLASSES:
        return None
    dates, date_evidence = _session_dates(footer, relative)
    return {
        "candidate_id": f"{root.root_id}:{relative}",
        "root_id": root.root_id,
        "relative_path": relative,
        "candidate_class": candidate_class,
        "size_bytes": path.stat().st_size,
        "physical_sha256": sha256_file(path),
        "parquet_footer": footer,
        "session_dates": dates,
        "session_date_evidence": date_evidence,
        "allowed_class_filter_applied": False,
        "authority_status": "DISCOVERED_REQUIRES_DEEP_REVIEW",
    }


def _zip_candidates(
    root: RootBinding, path: Path, relative: str
) -> tuple[list[dict[str, Any]], int, int]:
    archive_sha = sha256_file(path)
    rows: list[dict[str, Any]] = []
    members_inspected = 0
    parquet_metadata_inspected = 0
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise InventoryError(f"invalid_zip:{root.root_id}:{relative}") from exc
    with archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            name = _safe_member_name(info.filename)
            members_inspected += 1
            if info.is_dir() or _archive_metadata(name) or _is_denied(name):
                continue
            if not name.casefold().endswith(".parquet") or not option_name_hint(name):
                continue
            record: dict[str, Any] = {
                "candidate_id": f"{root.root_id}:{relative}!{name}",
                "root_id": root.root_id,
                "relative_path": relative,
                "archive_member": name,
                "archive_sha256": archive_sha,
                "member_crc32": f"{info.CRC:08x}",
                "member_size_bytes": int(info.file_size),
                "allowed_class_filter_applied": False,
                "authority_status": "DISCOVERED_REQUIRES_DEEP_REVIEW",
            }
            if info.file_size > MAX_ZIP_PARQUET_MEMBER_BYTES:
                record.update(
                    {
                        "candidate_class": "UNRESOLVED_ARCHIVE_OPTION_MEMBER",
                        "session_dates": [],
                        "metadata_status": "MEMBER_TOO_LARGE_FOR_BOUNDED_INSPECTION",
                    }
                )
                rows.append(record)
                continue
            with archive.open(info) as handle:
                content = handle.read(MAX_ZIP_PARQUET_MEMBER_BYTES + 1)
            if len(content) != info.file_size:
                raise InventoryError(f"archive_member_size_mismatch:{name}")
            footer = inspect_parquet_footer(io.BytesIO(content), path_hint=name)
            parquet_metadata_inspected += 1
            candidate_class = footer.get("candidate_class")
            if candidate_class not in OPTION_CLASSES:
                candidate_class = "OPTION_MEMBER_SCHEMA_NOT_REPLAY_RELEVANT"
            dates, date_evidence = _session_dates(footer, name)
            record.update(
                {
                    "candidate_class": candidate_class,
                    "physical_sha256": hashlib.sha256(content).hexdigest(),
                    "parquet_footer": footer,
                    "session_dates": dates,
                    "session_date_evidence": date_evidence,
                }
            )
            rows.append(record)
    return rows, members_inspected, parquet_metadata_inspected


def build_inventory(machine_manifest: Path) -> dict[str, Any]:
    roots = load_root_bindings(machine_manifest)
    candidates: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    files_visited = 0
    parquet_files = 0
    parquet_metadata = 0
    zip_files = 0
    zip_members = 0
    root_records: list[dict[str, Any]] = []
    for root in sorted(roots, key=lambda item: item.root_id):
        root_files = 0
        for path, relative in _walk(root):
            files_visited += 1
            root_files += 1
            if _is_denied(relative):
                denied.append(
                    {
                        "candidate_id": f"{root.root_id}:{relative}",
                        "root_id": root.root_id,
                        "relative_path": relative,
                        "size_bytes": path.stat().st_size,
                        "content_opened": False,
                        "classification": "DENIED_OUTCOME_METADATA_ONLY",
                    }
                )
                continue
            suffix = path.suffix.casefold()
            if suffix == ".parquet":
                parquet_files += 1
                parquet_metadata += 1
                record = _parquet_candidate(root, path, relative)
                if record:
                    candidates.append(record)
            elif suffix == ".zip":
                zip_files += 1
                found, member_count, footer_count = _zip_candidates(
                    root, path, relative
                )
                candidates.extend(found)
                zip_members += member_count
                parquet_metadata += footer_count
            elif _is_manifest(relative):
                candidates.append(
                    {
                        "candidate_id": f"{root.root_id}:{relative}",
                        "root_id": root.root_id,
                        "relative_path": relative,
                        "candidate_class": "SOURCE_OR_INSTRUMENT_MANIFEST",
                        "size_bytes": path.stat().st_size,
                        "physical_sha256": sha256_file(path),
                        "content_opened": False,
                        "allowed_class_filter_applied": False,
                        "authority_status": "DISCOVERED_REQUIRES_DEEP_REVIEW",
                    }
                )
        root_records.append(
            {
                "root_id": root.root_id,
                "files_visited": root_files,
                "declared_allowed_candidate_classes": list(
                    root.allowed_candidate_classes
                ),
                "allowed_class_filter_applied": False,
            }
        )

    candidates.sort(key=lambda row: row["candidate_id"])
    denied.sort(key=lambda row: row["candidate_id"])
    groups: dict[str, list[str]] = {}
    for row in candidates:
        digest = row.get("physical_sha256")
        if digest:
            groups.setdefault(str(digest), []).append(row["candidate_id"])
    option_rows = [
        row for row in candidates if row.get("candidate_class") in OPTION_CLASSES
    ]
    session_dates = sorted(
        {session for row in option_rows for session in row.get("session_dates", [])}
    )
    return {
        "schema_version": "ce_pe_history_inventory_v1",
        "root_count": len(roots),
        "root_records": root_records,
        "files_visited": files_visited,
        "parquet_files_found": parquet_files,
        "parquet_metadata_inspected": parquet_metadata,
        "zip_files_inspected": zip_files,
        "zip_members_inspected": zip_members,
        "candidate_limit": None,
        "candidate_count": len(candidates),
        "option_candidate_count": len(option_rows),
        "candidate_identity_manifest_sha256": sha256_text(
            "".join(f"{row['candidate_id']}\n" for row in candidates)
        ),
        "candidates": candidates,
        "exact_duplicate_groups": sorted(
            sorted(ids) for ids in groups.values() if len(ids) > 1
        ),
        "denied_metadata_only_count": len(denied),
        "denied_metadata_only": denied,
        "valid_option_session_dates": session_dates,
        "valid_option_session_count": len(session_dates),
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "strategy_code_invoked": False,
        "backtests_run": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
