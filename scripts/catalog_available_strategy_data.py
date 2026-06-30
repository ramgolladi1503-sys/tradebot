from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SUPPORTED_SUFFIXES = {".parquet", ".csv", ".json", ".jsonl", ".db", ".sqlite", ".sqlite3"}
OUTPUT_COLUMNS = [
    "path",
    "file_type",
    "row_count",
    "date_min",
    "date_max",
    "instruments_symbols",
    "schema_columns",
    "detected_dataset_type",
    "evidence_origin",
    "eligible_as_raw_market_input",
    "exclusion_reason",
    "dataset_fingerprint",
    "duplicate_group_id",
    "is_duplicate",
    "canonical_dataset_path",
    "volume_quality",
    "has_index_ohlc",
    "has_option_ltp",
    "has_bid_ask",
    "has_depth",
    "has_spread",
    "has_oi",
    "has_iv",
    "has_greeks",
    "has_candidate_id",
    "has_instrument_id",
    "has_strategy",
    "has_entry_target_stop",
    "has_executable_flag",
    "has_rejection_reason",
    "has_quote_age",
    "usable_for_directional_proxy",
    "usable_for_vwap_or_volume_proxy",
    "usable_for_option_ltp_replay",
    "usable_for_executable_option_replay",
    "reason",
]


@dataclass
class CatalogRow:
    path: str
    file_type: str
    row_count: int
    date_min: str
    date_max: str
    instruments_symbols: str
    schema_columns: str
    detected_dataset_type: str
    evidence_origin: str
    eligible_as_raw_market_input: bool
    exclusion_reason: str
    dataset_fingerprint: str
    duplicate_group_id: str
    is_duplicate: bool
    canonical_dataset_path: str
    volume_quality: str
    has_index_ohlc: bool
    has_option_ltp: bool
    has_bid_ask: bool
    has_depth: bool
    has_spread: bool
    has_oi: bool
    has_iv: bool
    has_greeks: bool
    has_candidate_id: bool
    has_instrument_id: bool
    has_strategy: bool
    has_entry_target_stop: bool
    has_executable_flag: bool
    has_rejection_reason: bool
    has_quote_age: bool
    usable_for_directional_proxy: bool
    usable_for_vwap_or_volume_proxy: bool
    usable_for_option_ltp_replay: bool
    usable_for_executable_option_replay: bool
    reason: str


def discover_files(roots: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() in SUPPORTED_SUFFIXES:
            paths = [root]
        else:
            paths = [p for p in root.rglob("*") if _is_supported_dataset_path(p) and "all_available_data_audit" not in p.parts]
        for path in paths:
            resolved = path.resolve()
            if resolved not in seen:
                found.append(path)
                seen.add(resolved)
    return sorted(found, key=lambda p: str(p))


def _is_supported_dataset_path(path: Path) -> bool:
    if path.is_dir():
        return path.suffix.lower() == ".parquet"
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def _read_dataset(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path, nrows=200000)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True, nrows=200000)
    if suffix == ".json":
        try:
            return pd.read_json(path)
        except ValueError:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            if isinstance(payload, dict):
                for value in payload.values():
                    if isinstance(value, list):
                        return pd.DataFrame(value)
                return pd.DataFrame([payload])
            return pd.DataFrame()
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return _read_sqlite_preview(path)
    raise ValueError(f"unsupported file type: {suffix}")


def _read_sqlite_preview(path: Path) -> pd.DataFrame:
    with sqlite3.connect(path) as conn:
        tables = pd.read_sql_query("select name from sqlite_master where type='table' order by name", conn)
        frames = []
        for table in tables["name"].head(5):
            quoted = str(table).replace('"', '""')
            try:
                frame = pd.read_sql_query(f'select * from "{quoted}" limit 200000', conn)
            except Exception:
                continue
            frame["_sqlite_table"] = table
            frames.append(frame)
        return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _norm_columns(frame: pd.DataFrame) -> dict[str, str]:
    return {str(col).lower().strip(): str(col) for col in frame.columns}


def _has_any(cols: set[str], names: Iterable[str]) -> bool:
    return any(name in cols for name in names)


def _has_all(cols: set[str], names: Iterable[str]) -> bool:
    return all(name in cols for name in names)


def _dates(frame: pd.DataFrame, colmap: dict[str, str]) -> tuple[str, str]:
    for key in ("date", "timestamp", "ts", "datetime", "time", "created_at", "signal_timestamp", "entry_timestamp"):
        if key in colmap:
            parsed = pd.to_datetime(frame[colmap[key]], errors="coerce")
            parsed = parsed.dropna()
            if not parsed.empty:
                return parsed.min().isoformat(), parsed.max().isoformat()
    return "", ""


