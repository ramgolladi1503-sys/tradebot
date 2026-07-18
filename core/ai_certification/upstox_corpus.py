from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import pandas as pd


OHLC = {"open", "high", "low", "close"}
TIMESTAMP_NAMES = ("timestamp", "ts", "datetime", "date_time", "bar_start_timestamp")
QUOTE_NAMES = {"bid", "ask", "bid_qty", "ask_qty"}
PRICE_NAMES = {"ltp", "last_price", "price"}
FUTURE_MARKERS = ("FUT", "FUTURES", "NIFTY_F1", "BANKNIFTY_F1")


class CorpusError(ValueError):
    pass


@dataclass(frozen=True)
class CorpusEntry:
    path: str
    sha256: str
    size_bytes: int
    kind: str
    eligibility: str
    rows: int | None
    columns: tuple[str, ...]
    timestamp_column: str | None
    volume_sum: float | None
    instrument_identity: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class UpstoxCorpusManifest:
    schema_version: int
    source_path: str
    source_kind: str
    source_sha256: str | None
    files_scanned: int
    entries: tuple[CorpusEntry, ...]
    summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "entries": [asdict(entry) for entry in self.entries],
        }


def _sha256_stream(handle) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _sha256_path(path: Path) -> str:
    with path.open("rb") as handle:
        return _sha256_stream(handle)


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name and not path.is_absolute() and ".." not in path.parts)


def _normalized_columns(columns: Iterable[Any]) -> dict[str, str]:
    return {str(column).strip().lower(): str(column) for column in columns}


def _timestamp_column(columns: dict[str, str]) -> str | None:
    return next((columns[name] for name in TIMESTAMP_NAMES if name in columns), None)


def _future_identity(path: str, frame: pd.DataFrame | None) -> tuple[bool, str]:
    upper = path.upper()
    if any(marker in upper for marker in FUTURE_MARKERS):
        return True, "filename_future_marker"
    if frame is not None:
        for candidate in ("instrument_type", "segment", "instrument", "tradingsymbol", "symbol"):
            if candidate not in frame.columns:
                continue
            values = " ".join(str(value).upper() for value in frame[candidate].dropna().head(50))
            if "FUT" in values:
                return True, f"column:{candidate}"
    return False, "unconfirmed"


def _read_parquet(source: Path | io.BytesIO) -> tuple[pd.DataFrame, int]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - repository dependency includes pyarrow
        raise CorpusError("pyarrow is required for parquet inspection") from exc
    parquet = pq.ParquetFile(source)
    rows = int(parquet.metadata.num_rows)
    available = list(parquet.schema.names)
    wanted = [
        name
        for name in available
        if name.strip().lower()
        in OHLC
        | set(TIMESTAMP_NAMES)
        | {"volume", "vol", "ltp", "last_price", "price"}
        | QUOTE_NAMES
        | {"instrument_type", "segment", "instrument", "tradingsymbol", "symbol"}
    ]
    table = parquet.read(columns=wanted or available[: min(8, len(available))])
    frame = table.to_pandas()
    if len(frame) > 5000:
        frame = frame.head(5000)
    return frame, rows


def _volume_sum(frame: pd.DataFrame, columns: dict[str, str]) -> float | None:
    column = columns.get("volume") or columns.get("vol")
    if column is None:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    total = float(values.clip(lower=0.0).sum())
    return total if math.isfinite(total) else None


def _classify_parquet(
    *,
    name: str,
    sha256: str,
    size_bytes: int,
    source: Path | io.BytesIO,
) -> CorpusEntry:
    blockers: list[str] = []
    try:
        frame, rows = _read_parquet(source)
    except Exception as exc:
        return CorpusEntry(
            path=name,
            sha256=sha256,
            size_bytes=size_bytes,
            kind="parquet",
            eligibility="INVALID",
            rows=None,
            columns=(),
            timestamp_column=None,
            volume_sum=None,
            instrument_identity="unreadable",
            blockers=(f"parquet_read_error:{type(exc).__name__}",),
        )
    columns = _normalized_columns(frame.columns)
    timestamp = _timestamp_column(columns)
    volume = _volume_sum(frame, columns)
    is_future, identity = _future_identity(name, frame)
    has_ohlc = OHLC.issubset(columns)
    has_quotes = QUOTE_NAMES.issubset(columns)
    has_price = bool(PRICE_NAMES & set(columns))

    if timestamp is None:
        blockers.append("timestamp_missing")
    if rows <= 0:
        blockers.append("empty_parquet")
    if blockers:
        eligibility = "INVALID"
    elif has_ohlc:
        if volume is not None and volume > 0 and is_future:
            eligibility = "FUTURES_VOLUME_ELIGIBLE"
        elif volume is not None and volume > 0:
            eligibility = "POSITIVE_VOLUME_IDENTITY_UNCONFIRMED"
            blockers.append("futures_identity_unconfirmed")
        else:
            eligibility = "PRICE_STRUCTURE_ONLY"
            blockers.append("truthful_positive_volume_unavailable")
    elif has_quotes and has_price:
        eligibility = "OPTION_QUOTE_REPLAY_CANDIDATE"
    elif has_quotes or has_price:
        eligibility = "TICK_QUOTE_CONTROL"
    else:
        eligibility = "NON_MARKET_PARQUET"

    return CorpusEntry(
        path=name,
        sha256=sha256,
        size_bytes=size_bytes,
        kind="parquet",
        eligibility=eligibility,
        rows=rows,
        columns=tuple(sorted(columns)),
        timestamp_column=timestamp,
        volume_sum=volume,
        instrument_identity=identity,
        blockers=tuple(blockers),
    )


