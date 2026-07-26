from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .engine import ReplayDataError


@dataclass(frozen=True)
class PreparedOptionSource:
    root: Path
    source_path: Path
    source_kind: str
    source_sha256: str
    extracted: bool
    temporary_root: Path | None = None

    def cleanup(self) -> None:
        if self.temporary_root is not None:
            shutil.rmtree(self.temporary_root, ignore_errors=True)


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.infolist():
        member_path = destination / member.filename
        try:
            member_path.resolve().relative_to(destination_resolved)
        except ValueError as exc:
            raise ReplayDataError(f"unsafe_zip_member:{member.filename}") from exc
        if member.is_dir():
            member_path.mkdir(parents=True, exist_ok=True)
            continue
        member_path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, member_path.open("wb") as target:
            shutil.copyfileobj(source, target)


def _discover_dataset_root(extracted_root: Path) -> Path:
    candidates = []
    if (extracted_root / "raw" / "responses").is_dir():
        candidates.append(extracted_root)
    for child in extracted_root.iterdir():
        if child.is_dir() and (child / "raw" / "responses").is_dir():
            candidates.append(child)
    if len(candidates) != 1:
        raise ReplayDataError(
            "option_dataset_root_ambiguous_or_missing:"
            + ",".join(str(path) for path in sorted(candidates))
        )
    return candidates[0]


def prepare_option_source(path: Path) -> PreparedOptionSource:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise ReplayDataError(f"option_source_missing:{source}")
    if source.is_dir():
        if not (source / "raw" / "responses").is_dir():
            raise ReplayDataError(f"raw_response_root_missing:{source / 'raw' / 'responses'}")
        return PreparedOptionSource(
            root=source,
            source_path=source,
            source_kind="directory",
            source_sha256="DIRECTORY_NOT_SINGLE_FILE",
            extracted=False,
        )
    if source.suffix.lower() != ".zip":
        raise ReplayDataError(f"unsupported_option_source:{source.suffix}")
    temporary_root = Path(tempfile.mkdtemp(prefix="tradebot-expired-options-"))
    try:
        with zipfile.ZipFile(source) as archive:
            _safe_extract(archive, temporary_root)
        root = _discover_dataset_root(temporary_root)
        return PreparedOptionSource(
            root=root,
            source_path=source,
            source_kind="zip",
            source_sha256=sha256_file(source),
            extracted=True,
            temporary_root=temporary_root,
        )
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