def _symbols(frame: pd.DataFrame, colmap: dict[str, str]) -> str:
    values: list[str] = []
    for key in ("instrument", "symbol", "tradingsymbol", "instrument_id", "underlying"):
        if key in colmap:
            values.extend(str(item) for item in frame[colmap[key]].dropna().astype(str).unique()[:30])
    return "|".join(sorted(dict.fromkeys(values)))


def _volume_quality(frame: pd.DataFrame, colmap: dict[str, str]) -> str:
    if "volume" not in colmap:
        return "MISSING_VOLUME"
    volume = pd.to_numeric(frame[colmap["volume"]], errors="coerce")
    if volume.empty or volume.isna().all():
        return "MISSING_VOLUME"
    if float(volume.fillna(0).sum()) == 0.0:
        return "ZERO_VOLUME"
    if volume.isna().any():
        return "PARTIAL_VOLUME"
    return "OK"


def _is_derived_report(path: Path, cols: set[str]) -> bool:
    text = str(path).lower()
    name = path.name.lower()
    if "/runtime/backtests/" in text and any(token in name for token in ("summary", "report", "catalog", "errors", "matrix", "trades")):
        return True
    if "/runtime/" in text and any(token in name for token in ("report", "summary", "edge", "catalog", "trade", "proxy")):
        return True
    if _has_any(cols, ("avg_net_bps", "profit_factor_proxy", "verdict")) and not _has_all(cols, ("open", "high", "low", "close")):
        return True
    return False


def _file_hash(path: Path, *, limit_bytes: int = 1_000_000) -> str:
    try:
        if not path.is_file() or path.stat().st_size > limit_bytes:
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return ""