def _json_entry(name: str, sha256: str, size_bytes: int, payload: bytes) -> CorpusEntry:
    blockers: list[str] = []
    try:
        value = json.loads(payload.decode("utf-8"))
        columns = tuple(sorted(str(key).lower() for key in value)) if isinstance(value, dict) else ()
        eligibility = "MANIFEST_OR_METADATA"
    except (UnicodeDecodeError, json.JSONDecodeError):
        columns = ()
        eligibility = "INVALID"
        blockers.append("invalid_json")
    return CorpusEntry(
        path=name,
        sha256=sha256,
        size_bytes=size_bytes,
        kind="json",
        eligibility=eligibility,
        rows=None,
        columns=columns,
        timestamp_column=None,
        volume_sum=None,
        instrument_identity="metadata",
        blockers=tuple(blockers),
    )


def _directory_entries(root: Path) -> list[CorpusEntry]:
    entries: list[CorpusEntry] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        sha = _sha256_path(path)
        size = path.stat().st_size
        suffix = path.suffix.lower()
        if suffix in {".parquet", ".pq"}:
            entries.append(
                _classify_parquet(
                    name=relative,
                    sha256=sha,
                    size_bytes=size,
                    source=path,
                )
            )
        elif suffix == ".json":
            entries.append(_json_entry(relative, sha, size, path.read_bytes()))
    return entries


def _zip_entries(path: Path) -> list[CorpusEntry]:
    entries: list[CorpusEntry] = []
    with zipfile.ZipFile(path) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            name = info.filename
            if not _safe_member(name):
                entries.append(
                    CorpusEntry(
                        path=name,
                        sha256="",
                        size_bytes=int(info.file_size),
                        kind="unknown",
                        eligibility="INVALID",
                        rows=None,
                        columns=(),
                        timestamp_column=None,
                        volume_sum=None,
                        instrument_identity="unsafe_archive_member",
                        blockers=("unsafe_archive_path",),
                    )
                )
                continue
            suffix = PurePosixPath(name).suffix.lower()
            if suffix not in {".parquet", ".pq", ".json"}:
                continue
            payload = archive.read(info)
            sha = hashlib.sha256(payload).hexdigest()
            if suffix in {".parquet", ".pq"}:
                entries.append(
                    _classify_parquet(
                        name=name,
                        sha256=sha,
                        size_bytes=len(payload),
                        source=io.BytesIO(payload),
                    )
                )
            else:
                entries.append(_json_entry(name, sha, len(payload), payload))
    return entries


def build_upstox_corpus_manifest(source: str | Path) -> UpstoxCorpusManifest:
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise CorpusError(f"corpus source not found: {path}")
    if path.is_dir():
        entries = _directory_entries(path)
        source_kind = "directory"
        source_hash = None
    elif path.is_file() and path.suffix.lower() == ".zip":
        entries = _zip_entries(path)
        source_kind = "zip"
        source_hash = _sha256_path(path)
    else:
        raise CorpusError("corpus source must be a directory or ZIP archive")
    summary: dict[str, int] = {}
    for entry in entries:
        summary[entry.eligibility] = summary.get(entry.eligibility, 0) + 1
    return UpstoxCorpusManifest(
        schema_version=1,
        source_path=str(path),
        source_kind=source_kind,
        source_sha256=source_hash,
        files_scanned=len(entries),
        entries=tuple(entries),
        summary=dict(sorted(summary.items())),
    )


def write_upstox_corpus_manifest(
    manifest: UpstoxCorpusManifest,
    output: str | Path,
) -> Path:
    path = Path(output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
