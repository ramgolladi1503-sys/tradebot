from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
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


CENSUS_VERSION = "option_e2e_data_census_v4"
SUPPORTED_SUFFIXES = {".parquet", ".csv", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
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
DATE_COLUMNS = ("date", "session", "timestamp", "ts", "datetime", "time", "quote_ts", "quote_ts_epoch")
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
class CensusFile:
    logical_path: str
    absolute_path: str
    suffix: str
    size_bytes: int
    sha256: str
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
    roots: tuple[str, ...]
    files_scanned: int
    files_classified: int
    option_quote_files: int
    executable_quote_files: int
    instrument_master_files: int
    point_in_time_authority_files: int
    blocked_files: int
    census_sha256: str


def default_roots(repo_root: Path) -> tuple[Path, ...]:
    candidates = (
        repo_root / "data",
        repo_root / ".runtime" / "market_data",
        repo_root / "runtime" / "market_data",
        repo_root / "runtime" / "upstox_instruments",
        repo_root / "runtime" / "upstox_candidate_replay",
        repo_root / "runtime" / "kite_candidate_replay",
        repo_root / "runtime" / "strategy_validation",
        repo_root / "configs" / "backtest_data_schema_examples",
        Path("/Users/madhuram/tradebot-data"),
        Path("/Users/madhuram/tradebot-ml-evidence"),
    )
    return tuple(path for path in candidates if path.exists())


def build_census(roots: Iterable[Path], *, repo_root: Path | None = None) -> tuple[list[CensusFile], CensusSummary]:
    root_tuple = tuple(Path(root).expanduser() for root in roots)
    files = [_classify_file(path, repo_root=repo_root) for path in _discover_files(root_tuple)]
    files = [item for item in files if item is not None]
    payload = [_portable_record(item) for item in files]
    digest = _sha256_bytes(_canonical_json(payload))
    summary = CensusSummary(
        version=CENSUS_VERSION,
        roots=tuple(str(path) for path in root_tuple),
        files_scanned=len(files),
        files_classified=len(files),
        option_quote_files=sum(1 for item in files if item.classification == "option_quote"),
        executable_quote_files=sum(1 for item in files if item.classification == "option_quote" and item.has_bid_ask),
        instrument_master_files=sum(1 for item in files if item.classification == "instrument_master"),
        point_in_time_authority_files=sum(1 for item in files if item.point_in_time_status == "POINT_IN_TIME_AUTHORITY_CANDIDATE"),
        blocked_files=sum(1 for item in files if not item.usable_for_option_e2e),
        census_sha256=digest,
    )
    return files, summary


def write_census_artifacts(files: list[CensusFile], summary: CensusSummary, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [_portable_record(item) for item in sorted(files, key=lambda item: item.logical_path)]
    summary_payload = asdict(summary)
    (output_dir / "option_data_census.json").write_text(
        json.dumps({"summary": summary_payload, "files": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fieldnames = list(records[0].keys()) if records else list(CensusFile.__dataclass_fields__)
    with (output_dir / "option_data_census.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    (output_dir / "option_data_census_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    digest = _sha256_file(output_dir / "option_data_census.json")
    (output_dir / "option_data_census.json.sha256").write_text(
        f"{digest}  option_data_census.json\n",
        encoding="utf-8",
    )


def _discover_files(roots: Iterable[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for root in roots:
        if root.is_file():
            if _is_secret_path(root):
                continue
            candidates = (root,)
        elif root.exists():
            candidates = (path for path in root.rglob("*") if path.is_file())
        else:
            candidates = ()
        for path in candidates:
            if _is_ignored_runtime_path(path):
                continue
            if path.suffix.lower() in SUPPORTED_SUFFIXES and not _is_secret_path(path):
                found[str(path.resolve())] = path
    return [found[key] for key in sorted(found)]


def _classify_file(path: Path, *, repo_root: Path | None) -> CensusFile | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    columns, row_count, date_min, date_max = _preview(path)
    cols = {col.lower() for col in columns}
    text = str(path).lower()
    has_option_identity = _has_any(cols, OPTION_COLUMNS) or any(token in text for token in ("option", "nfo", "nifty", "banknifty"))
    has_expiry = _has_any(cols, ("expiry", "expiry_date", "expiry_dt"))
    has_strike = _has_any(cols, ("strike", "strike_price"))
    has_lot_size = _has_any(cols, ("lot_size", "lotsize", "lot"))
    has_bid_ask = _has_any(cols, QUOTE_BID_COLUMNS) and _has_any(cols, QUOTE_ASK_COLUMNS)
    has_quote_time = _has_any(cols, ("quote_ts", "quote_ts_epoch", "timestamp", "ts", "datetime", "time"))
    classification = _classification(path, cols, has_bid_ask=has_bid_ask)
    authority_role = _authority_role(cols, text)
    pit_status = _point_in_time_status(path, classification, cols, text)
    usable, blocker = _usability(classification, pit_status, has_expiry, has_strike, has_lot_size, has_bid_ask, has_quote_time)
    return CensusFile(
        logical_path=_logical_path(path, repo_root),
        absolute_path=str(path.resolve()),
        suffix=path.suffix.lower(),
        size_bytes=stat.st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
        columns=tuple(columns),
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


def _preview(path: Path) -> tuple[tuple[str, ...], int | None, str, str]:
    try:
        if path.suffix.lower() == ".parquet" and pq is not None:
            parquet_file = pq.ParquetFile(path)  # type: ignore[union-attr]
            columns = tuple(str(name) for name in parquet_file.schema_arrow.names)
            row_count = int(parquet_file.metadata.num_rows) if parquet_file.metadata is not None else None
            date_min, date_max = _parquet_date_bounds(path, columns)
            return columns, row_count, date_min, date_max
        elif path.suffix.lower() == ".csv" and pd is not None:
            frame = pd.read_csv(path, nrows=10_000)
        elif path.suffix.lower() == ".jsonl" and pd is not None:
            frame = pd.read_json(path, lines=True, nrows=10_000)
        elif path.suffix.lower() == ".json" and pd is not None:
            frame = _read_json_frame(path)
        elif path.suffix.lower() in {".db", ".sqlite", ".sqlite3"} and pd is not None:
            frame = _read_sqlite_preview(path)
        else:
            return (), None, "", ""
    except Exception:
        return (), None, "", ""
    columns = tuple(str(col) for col in frame.columns)
    date_min, date_max = _date_bounds(frame)
    return columns, int(len(frame)), date_min, date_max


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
) -> tuple[bool, str]:
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
