from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


VERSION = "option_e2e_contract_reconstruction_v4_1"
QUOTE_COLUMNS = {"ltp", "bid_price", "ask_price"}
DEPTH_COLUMNS = {"last_price", "best_bid", "best_ask", "depth_json"}
TOKEN_COLUMNS = ("instrument_key", "instrument_token")
TIME_COLUMNS = ("ts", "exchange_timestamp", "local_ts", "timestamp", "datetime", "time")


@dataclass(frozen=True)
class FileCoverage:
    logical_path: str
    absolute_path: str
    sha256: str
    source_identity: str
    file_kind: str
    row_count: int
    observed_tokens: int
    reconstructed_nifty_option_tokens: int
    has_timestamp: bool
    has_symbol_or_token: bool
    has_nifty: bool
    has_ce_pe: bool
    has_strike: bool
    has_expiry: bool
    has_provider_source: bool
    has_immutable_hash: bool
    has_quote_values: bool
    has_depth_values: bool
    has_no_post_expiry_rows: bool
    point_in_time_authority: bool
    proves_historical_contract_existence: bool
    blocker: str


def default_roots(repo_root: Path) -> tuple[Path, ...]:
    roots = (
        repo_root / "runtime" / "market_data" / "upstox",
        repo_root / "runtime" / "strategy_validation",
        repo_root / "configs" / "backtest_data_schema_examples",
        repo_root / ".runtime" / "market_data",
        Path("/Users/madhuram/tradebot-data"),
        Path("/Users/madhuram/tradebot-ml-evidence"),
    )
    return tuple(path for path in roots if path.exists())