def classify_dataset(path: Path, frame: pd.DataFrame) -> CatalogRow:
    colmap = _norm_columns(frame)
    cols = set(colmap)
    row_count = int(len(frame))
    schema = "|".join(str(col) for col in frame.columns)
    date_min, date_max = _dates(frame, colmap)
    symbols = _symbols(frame, colmap)
    volume_quality = _volume_quality(frame, colmap)
    has_index_ohlc = _has_all(cols, ("open", "high", "low", "close")) and _has_any(cols, ("instrument", "symbol", "underlying"))
    has_option_ltp = _has_any(cols, ("option_ltp", "contract_ltp", "ltp", "last_price", "last_traded_price")) and _has_any(cols, ("strike", "option_type", "expiry", "tradingsymbol"))
    has_bid_ask = _has_any(cols, ("bid", "best_bid", "bid_price")) and _has_any(cols, ("ask", "best_ask", "ask_price"))
    has_depth = _has_any(cols, ("depth", "bid_qty", "ask_qty", "market_depth"))
    has_spread = _has_any(cols, ("spread", "spread_pct", "bid_ask_spread")) or has_bid_ask
    has_oi = _has_any(cols, ("oi", "open_interest", "call_oi", "put_oi"))
    has_iv = _has_any(cols, ("iv", "implied_volatility"))
    has_greeks = _has_any(cols, ("delta", "gamma", "theta", "vega", "rho"))
    has_candidate_id = _has_any(cols, ("candidate_id", "candidate_intent_id", "trade_id"))
    has_instrument_id = _has_any(cols, ("instrument_id", "instrument_token", "token"))
    has_strategy = _has_any(cols, ("strategy", "strategy_id", "strategy_name", "family"))
    has_entry_target_stop = _has_any(cols, ("entry", "entry_price", "entry_underlying")) and _has_any(cols, ("target", "target_price")) and _has_any(cols, ("stop", "stop_loss", "sl"))
    has_executable_flag = _has_any(cols, ("executable", "execution_ok", "allowed_for_live_execution"))
    has_rejection_reason = _has_any(cols, ("rejection_reason", "block_reason", "reason", "reject_reason"))
    has_quote_age = _has_any(cols, ("quote_age", "quote_age_sec", "option_quote_age_sec", "age_ms", "age_sec"))
    origin = "UNKNOWN"
    eligible_raw = False
    exclusion_reason = ""
    if "/runtime/backtests/" in str(path).lower() or _is_derived_report(path, cols):
        origin = "DERIVED_BACKTEST_OUTPUT"
        exclusion_reason = "derived backtest output"
    elif any(token in str(path).lower() for token in ("/runtime/", "/reports/", "/artifacts/")):
        origin = "DERIVED_REPORT"
        exclusion_reason = "derived runtime/report artifact"
    elif any(token in str(path).lower() for token in ("/logs/",)) or any(token in str(path).lower() for token in ("live_evidence", "live_log")):
        origin = "RAW_LIVE_EVIDENCE" if has_strategy or has_candidate_id or has_executable_flag else "LOG_ONLY"
        exclusion_reason = "" if origin == "RAW_LIVE_EVIDENCE" else "log-only evidence"
    elif has_index_ohlc or has_option_ltp or has_bid_ask or has_depth:
        origin = "RAW_MARKET_DATA"
        exclusion_reason = ""
        eligible_raw = True
    elif has_candidate_id or has_strategy:
        origin = "RAW_LIVE_EVIDENCE"
        exclusion_reason = ""
    else:
        origin = "UNKNOWN"
        exclusion_reason = "schema not recognized as raw evidence"

    if row_count == 0:
        dtype = "INVALID_OR_EMPTY"
        reason = "empty dataset"
    elif _is_derived_report(path, cols):
        dtype = "BACKTEST_REPORT"
        reason = "derived report/backtest artifact; not raw market evidence"
    elif has_index_ohlc:
        dtype = "INDEX_OHLC"
        reason = "index OHLC available for directional proxy only"
    elif has_option_ltp and has_bid_ask and has_depth:
        dtype = "OPTION_QUOTE_TRUTH"
        reason = "option quote truth appears available"
    elif has_option_ltp:
        dtype = "OPTION_OHLC_OR_LTP"
        reason = "option LTP available without full executable quote truth"
    elif has_candidate_id and has_rejection_reason:
        dtype = "CANDIDATE_DECISIONS"
        reason = "candidate decision/rejection evidence"
    elif has_strategy and _has_any(cols, ("rank", "score", "ranking_bucket", "top_opportunity")):
        dtype = "RANKING_SNAPSHOTS"
        reason = "ranking behavior evidence without quote truth"
    elif has_strategy and _has_any(cols, ("direction", "signal", "side")):
        dtype = "STRATEGY_SIGNAL_TRACE"
        reason = "strategy signal trace"
    elif any(token in str(path).lower() for token in ("/logs/", "runtime/live_evidence")):
        dtype = "LIVE_LOG"
        reason = "runtime/live log evidence"
    else:
        dtype = "UNKNOWN"
        reason = "schema not recognized as market, option, candidate, ranking, or signal evidence"

    usable_directional = dtype == "INDEX_OHLC"
    usable_vwap = usable_directional and volume_quality == "OK"
    usable_option_ltp = dtype in {"OPTION_OHLC_OR_LTP", "OPTION_QUOTE_TRUTH"}
    usable_executable = dtype == "OPTION_QUOTE_TRUTH" and has_candidate_id and has_bid_ask and has_spread and has_depth and has_quote_age
    if dtype == "BACKTEST_REPORT":
        usable_directional = usable_vwap = usable_option_ltp = usable_executable = False
    if dtype in {"BACKTEST_REPORT", "STRATEGY_SIGNAL_TRACE", "RANKING_SNAPSHOTS", "CANDIDATE_DECISIONS", "LIVE_LOG"}:
        eligible_raw = False
        if not exclusion_reason:
            exclusion_reason = f"evidence_origin={origin}"
    elif origin != "RAW_MARKET_DATA":
        eligible_raw = False
        if not exclusion_reason:
            exclusion_reason = f"evidence_origin={origin}"
    elif dtype == "INDEX_OHLC":
        eligible_raw = True
        if volume_quality != "OK":
            exclusion_reason = f"volume_quality={volume_quality}" if volume_quality != "OK" else ""

    fingerprint_seed = "|".join(
        [
            schema,
            str(row_count),
            date_min,
            date_max,
            symbols,
            volume_quality,
            origin,
            _file_hash(path),
        ]
    )
    fingerprint = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()
    return CatalogRow(
        path=str(path),
        file_type=path.suffix.lower().lstrip(".") or "directory",
        row_count=row_count,
        date_min=date_min,
        date_max=date_max,
        instruments_symbols=symbols,
        schema_columns=schema,
        detected_dataset_type=dtype,
        evidence_origin=origin,
        eligible_as_raw_market_input=eligible_raw,
        exclusion_reason=exclusion_reason,
        dataset_fingerprint=fingerprint,
        duplicate_group_id="",
        is_duplicate=False,
        canonical_dataset_path="",
        volume_quality=volume_quality,
        has_index_ohlc=has_index_ohlc,
        has_option_ltp=has_option_ltp,
        has_bid_ask=has_bid_ask,
        has_depth=has_depth,
        has_spread=has_spread,
        has_oi=has_oi,
        has_iv=has_iv,
        has_greeks=has_greeks,
        has_candidate_id=has_candidate_id,
        has_instrument_id=has_instrument_id,
        has_strategy=has_strategy,
        has_entry_target_stop=has_entry_target_stop,
        has_executable_flag=has_executable_flag,
        has_rejection_reason=has_rejection_reason,
        has_quote_age=has_quote_age,
        usable_for_directional_proxy=usable_directional,
        usable_for_vwap_or_volume_proxy=usable_vwap,
        usable_for_option_ltp_replay=usable_option_ltp,
        usable_for_executable_option_replay=usable_executable,
        reason=reason,
    )


