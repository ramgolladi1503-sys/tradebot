from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore[assignment]

try:
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover
    pq = None  # type: ignore[assignment]


CENSUS_VERSION = "option_e2e_data_census_v4_1"
SUPPORTED_SUFFIXES = {".parquet", ".csv", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3", ".zip", ".tar", ".gz", ".tgz"}
ARCHIVE_SUFFIXES = {".zip", ".tar", ".tar.gz", ".tgz"}
SECRET_NAME_TOKENS = (
    ".env",
    "credential",
    "credentials",
    "secret",
    "access_token",
    "refresh_token",
    "apikey",
    "api_key",
)
DATE_COLUMNS = ("date", "session", "timestamp", "ts", "datetime", "time", "quote_ts", "quote_ts_epoch", "asof", "as_of")
OPTION_COLUMNS = (
    "tradingsymbol",
    "trading_symbol",
    "instrument_token",
    "instrument_key",
    "expiry",
    "expiry_date",
    "strike",
    "strike_price",
    "option_type",
    "instrument_type",
)
AUTHORITY_COLUMNS = (
    "lot_size",
    "tick_size",
    "expiry",
    "expiry_date",
    "strike",
    "strike_price",
    "tradingsymbol",
    "trading_symbol",
    "instrument_token",
    "instrument_key",
)
QUOTE_BID_COLUMNS = ("bid", "best_bid", "bid_price", "decision_bid")
QUOTE_ASK_COLUMNS = ("ask", "best_ask", "ask_price", "decision_ask")


@dataclass(frozen=True)
class RootProof:
    root: str
    exists: bool
    is_dir: bool
    is_file: bool
    file_count: int
    byte_count: int
    sha256: str
    proof_error: str


@dataclass(frozen=True)
class CensusFile:
    logical_path: str
    absolute_path: str
    root: str
    root_relative_path: str
    container_path: str
    archive_member_path: str
    suffix: str
    size_bytes: int
    sha256: str
    parse_status: str
    parse_error: str
    row_count: int | None
    columns: tuple[str, ...]
    date_min: str
    date_max: str
    classification: str
    authority_role: str
    point_in_time_status: str
    has_option_identity: bool
    has_expiry: bool
    has_strike: bool
    has_lot_size: bool
    has_bid_ask: bool
    has_quote_time: bool
    usable_for_option_e2e: bool
    blocker: str


@dataclass(frozen=True)
class CensusSummary:
    version: str
    roots_requested: tuple[str, ...]
    roots_existing: tuple[str, ...]
    files_scanned: int
    files_classified: int
    archive_files: int
    archive_members_scanned: int
    option_quote_files: int
    executable_quote_files: int
    instrument_master_files: int
    point_in_time_authority_files: int
    blocked_files: int
    parse_error_files: int
    census_sha256: str
    root_proof_sha256: str


def default_roots(repo_root: Path) -> tuple[Path, ...]:
    return (
        Path("/Users/madhuram/tradebot/.runtime/market_data"),
        Path("/Users/madhuram/tradebot/runtime/market_data"),
        Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay"),
        Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay"),
        Path("/Users/madhuram/tradebot/runtime/upstox_instruments"),
        Path("/Users/madhuram/tradebot/runtime/strategy_validation"),
        Path("/Users/madhuram/tradebot-data"),
        Path("/Users/madhuram/tradebot-ml-evidence"),
    )


def discover_retained_worktree_untracked_roots(repo_root: Path) -> tuple[Path, ...]:
    try:
        output = subprocess.check_output(["git", "worktree", "list", "--porcelain"], cwd=repo_root, text=True)
    except Exception:
        return ()
    roots: list[Path] = []
    current = ""
    for line in output.splitlines():
        if line.startswith("worktree "):
            current = line.removeprefix("worktree ")
            continue
        if line.startswith("branch ") and current:
            branch = line.removeprefix("branch refs/heads/")
            if any(token in branch for token in ("option-e2e", "all-strategy-option-e2e")):
                roots.extend(_untracked_data_roots(Path(current)))
            current = ""
    return tuple(dict.fromkeys(path for path in roots if path.exists()))


def build_census(roots: Iterable[Path], *, repo_root: Path | None = None) -> tuple[list[CensusFile], CensusSummary, list[RootProof]]:
    root_tuple = tuple(Path(root).expanduser() for root in roots)
    root_proofs = [_root_proof(root) for root in root_tuple]
    files = [_classify_file(path, root=_owning_root(path, root_tuple), repo_root=repo_root) for path in _discover_files(root_tuple)]
    records = [item for group in files for item in group]
    payload = [_portable_record(item) for item in records]
    root_payload = [asdict(item) for item in root_proofs]
    digest = _sha256_bytes(_canonical_json(payload))
    root_digest = _sha256_bytes(_canonical_json(root_payload))
    summary = CensusSummary(
        version=CENSUS_VERSION,
        roots_requested=tuple(str(path) for path in root_tuple),
        roots_existing=tuple(str(path) for path in root_tuple if path.exists()),
        files_scanned=len(records),
        files_classified=len(records),
        archive_files=sum(1 for item in records if not item.archive_member_path and _is_archive_path(Path(item.absolute_path))),
        archive_members_scanned=sum(1 for item in records if item.archive_member_path),
        option_quote_files=sum(1 for item in records if item.classification == "option_quote"),
        executable_quote_files=sum(1 for item in records if item.classification == "option_quote" and item.has_bid_ask),
        instrument_master_files=sum(1 for item in records if item.classification == "instrument_master"),
        point_in_time_authority_files=sum(1 for item in records if item.point_in_time_status == "POINT_IN_TIME_AUTHORITY_CANDIDATE"),
        blocked_files=sum(1 for item in records if not item.usable_for_option_e2e),
        parse_error_files=sum(1 for item in records if item.parse_status == "error"),
        census_sha256=digest,
        root_proof_sha256=root_digest,
    )
    return records, summary, root_proofs


def write_census_artifacts(files: list[CensusFile], summary: CensusSummary, root_proofs: list[RootProof], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [_portable_record(item) for item in sorted(files, key=lambda item: (item.logical_path, item.archive_member_path))]
    summary_payload = asdict(summary)
    (output_dir / "option_data_census_v4_1.json").write_text(
        json.dumps({"summary": summary_payload, "root_proof": [asdict(item) for item in root_proofs], "files": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fieldnames = list(records[0].keys()) if records else list(CensusFile.__dataclass_fields__)
    with (output_dir / "option_data_census_v4_1.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    (output_dir / "option_data_census_v4_1_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "root_proof_v4_1.json").write_text(
        json.dumps([asdict(item) for item in root_proofs], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest = _sha256_file(output_dir / "option_data_census_v4_1.json")
    (output_dir / "option_data_census_v4_1.json.sha256").write_text(
        f"{digest}  option_data_census_v4_1.json\n",
        encoding="utf-8",
    )


def _untracked_data_roots(worktree: Path) -> list[Path]:
    try:
        output = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=worktree, text=True)
    except Exception:
        return []
    roots: set[Path] = set()
    for item in output.split("\0"):
        if not item:
            continue
        path = worktree / item
        if path.suffix.lower() not in SUPPORTED_SUFFIXES and not _is_archive_path(path):
            continue
        if _is_secret_path(path) or _is_appledouble_path(item):
            continue
        parts = Path(item).parts
        if parts[:2] in {("runtime", "market_data"), ("runtime", "upstox_candidate_replay"), ("runtime", "kite_candidate_replay")}:
            roots.add(worktree / parts[0] / parts[1])
        elif parts[:2] == (".runtime", "market_data"):
            roots.add(worktree / parts[0] / parts[1])
    return sorted(roots)


def _root_proof(root: Path) -> RootProof:
    try:
        if not root.exists():
            return RootProof(str(root), False, False, False, 0, 0, "", "")
        files = [path for path in _iter_root_files(root) if not _is_secret_path(path) and not _is_appledouble_path(str(path))]
        payload = [{"path": str(path), "size": path.stat().st_size, "sha256": _sha256_file(path)} for path in files]
        return RootProof(
            root=str(root),
            exists=True,
            is_dir=root.is_dir(),
            is_file=root.is_file(),
            file_count=len(files),
            byte_count=sum(item["size"] for item in payload),
            sha256=_sha256_bytes(_canonical_json(payload)),
            proof_error="",
        )
    except Exception as exc:
        return RootProof(str(root), root.exists(), root.is_dir(), root.is_file(), 0, 0, "", f"{type(exc).__name__}: {exc}")


def _discover_files(roots: Iterable[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for root in roots:
        for path in _iter_root_files(root):
            if _is_ignored_runtime_path(path) or _is_secret_path(path) or _is_appledouble_path(str(path)):
                continue
            if path.suffix.lower() in SUPPORTED_SUFFIXES or _is_archive_path(path):
                found[str(path.resolve())] = path
    return [found[key] for key in sorted(found)]


def _iter_root_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if root.exists():
        return [path for path in root.rglob("*") if path.is_file()]
    return []


def _classify_file(path: Path, *, root: Path | None, repo_root: Path | None) -> list[CensusFile]:
    try:
        stat = path.stat()
    except OSError:
        return []
    if _is_archive_path(path):
        return [_archive_container_record(path, stat.st_size, root=root, repo_root=repo_root), *_archive_member_records(path, root=root, repo_root=repo_root)]
    columns, row_count, date_min, date_max, parse_status, parse_error = _preview(path)
    return [_record_for(path, stat.st_size, _sha256_file(path), columns, row_count, date_min, date_max, parse_status, parse_error, root=root, repo_root=repo_root)]


def _archive_container_record(path: Path, size_bytes: int, *, root: Path | None, repo_root: Path | None) -> CensusFile:
    return _record_for(path, size_bytes, _sha256_file(path), (), None, "", "", "archive_listed", "", root=root, repo_root=repo_root, classification_override="archive")


def _archive_member_records(path: Path, *, root: Path | None, repo_root: Path | None) -> list[CensusFile]:
    try:
        names = _archive_member_names(path)
    except Exception as exc:
        return [_record_for(path, path.stat().st_size, _sha256_file(path), (), None, "", "", "error", f"{type(exc).__name__}: {exc}", root=root, repo_root=repo_root, classification_override="archive")]
    records = []
    for name in names:
        if _is_appledouble_path(name) or _is_secret_path(Path(name)):
            continue
        suffix = "".join(Path(name).suffixes[-2:]).lower() if name.endswith(".tar.gz") else Path(name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES and suffix not in ARCHIVE_SUFFIXES:
            continue
        records.append(_record_for(path, 0, "", (), None, "", "", "archive_member_listed", "", root=root, repo_root=repo_root, archive_member_path=name))
    return records


def _archive_member_names(path: Path) -> list[str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return sorted(info.filename for info in archive.infolist() if not info.is_dir())
    mode = "r:gz" if _is_targz_path(path) else "r:"
    with tarfile.open(path, mode) as archive:
        return sorted(member.name for member in archive.getmembers() if member.isfile())


def _record_for(
    path: Path,
    size_bytes: int,
    sha256: str,
    columns: tuple[str, ...],
    row_count: int | None,
    date_min: str,
    date_max: str,
    parse_status: str,
    parse_error: str,
    *,
    root: Path | None,
    repo_root: Path | None,
    archive_member_path: str = "",
    classification_override: str | None = None,
) -> CensusFile:
    cols = {col.lower() for col in columns}
    text = f"{path} {archive_member_path}".lower()
    has_expiry = _has_any(cols, ("expiry", "expiry_date", "expiry_dt"))
    has_strike = _has_any(cols, ("strike", "strike_price"))
    has_lot_size = _has_any(cols, ("lot_size", "lotsize", "lot"))
    has_bid_ask = _has_any(cols, QUOTE_BID_COLUMNS) and _has_any(cols, QUOTE_ASK_COLUMNS)
    has_quote_time = _has_any(cols, ("quote_ts", "quote_ts_epoch", "timestamp", "ts", "datetime", "time"))
    has_option_identity = _has_any(cols, OPTION_COLUMNS) or any(token in text for token in ("option", "nfo", "nifty", "banknifty"))
    classification = classification_override or _classification(path, cols, has_bid_ask=has_bid_ask)
    authority_role = _authority_role(cols, text)
    pit_status = _point_in_time_status(path, classification, cols, text)
    usable, blocker = _usability(classification, pit_status, has_expiry, has_strike, has_lot_size, has_bid_ask, has_quote_time, parse_status)
    return CensusFile(
        logical_path=_logical_path(path, repo_root),
        absolute_path=str(path.resolve()),
        root=str(root) if root else "",
        root_relative_path=_root_relative_path(path, root),
        container_path=str(path.resolve()) if archive_member_path else "",
        archive_member_path=archive_member_path,
        suffix=_effective_suffix(path, archive_member_path),
        size_bytes=size_bytes,
        sha256=sha256,
        parse_status=parse_status,
        parse_error=parse_error,
        row_count=row_count,
        columns=columns,
        date_min=date_min,
        date_max=date_max,
        classification=classification,
        authority_role=authority_role,
        point_in_time_status=pit_status,
        has_option_identity=has_option_identity,
        has_expiry=has_expiry,
        has_strike=has_strike,
        has_lot_size=has_lot_size,
        has_bid_ask=has_bid_ask,
        has_quote_time=has_quote_time,
        usable_for_option_e2e=usable,
        blocker=blocker,
    )


def _preview(path: Path) -> tuple[tuple[str, ...], int | None, str, str, str, str]:
    try:
        if path.suffix.lower() == ".parquet" and pq is not None:
            parquet_file = pq.ParquetFile(path)  # type: ignore[union-attr]
            columns = tuple(str(name) for name in parquet_file.schema_arrow.names)
            row_count = int(parquet_file.metadata.num_rows) if parquet_file.metadata is not None else None
            date_min, date_max = _parquet_date_bounds(path, columns)
            return columns, row_count, date_min, date_max, "parsed", ""
        if path.suffix.lower() == ".csv" and pd is not None:
            frame = pd.read_csv(path, nrows=10_000)
        elif path.suffix.lower() == ".jsonl" and pd is not None:
            frame = pd.read_json(path, lines=True, nrows=10_000)
        elif path.suffix.lower() == ".json" and pd is not None:
            frame = _read_json_frame(path)
        elif path.suffix.lower() in {".db", ".sqlite", ".sqlite3"} and pd is not None:
            frame = _read_sqlite_preview(path)
        else:
            return (), None, "", "", "unsupported_parser", "pandas_or_pyarrow_unavailable"
    except Exception as exc:
        return (), None, "", "", "error", f"{type(exc).__name__}: {exc}"
    columns = tuple(str(col) for col in frame.columns)
    date_min, date_max = _date_bounds(frame)
    return columns, int(len(frame)), date_min, date_max, "parsed", ""


def _read_json_frame(path: Path) -> Any:
    try:
        return pd.read_json(path)  # type: ignore[union-attr]
    except ValueError:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame(payload)  # type: ignore[union-attr]
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    return pd.DataFrame(value)  # type: ignore[union-attr]
            return pd.DataFrame([payload])  # type: ignore[union-attr]
        return pd.DataFrame()  # type: ignore[union-attr]


def _read_sqlite_preview(path: Path) -> Any:
    with sqlite3.connect(path) as conn:
        tables = pd.read_sql_query("select name from sqlite_master where type='table' order by name", conn)  # type: ignore[union-attr]
        frames = []
        for table in tables["name"].head(5):
            quoted = str(table).replace('"', '""')
            frame = pd.read_sql_query(f'select * from "{quoted}" limit 200000', conn)  # type: ignore[union-attr]
            frame["_sqlite_table"] = table
            frames.append(frame)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()  # type: ignore[union-attr]


def _parquet_date_bounds(path: Path, columns: tuple[str, ...]) -> tuple[str, str]:
    if pd is None:
        return "", ""
    lowered = {name.lower(): name for name in columns}
    for name in DATE_COLUMNS:
        if name in lowered:
            try:
                frame = pd.read_parquet(path, columns=[lowered[name]])
            except Exception:
                return "", ""
            return _date_bounds(frame)
    return "", ""


def _date_bounds(frame: Any) -> tuple[str, str]:
    columns = {str(col).lower(): str(col) for col in frame.columns}
    for name in DATE_COLUMNS:
        if name in columns:
            values = frame[columns[name]].head(10_000)
            parsed = pd.to_datetime(values, errors="coerce")  # type: ignore[union-attr]
            parsed = parsed.dropna()
            if not parsed.empty:
                return parsed.min().isoformat(), parsed.max().isoformat()
    return "", ""


def _classification(path: Path, cols: set[str], *, has_bid_ask: bool) -> str:
    text = str(path).lower()
    if _has_any(cols, AUTHORITY_COLUMNS) and any(token in text for token in ("instrument", "master", "nfo", "upstox_instruments")):
        return "instrument_master"
    if has_bid_ask or _has_any(cols, ("ltp", "last_price", "last_traded_price", "quote_ts", "quote_age_sec")):
        if (
            _has_any(cols, ("expiry", "expiry_date"))
            and _has_any(cols, ("strike", "strike_price"))
            and _has_any(cols, ("option_type", "instrument_type", "right"))
        ) or "option" in text:
            return "option_quote"
    if _has_any(cols, ("open", "high", "low", "close")):
        return "candle_or_ohlc"
    if any(token in text for token in ("report", "summary", "scoreboard", "audit", "candidate")):
        return "derived_report"
    return "unknown"


def _authority_role(cols: set[str], text: str) -> str:
    roles = []
    if _has_any(cols, ("expiry", "expiry_date")):
        roles.append("expiry")
    if _has_any(cols, ("strike", "strike_price")):
        roles.append("strike")
    if _has_any(cols, ("lot_size", "lotsize", "lot")):
        roles.append("lot_size")
    if "current" in text and "instrument" in text:
        roles.append("current_master_warning")
    return "|".join(roles) if roles else "none"


def _point_in_time_status(path: Path, classification: str, cols: set[str], text: str) -> str:
    if classification != "instrument_master":
        return "NOT_AUTHORITY"
    if "current" in text or path.name in {"complete.json", "instruments.json", "kite_instruments.json"}:
        return "CURRENT_MASTER_NOT_POINT_IN_TIME"
    if _has_any(cols, ("asof", "as_of", "snapshot_date", "listed_from", "listed_until", "valid_from", "valid_until")):
        return "POINT_IN_TIME_AUTHORITY_CANDIDATE"
    return "AUTHORITY_CANDIDATE_NEEDS_ASOF_PROOF"


def _usability(
    classification: str,
    pit_status: str,
    has_expiry: bool,
    has_strike: bool,
    has_lot_size: bool,
    has_bid_ask: bool,
    has_quote_time: bool,
    parse_status: str,
) -> tuple[bool, str]:
    if parse_status != "parsed":
        return False, parse_status
    if classification == "instrument_master":
        if pit_status != "POINT_IN_TIME_AUTHORITY_CANDIDATE":
            return False, pit_status
        missing = [name for name, present in (("expiry", has_expiry), ("strike", has_strike), ("lot_size", has_lot_size)) if not present]
        return (not missing, "" if not missing else "missing_" + "_".join(missing))
    if classification == "option_quote":
        if not has_bid_ask:
            return False, "missing_bid_ask"
        if not has_quote_time:
            return False, "missing_quote_time"
        return True, ""
    return False, "not_option_e2e_authority_or_quote"


def _has_any(cols: set[str], names: Iterable[str]) -> bool:
    return any(name in cols for name in names)


def _is_secret_path(path: Path) -> bool:
    name = path.name.lower()
    return any(token in name for token in SECRET_NAME_TOKENS)


def _is_ignored_runtime_path(path: Path) -> bool:
    lowered = tuple(part.lower() for part in path.parts)
    return "logs" in lowered


def _is_appledouble_path(path: str) -> bool:
    parts = Path(path).parts
    return "__MACOSX" in parts or any(part.startswith("._") for part in parts)


def _is_archive_path(path: Path) -> bool:
    return path.suffix.lower() in {".zip", ".tar", ".tgz"} or _is_targz_path(path)


def _is_targz_path(path: Path) -> bool:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    return suffixes[-2:] == [".tar", ".gz"]


def _effective_suffix(path: Path, archive_member_path: str) -> str:
    target = Path(archive_member_path) if archive_member_path else path
    if _is_targz_path(target):
        return ".tar.gz"
    return target.suffix.lower()


def _owning_root(path: Path, roots: tuple[Path, ...]) -> Path | None:
    resolved = path.resolve()
    for root in sorted((item for item in roots if item.exists()), key=lambda item: len(str(item.resolve())), reverse=True):
        try:
            resolved.relative_to(root.resolve())
            return root
        except ValueError:
            continue
    return None


def _root_relative_path(path: Path, root: Path | None) -> str:
    if root is None:
        return ""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return ""


def _logical_path(path: Path, repo_root: Path | None) -> str:
    resolved = path.resolve()
    if repo_root is not None:
        try:
            return str(resolved.relative_to(repo_root.resolve()))
        except ValueError:
            pass
    return str(resolved)


def _portable_record(item: CensusFile) -> dict[str, Any]:
    record = asdict(item)
    record["columns"] = list(item.columns)
    return record


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
