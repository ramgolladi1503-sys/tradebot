from __future__ import annotations

import hashlib
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import (
    EXPECTED_ARCHIVE_SHA256,
    ArchiveFormatError,
    ArchiveHashMismatchError,
    ArchiveMissingError,
    UnsafeArchiveError,
)

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_archive_metadata(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(path.parts and path.parts[0] == "__MACOSX")
        or path.name.startswith("._")
        or path.name == ".DS_Store"
    )


def oracle_archive_facts(
    path: Path,
    *,
    expected_sha256: str = EXPECTED_ARCHIVE_SHA256,
) -> dict[str, Any]:
    if not path.is_file():
        raise ArchiveMissingError(f"archive_missing:{path}")
    digest = _hash(path)
    if digest != expected_sha256:
        raise ArchiveHashMismatchError(
            f"archive_hash_mismatch:expected={expected_sha256}:actual={digest}"
        )

    names: list[str] = []
    metadata_count = 0
    content_file_count = 0
    content_directory_count = 0
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            for info in infos:
                name = info.filename
                member = PurePosixPath(name)
                if (
                    not name
                    or "\\" in name
                    or name.startswith("/")
                    or _DRIVE_RE.match(name)
                    or any(part in {"", ".", ".."} for part in member.parts)
                ):
                    raise UnsafeArchiveError(f"unsafe_member_path:{name!r}")
                mode = (info.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                if not info.is_dir() and kind not in {0, stat.S_IFREG}:
                    raise UnsafeArchiveError(f"non_regular_member:{name}")
                if info.flag_bits & 0x1:
                    raise UnsafeArchiveError(f"encrypted_member:{name}")
                normalized = member.as_posix()
                names.append(normalized)
                if _is_archive_metadata(normalized):
                    metadata_count += 1
                elif info.is_dir():
                    content_directory_count += 1
                else:
                    content_file_count += 1
    except zipfile.BadZipFile as exc:
        raise ArchiveFormatError("archive_not_valid_zip") from exc

    if len(names) != len(set(names)):
        raise UnsafeArchiveError("duplicate_member_names")
    if len({name.casefold() for name in names}) != len(names):
        raise UnsafeArchiveError("case_colliding_member_names")

    return {
        "archive_sha256": digest,
        "archive_size_bytes": path.stat().st_size,
        "member_count": len(names),
        "archive_metadata_member_count": metadata_count,
        "content_tree_member_count": len(names) - metadata_count,
        "content_file_member_count": content_file_count,
        "content_directory_member_count": content_directory_count,
        "member_name_manifest_sha256": hashlib.sha256(
            ("\n".join(sorted(names)) + "\n").encode("utf-8")
        ).hexdigest(),
        "zip_valid": True,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def reconcile_primary_oracle(
    primary: dict[str, Any],
    oracle: dict[str, Any],
) -> dict[str, Any]:
    exact_fields = (
        "archive_sha256",
        "archive_size_bytes",
        "member_count",
        "archive_metadata_member_count",
        "content_tree_member_count",
        "content_file_member_count",
        "content_directory_member_count",
    )
    checks = {
        field: primary.get(field) == oracle.get(field) for field in exact_fields
    }
    checks["zip_valid"] = (
        primary.get("zip_valid") is True and oracle.get("zip_valid") is True
    )
    checks["safety"] = all(
        primary.get(key) == oracle.get(key)
        for key in (
            "research_only",
            "read_only",
            "is_order_action",
            "broker_api_called",
            "allowed_for_live_execution",
        )
    )
    return {
        "status": "AGREEMENT" if all(checks.values()) else "DISAGREEMENT",
        "checks": checks,
    }