def error_row(path: Path, message: str) -> CatalogRow:
    return CatalogRow(
        path=str(path),
        file_type=path.suffix.lower().lstrip(".") or "directory",
        row_count=0,
        date_min="",
        date_max="",
        instruments_symbols="",
        schema_columns="",
        detected_dataset_type="INVALID_OR_EMPTY",
        evidence_origin="UNKNOWN",
        eligible_as_raw_market_input=False,
        exclusion_reason=f"read_error: {message}",
        dataset_fingerprint="",
        duplicate_group_id="",
        is_duplicate=False,
        canonical_dataset_path="",
        volume_quality="UNKNOWN",
        has_index_ohlc=False,
        has_option_ltp=False,
        has_bid_ask=False,
        has_depth=False,
        has_spread=False,
        has_oi=False,
        has_iv=False,
        has_greeks=False,
        has_candidate_id=False,
        has_instrument_id=False,
        has_strategy=False,
        has_entry_target_stop=False,
        has_executable_flag=False,
        has_rejection_reason=False,
        has_quote_age=False,
        usable_for_directional_proxy=False,
        usable_for_vwap_or_volume_proxy=False,
        usable_for_option_ltp_replay=False,
        usable_for_executable_option_replay=False,
        reason=f"read_error: {message}",
    )


def build_catalog(*, roots: Iterable[Path], out_dir: Path) -> pd.DataFrame:
    rows: list[CatalogRow] = []
    for path in discover_files(roots):
        try:
            frame = _read_dataset(path)
            rows.append(classify_dataset(path, frame))
        except Exception as exc:
            rows.append(error_row(path, repr(exc)))
    catalog = pd.DataFrame([asdict(row) for row in rows], columns=OUTPUT_COLUMNS)
    if not catalog.empty:
        catalog["duplicate_group_id"] = catalog["dataset_fingerprint"].astype(str)
        grouped = catalog.groupby("dataset_fingerprint", dropna=False)
        canonical_paths = grouped["path"].transform("min")
        catalog["canonical_dataset_path"] = canonical_paths
        catalog["is_duplicate"] = catalog["path"].astype(str) != catalog["canonical_dataset_path"].astype(str)
        dup_counts = grouped["path"].transform("count")
        catalog.loc[catalog["dataset_fingerprint"].ne(""), "duplicate_group_id"] = catalog["dataset_fingerprint"]
        catalog.loc[catalog["dataset_fingerprint"].eq(""), "duplicate_group_id"] = catalog["path"].astype(str)
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(out_dir / "available_data_catalog.csv", index=False)
    (out_dir / "available_data_catalog.json").write_text(json.dumps(catalog.to_dict("records"), indent=2, default=str), encoding="utf-8")
    write_report(catalog, out_dir)
    return catalog


def write_report(catalog: pd.DataFrame, out_dir: Path) -> None:
    counts = catalog["detected_dataset_type"].value_counts().sort_index().to_dict() if not catalog.empty else {}
    lines = [
        "# Available Strategy Data Catalog",
        "",
        "Offline catalog only. This does not call broker APIs, place orders, or promote derived backtest reports to raw evidence.",
        "",
        "## Dataset Type Counts",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in counts.items())
    lines.extend(
        [
            "",
            "## Capability Counts",
            "",
            f"- Directional proxy datasets: {int(catalog['usable_for_directional_proxy'].sum()) if not catalog.empty else 0}",
            f"- VWAP/volume-valid datasets: {int(catalog['usable_for_vwap_or_volume_proxy'].sum()) if not catalog.empty else 0}",
            f"- Option LTP replay datasets: {int(catalog['usable_for_option_ltp_replay'].sum()) if not catalog.empty else 0}",
            f"- Executable option replay datasets: {int(catalog['usable_for_executable_option_replay'].sum()) if not catalog.empty else 0}",
            "",
            "## Safety",
            "",
            "- broker_api_called=false",
            "- is_order_action=false",
            "- allowed_for_live_execution=false",
        ]
    )
    (out_dir / "available_data_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Catalog available offline strategy evidence datasets.")
    parser.add_argument("--roots", nargs="+", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    catalog = build_catalog(roots=args.roots, out_dir=args.out)
    print(json.dumps({"datasets": int(len(catalog)), "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
