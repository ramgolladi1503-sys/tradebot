from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import stat
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

EXPECTED_ARCHIVE_SHA256 = (
    "4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707"
)
MAX_STRUCTURED_MEMBER_BYTES = 5 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024
_DENIED_TOKENS = (
    "outcome",
    "label",
    "target",
    "future_return",
    "forward_return",
    "realized_pnl",
    "pnl",
    "profit",
    "loss",
    "trade_result",
    "holdout_result",
    "post_trade",
)
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_OPTION_FILE_RE = re.compile(r"(?:^|\s)(?:CE|PE)(?:\s|$)", re.IGNORECASE)


class TrackedArchiveAuditError(RuntimeError):
    """Base failure for the tracked replay archive audit."""


class ArchiveMissingError(TrackedArchiveAuditError):
    """The frozen archive path does not exist."""


class ArchiveHashMismatchError(TrackedArchiveAuditError):
    """The physical archive bytes do not match the frozen hash."""


class ArchiveFormatError(TrackedArchiveAuditError):
    """The ZIP structure or a permitted member cannot be read safely."""


class UnsafeArchiveError(TrackedArchiveAuditError):
    """The archive contains an unsafe or ambiguous member."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_denied_path(name: str) -> bool:
    normalized = name.lower().replace("-", "_").replace(" ", "_")
    return any(token in normalized for token in _DENIED_TOKENS)


def _is_archive_metadata(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(path.parts and path.parts[0] == "__MACOSX")
        or path.name.startswith("._")
        or path.name == ".DS_Store"
    )


def _normalized_member_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/") or _DRIVE_RE.match(name):
        raise UnsafeArchiveError(f"unsafe_member_path:{name!r}")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeArchiveError(f"unsafe_member_path:{name!r}")
    return path.as_posix()


def _member_kind(info: zipfile.ZipInfo, normalized_name: str) -> tuple[str, bool]:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if info.is_dir():
        return "DIRECTORY", False
    if file_type == stat.S_IFLNK:
        raise UnsafeArchiveError(f"symlink_member:{normalized_name}")
    if file_type not in {0, stat.S_IFREG}:
        raise UnsafeArchiveError(f"special_member:{normalized_name}")
    if info.flag_bits & 0x1:
        raise UnsafeArchiveError(f"encrypted_member:{normalized_name}")
    return "FILE", True


def _classify_candidate(name: str) -> str:
    lowered = name.lower()
    suffix = Path(lowered).suffix
    if any(token in lowered for token in ("signal", "ledger")):
        return "SIGNAL_LIKE_MEMBER"
    if any(
        token in lowered
        for token in ("instrument", "token", "mapping", "contract")
    ):
        return "INSTRUMENT_MAPPING_MEMBER"
    if suffix == ".parquet":
        return "MARKET_DATA_PARQUET_MEMBER"
    if suffix in {".json", ".jsonl", ".csv"} and any(
        token in lowered
        for token in ("manifest", "inventory", "summary", "metadata")
    ):
        return "SOURCE_MANIFEST_MEMBER"
    if suffix in {".json", ".jsonl", ".csv"}:
        return "STRUCTURED_MEMBER"
    return "OTHER_PERMITTED_MEMBER"


def _read_and_hash_member(
    handle: BinaryIO,
    size: int,
) -> tuple[str, bytes | None, int]:
    digest = hashlib.sha256()
    buffer = bytearray() if size <= MAX_STRUCTURED_MEMBER_BYTES else None
    total = 0
    while True:
        chunk = handle.read(_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
        if buffer is not None:
            buffer.extend(chunk)
    return digest.hexdigest(), bytes(buffer) if buffer is not None else None, total


def _structured_summary(
    name: str,
    content: bytes | None,
) -> dict[str, Any] | None:
    if content is None:
        return {
            "inspection": "SKIPPED_SIZE_LIMIT",
            "size_limit_bytes": MAX_STRUCTURED_MEMBER_BYTES,
        }
    suffix = Path(name.lower()).suffix
    if suffix == ".json":
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"inspection": "MALFORMED_JSON"}
        if isinstance(payload, dict):
            return {
                "inspection": "PARSED",
                "top_level_type": "object",
                "keys": sorted(map(str, payload)),
            }
        if isinstance(payload, list):
            keys = sorted(
                {
                    str(key)
                    for item in payload
                    if isinstance(item, dict)
                    for key in item
                }
            )
            return {
                "inspection": "PARSED",
                "top_level_type": "array",
                "record_count": len(payload),
                "object_keys": keys,
            }
        return {
            "inspection": "PARSED",
            "top_level_type": type(payload).__name__,
        }
    if suffix == ".jsonl":
        valid = 0
        invalid = 0
        keys: set[str] = set()
        for raw_line in content.splitlines():
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if isinstance(row, dict):
                valid += 1
                keys.update(map(str, row))
            else:
                invalid += 1
        return {
            "inspection": "PARSED",
            "valid_object_records": valid,
            "invalid_or_non_object_records": invalid,
            "object_keys": sorted(keys),
        }
    if suffix == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return {"inspection": "MALFORMED_CSV_ENCODING"}
        reader = csv.reader(io.StringIO(text))
        header = next(reader, [])
        row_count = sum(1 for _ in reader)
        return {
            "inspection": "PARSED",
            "header": header,
            "data_row_count": row_count,
        }
    return None


def _member_name_collisions(
    infos: list[zipfile.ZipInfo],
) -> tuple[list[str], list[list[str]]]:
    raw_names = [info.filename for info in infos]
    duplicate_names = sorted(
        name for name, count in Counter(raw_names).items() if count > 1
    )
    case_groups: dict[str, set[str]] = {}
    for name in raw_names:
        case_groups.setdefault(name.casefold(), set()).add(name)
    case_collisions = sorted(
        sorted(group) for group in case_groups.values() if len(group) > 1
    )
    return duplicate_names, case_collisions


def _date_component(name: str) -> str | None:
    for part in PurePosixPath(name).parts:
        if len(part) == 8 and part.isdigit():
            return part
    return None


def audit_tracked_archive(
    archive_path: Path,
    *,
    expected_sha256: str = EXPECTED_ARCHIVE_SHA256,
) -> dict[str, Any]:
    if not archive_path.is_file():
        raise ArchiveMissingError(f"archive_missing:{archive_path}")
    archive_sha256 = sha256_file(archive_path)
    if archive_sha256 != expected_sha256:
        raise ArchiveHashMismatchError(
            f"archive_hash_mismatch:expected={expected_sha256}:actual={archive_sha256}"
        )
    try:
        archive = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise ArchiveFormatError("archive_not_valid_zip") from exc

    with archive:
        infos = archive.infolist()
        duplicate_names, case_collisions = _member_name_collisions(infos)
        if duplicate_names or case_collisions:
            raise UnsafeArchiveError("ambiguous_member_names")

        members: list[dict[str, Any]] = []
        denied_count = 0
        opened_count = 0
        archive_metadata_count = 0
        signal_like_count = 0
        parquet_count = 0
        option_like_parquet_count = 0
        manifest_count = 0
        represented_dates: set[str] = set()
        parquet_dates: set[str] = set()

        for info in infos:
            normalized_name = _normalized_member_name(info.filename)
            member_type, should_open = _member_kind(info, normalized_name)
            archive_metadata = _is_archive_metadata(normalized_name)
            denied = not archive_metadata and _is_denied_path(normalized_name)
            if archive_metadata:
                candidate_class = "ARCHIVE_METADATA_MEMBER"
            elif denied:
                candidate_class = "DENIED_OUTCOME_BEARING_CONTENT"
            else:
                candidate_class = _classify_candidate(normalized_name)

            record: dict[str, Any] = {
                "member_path": normalized_name,
                "member_type": member_type,
                "compressed_size": info.compress_size,
                "uncompressed_size": info.file_size,
                "crc32": f"{info.CRC:08x}",
                "candidate_class": candidate_class,
                "content_opened": False,
                "archive_metadata": archive_metadata,
                "denied_by_policy": denied,
            }
            if archive_metadata:
                archive_metadata_count += 1
            elif denied:
                denied_count += 1
            elif should_open:
                try:
                    with archive.open(info, "r") as handle:
                        member_sha, content, bytes_read = _read_and_hash_member(
                            handle,
                            info.file_size,
                        )
                except (RuntimeError, zipfile.BadZipFile, OSError) as exc:
                    raise ArchiveFormatError(
                        f"member_read_failed:{normalized_name}"
                    ) from exc
                if bytes_read != info.file_size:
                    raise ArchiveFormatError(
                        "member_size_mismatch:"
                        f"{normalized_name}:expected={info.file_size}:actual={bytes_read}"
                    )
                record.update(
                    content_opened=True,
                    member_sha256=member_sha,
                    bytes_read=bytes_read,
                    structured_summary=_structured_summary(normalized_name, content),
                )
                opened_count += 1

            date_component = _date_component(normalized_name)
            if not archive_metadata and date_component:
                represented_dates.add(date_component)
            if candidate_class == "SIGNAL_LIKE_MEMBER":
                signal_like_count += 1
            elif candidate_class == "MARKET_DATA_PARQUET_MEMBER":
                parquet_count += 1
                if date_component:
                    parquet_dates.add(date_component)
                if _OPTION_FILE_RE.search(PurePosixPath(normalized_name).stem):
                    option_like_parquet_count += 1
            elif candidate_class == "SOURCE_MANIFEST_MEMBER":
                manifest_count += 1
            members.append(record)

    classification = (
        "ARCHIVE_REPLAY_INPUT_ONLY"
        if parquet_count or manifest_count
        else "ARCHIVE_NON_CANONICAL_SOURCE_MATERIAL"
    )
    reason_codes = ["archive_does_not_establish_pre_outcome_signal_authority"]
    if signal_like_count:
        reason_codes.append("signal_like_paths_require_independent_authority_evidence")
    if denied_count:
        reason_codes.append("outcome_bearing_members_excluded_without_content_read")
    if archive_metadata_count:
        reason_codes.append("appledouble_metadata_excluded_from_source_content")

    content_members = [item for item in members if not item["archive_metadata"]]
    return {
        "schema_version": "tracked_replay_archive_source_audit_v1",
        "archive_path": "runtime/upstox_candidate_replay.zip",
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_path.stat().st_size,
        "zip_valid": True,
        "member_count": len(members),
        "compressed_size_total": sum(item["compressed_size"] for item in members),
        "uncompressed_size_total": sum(
            item["uncompressed_size"] for item in members
        ),
        "duplicate_member_names": duplicate_names,
        "case_colliding_member_names": case_collisions,
        "opened_member_count": opened_count,
        "archive_metadata_member_count": archive_metadata_count,
        "content_tree_member_count": len(content_members),
        "content_file_member_count": sum(
            item["member_type"] == "FILE" for item in content_members
        ),
        "content_directory_member_count": sum(
            item["member_type"] == "DIRECTORY" for item in content_members
        ),
        "denied_outcome_member_count": denied_count,
        "signal_like_member_count": signal_like_count,
        "market_data_parquet_member_count": parquet_count,
        "option_like_parquet_member_count": option_like_parquet_count,
        "source_manifest_member_count": manifest_count,
        "represented_date_directory_count": len(represented_dates),
        "dates_with_parquet_member_count": len(parquet_dates),
        "canonical_signal_source_count": 0,
        "canonical_dataset_source_count": 0,
        "source_disposition": classification,
        "authority_reason_codes": sorted(reason_codes),
        "members": sorted(members, key=lambda item: item["member_path"]),
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
