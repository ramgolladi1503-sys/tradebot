from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_COLUMNS = {
    "ts", "instrument_key", "ltp", "bid_price", "ask_price",
    "delta", "theta", "gamma", "vega", "iv", "volume", "oi",
}


@dataclass(frozen=True)
class FileAudit:
    path: str
    sha256: str
    size_bytes: int
    rows: int
    columns: tuple[str, ...]
    missing_columns: tuple[str, ...]
    instrument_count: int
    first_ts: str | None
    last_ts: str | None
    timestamps_valid: bool
    duplicate_rows: int
    duplicate_ts_instrument_rows: int
    crossed_quote_rows: int
    nonpositive_ltp_rows: int
    negative_volume_rows: int
    negative_oi_rows: int
    null_rates: dict[str, float]
    usable: bool
    blockers: tuple[str, ...]
    error: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_timestamps(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, utc=True, errors="coerce")
    numeric = pd.to_numeric(series, errors="coerce")
    sample = numeric.dropna()
    if sample.empty:
        return pd.to_datetime(series, utc=True, errors="coerce")
    median = float(sample.median())
    unit = "ns" if median > 1e17 else "us" if median > 1e14 else "ms" if median > 1e11 else "s"
    return pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")


def audit_file(path: Path) -> FileAudit:
    digest = _sha256(path)
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        return FileAudit(
            path=str(path), sha256=digest, size_bytes=path.stat().st_size,
            rows=0, columns=(), missing_columns=tuple(sorted(REQUIRED_COLUMNS)),
            instrument_count=0, first_ts=None, last_ts=None,
            timestamps_valid=False, duplicate_rows=0, duplicate_ts_instrument_rows=0,
            crossed_quote_rows=0, nonpositive_ltp_rows=0, negative_volume_rows=0,
            negative_oi_rows=0, null_rates={}, usable=False,
            blockers=("unreadable_parquet",), error=repr(exc),
        )

    columns = tuple(str(column) for column in frame.columns)
    missing = tuple(sorted(REQUIRED_COLUMNS.difference(frame.columns)))
    timestamps = _normalise_timestamps(frame["ts"]) if "ts" in frame else pd.Series(dtype="datetime64[ns, UTC]")
    timestamps_valid = bool(len(timestamps) and timestamps.notna().all())
    instrument_count = int(frame["instrument_key"].nunique(dropna=True)) if "instrument_key" in frame else 0

    numeric = frame.copy()
    for column in ("ltp", "bid_price", "ask_price", "volume", "oi"):
        if column in numeric:
            numeric[column] = pd.to_numeric(numeric[column], errors="coerce")

    crossed = 0
    if {"bid_price", "ask_price"}.issubset(numeric.columns):
        valid = numeric["bid_price"].notna() & numeric["ask_price"].notna()
        crossed = int((valid & (numeric["bid_price"] > numeric["ask_price"])).sum())

    blockers: list[str] = []
    if missing:
        blockers.append("missing_required_columns")
    if frame.empty:
        blockers.append("empty_file")
    if not timestamps_valid:
        blockers.append("invalid_timestamps")
    if not instrument_count:
        blockers.append("missing_instruments")
    if crossed:
        blockers.append("crossed_quotes")

    return FileAudit(
        path=str(path), sha256=digest, size_bytes=path.stat().st_size,
        rows=int(len(frame)), columns=columns, missing_columns=missing,
        instrument_count=instrument_count,
        first_ts=None if timestamps.empty or timestamps.isna().all() else timestamps.min().isoformat(),
        last_ts=None if timestamps.empty or timestamps.isna().all() else timestamps.max().isoformat(),
        timestamps_valid=timestamps_valid,
        duplicate_rows=int(frame.duplicated().sum()),
        duplicate_ts_instrument_rows=(
            int(frame.duplicated(subset=["ts", "instrument_key"], keep=False).sum())
            if {"ts", "instrument_key"}.issubset(frame.columns) else 0
        ),
        crossed_quote_rows=crossed,
        nonpositive_ltp_rows=(int((numeric["ltp"].notna() & (numeric["ltp"] <= 0)).sum()) if "ltp" in numeric else 0),
        negative_volume_rows=(int((numeric["volume"].notna() & (numeric["volume"] < 0)).sum()) if "volume" in numeric else 0),
        negative_oi_rows=(int((numeric["oi"].notna() & (numeric["oi"] < 0)).sum()) if "oi" in numeric else 0),
        null_rates={column: round(float(frame[column].isna().mean()), 8) for column in frame.columns},
        usable=not blockers,
        blockers=tuple(blockers),
    )


def run_audit(root: Path) -> dict[str, Any]:
    files = [root] if root.is_file() else sorted(root.rglob("*.parquet"))
    audits = [audit_file(path) for path in files]
    schema_fingerprints: dict[str, int] = {}
    for audit in audits:
        key = hashlib.sha256(json.dumps(audit.columns).encode()).hexdigest()
        schema_fingerprints[key] = schema_fingerprints.get(key, 0) + 1

    usable = bool(audits) and all(item.usable for item in audits)
    return {
        "root": str(root),
        "file_count": len(audits),
        "usable_file_count": sum(item.usable for item in audits),
        "total_rows": sum(item.rows for item in audits),
        "total_bytes": sum(item.size_bytes for item in audits),
        "distinct_schema_count": len(schema_fingerprints),
        "schema_fingerprints": schema_fingerprints,
        "verdict": {
            "market_input_replay_usable": usable,
            "candidate_lifecycle_present": False,
            "execution_authority_present": False,
            "scope": "market_input_reconstruction_only",
        },
        "files": [asdict(item) for item in audits],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/upstox_option_tick_replay_audit.json"))
    parser.add_argument("--require-usable", action="store_true")
    args = parser.parse_args()
    report = run_audit(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report["verdict"], sort_keys=True))
    return 0 if not args.require_usable or report["verdict"]["market_input_replay_usable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