def discover_quote_files(roots: Iterable[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for root in roots:
        candidates = [root] if root.is_file() else (
            path for path in root.rglob("*") if path.suffix.lower() in {".parquet", ".csv"}
        )
        for path in candidates:
            if not path.is_file():
                continue
            name = str(path).lower()
            if (
                "tick" not in name
                and "quote" not in name
                and "depth" not in name
                and "option" not in name
                and path.name != "combined.parquet"
            ):
                continue
            if any(token in name for token in (".env", "credential", "secret", "access_token", "refresh_token")):
                continue
            found[str(path.resolve())] = path
    return [found[key] for key in sorted(found)]


def load_upstox_nifty_option_master(repo_root: Path) -> dict[str, dict[str, Any]]:
    path = repo_root / "runtime" / "upstox_instruments" / "complete.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    by_key: dict[str, dict[str, Any]] = {}
    for row in records:
        underlying = str(row.get("underlying_symbol") or row.get("asset_symbol") or row.get("name") or "").upper()
        option_type = str(row.get("instrument_type") or "").upper()
        if underlying != "NIFTY" or option_type not in {"CE", "PE"}:
            continue
        normalized = {
            "instrument_key": row.get("instrument_key"),
            "instrument_token": str(row.get("exchange_token") or ""),
            "symbol": underlying,
            "option_type": option_type,
            "strike": row.get("strike_price"),
            "expiry": _expiry_date(row.get("expiry")),
            "trading_symbol": row.get("trading_symbol"),
            "provider": "upstox_complete_json_current_snapshot",
        }
        if normalized["instrument_key"]:
            by_key[str(normalized["instrument_key"])] = normalized
        if normalized["instrument_token"]:
            by_key[str(normalized["instrument_token"])] = normalized
    return by_key


def build_coverage(repo_root: Path, roots: Iterable[Path]) -> tuple[list[FileCoverage], dict[str, Any]]:
    master = load_upstox_nifty_option_master(repo_root)
    files = discover_quote_files(roots)
    coverage = [_classify(path, repo_root, master) for path in files]
    records = [asdict(item) for item in coverage]
    summary = {
        "version": VERSION,
        "repo_root": str(repo_root),
        "roots": [str(path) for path in roots],
        "files_discovered": len(files),
        "quote_files": sum(1 for item in coverage if item.file_kind == "quote"),
        "depth_files": sum(1 for item in coverage if item.file_kind == "depth"),
        "files_with_reconstructed_identity": sum(
            1 for item in coverage if item.reconstructed_nifty_option_tokens > 0
        ),
        "files_proving_historical_contract_existence": sum(
            1 for item in coverage if item.proves_historical_contract_existence
        ),
        "blocked_by_no_point_in_time_authority": sum(
            1 for item in coverage if "NO_POINT_IN_TIME_INSTRUMENT_AUTHORITY" in item.blocker
        ),
        "coverage_sha256": _sha256_bytes(_canonical_json(records)),
    }
    return coverage, summary


def write_artifacts(coverage: list[FileCoverage], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [asdict(item) for item in sorted(coverage, key=lambda item: item.logical_path)]
    (output_dir / "coverage_matrix.json").write_text(
        json.dumps({"summary": summary, "files": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "coverage_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()) if records else list(FileCoverage.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(records)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = _sha256_file(output_dir / "coverage_matrix.json")
    (output_dir / "coverage_matrix.json.sha256").write_text(f"{digest}  coverage_matrix.json\n", encoding="utf-8")


def _classify(path: Path, repo_root: Path, master: dict[str, dict[str, Any]]) -> FileCoverage:
    read_error = ""
    try:
        df = _read_table(path)
    except Exception as exc:
        read_error = f"READ_FAILED:{type(exc).__name__}"
        df = pd.DataFrame()
    columns = {str(col) for col in df.columns}
    lower_columns = {col.lower() for col in columns}
    has_quote_values = bool({"ltp", "bid_price", "ask_price", "bid", "ask", "open", "high", "low", "close"} & lower_columns)
    file_kind = "depth" if DEPTH_COLUMNS & lower_columns else "quote" if has_quote_values else "unknown"
    token_col = next((col for col in TOKEN_COLUMNS if col in df.columns), None)
    time_col = next((col for col in TIME_COLUMNS if col in df.columns), None)
    tokens = set()
    reconstructed: dict[str, dict[str, Any]] = {}
    if token_col:
        tokens = {str(value) for value in df[token_col].dropna().unique() if str(value) and str(value) != "feeds"}
        reconstructed = {token: master[token] for token in tokens if token in master}
    min_ts, max_ts = _time_bounds(df, time_col)
    has_no_post_expiry_rows = False
    if reconstructed and max_ts is not None:
        expiries = [row["expiry"] for row in reconstructed.values() if row.get("expiry")]
        has_no_post_expiry_rows = bool(expiries) and all(max_ts.date().isoformat() <= expiry for expiry in expiries)
    has_depth_values = bool({"depth_json", "best_bid", "best_ask"} & lower_columns)
    has_reconstructed_identity = bool(reconstructed)
    point_in_time_authority = False
    blockers = []
    if not has_reconstructed_identity:
        blockers.append("NO_NIFTY_CE_PE_TOKEN_MATCH")
    if not point_in_time_authority:
        blockers.append("NO_POINT_IN_TIME_INSTRUMENT_AUTHORITY")
    if not has_no_post_expiry_rows:
        blockers.append("NO_POST_EXPIRY_PROOF_UNAVAILABLE_OR_FAILED")
    if read_error:
        blockers.append(read_error)
    proves = (
        time_col is not None
        and has_reconstructed_identity
        and has_quote_values
        and has_no_post_expiry_rows
        and point_in_time_authority
    )
    return FileCoverage(
        logical_path=_logical_path(path, repo_root),
        absolute_path=str(path.resolve()),
        sha256=_sha256_file(path),
        source_identity=_source_identity(path),
        file_kind=file_kind,
        row_count=len(df),
        observed_tokens=len(tokens),
        reconstructed_nifty_option_tokens=len(reconstructed),
        has_timestamp=time_col is not None,
        has_symbol_or_token=token_col is not None or "symbol" in lower_columns,
        has_nifty=has_reconstructed_identity or _has_symbol(df, "NIFTY"),
        has_ce_pe=has_reconstructed_identity,
        has_strike=has_reconstructed_identity,
        has_expiry=has_reconstructed_identity,
        has_provider_source=_source_identity(path) != "unknown",
        has_immutable_hash=True,
        has_quote_values=has_quote_values,
        has_depth_values=has_depth_values,
        has_no_post_expiry_rows=has_no_post_expiry_rows,
        point_in_time_authority=point_in_time_authority,
        proves_historical_contract_existence=proves,
        blocker=";".join(blockers) if blockers else "",
    )


def _time_bounds(df: pd.DataFrame, column: str | None) -> tuple[datetime | None, datetime | None]:
    if not column:
        return None, None
    values = df[column].dropna()
    if values.empty:
        return None, None
    if pd.api.types.is_numeric_dtype(values):
        parsed = pd.to_datetime(values, unit="s", utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(values, utc=True, errors="coerce")
    parsed = parsed.dropna()
    if parsed.empty:
        return None, None
    return parsed.min().floor("s").to_pydatetime(), parsed.max().floor("s").to_pydatetime()


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def _expiry_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc).date().isoformat()
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return "" if pd.isna(parsed) else parsed.date().isoformat()


def _has_symbol(df: pd.DataFrame, symbol: str) -> bool:
    if "symbol" not in df.columns:
        return False
    return bool((df["symbol"].astype(str).str.upper() == symbol).any())


def _source_identity(path: Path) -> str:
    text = str(path).lower()
    if "upstox" in text:
        return "upstox"
    if "kite" in text:
        return "kite"
    return "unknown"


def _logical_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("research/option_e2e_recertification_v4/contract_reconstruction_v4_1"))
    parser.add_argument("--root", action="append", type=Path, dest="roots")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    roots = tuple(args.roots) if args.roots else default_roots(repo_root)
    coverage, summary = build_coverage(repo_root, roots)
    write_artifacts(coverage, summary, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
