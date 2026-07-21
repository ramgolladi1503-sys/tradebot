#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.ml_strategy_discovery_v2.artifacts import sha256_file

REQUIRED_COLUMNS = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
EXPECTED_ROWS = 375
EXPECTED_START = "09:15"
EXPECTED_END = "15:29"


def _logical_path(corpus: Path, path: Path) -> str:
    resolved_corpus = corpus.resolve()
    try:
        relative_unresolved = path.absolute().relative_to(corpus.absolute())
    except ValueError as exc:
        raise ValueError(f"source path is not under corpus: {path}") from exc
    current = corpus.absolute()
    for part in relative_unresolved.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"source path contains a symlink: {path}")
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_corpus)
    except ValueError as exc:
        raise ValueError(f"source path escapes corpus: {path}") from exc
    return str(Path("runtime/upstox_candidate_replay") / relative)


def _session_metadata(path: Path) -> tuple[str, str]:
    stem = path.stem
    if "_" not in stem:
        raise ValueError(f"source filename lacks symbol/date identity: {path.name}")
    symbol, compact_date = stem.rsplit("_", 1)
    if len(compact_date) != 8 or not compact_date.isdigit():
        raise ValueError(f"source filename date is invalid: {path.name}")
    session_date = f"{compact_date[:4]}-{compact_date[4:6]}-{compact_date[6:]}"
    return symbol, session_date


def _verify_frame(
    frame: pd.DataFrame, *, symbol: str, session_date: str, path: Path
) -> None:
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(
            f"source columns missing path={path} columns={sorted(missing)}"
        )
    timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
    if getattr(timestamps.dt, "tz", None) is None:
        timestamps = timestamps.dt.tz_localize(
            "Asia/Kolkata", ambiguous="raise", nonexistent="raise"
        )
    else:
        timestamps = timestamps.dt.tz_convert("Asia/Kolkata")
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError(f"source timestamps invalid: {path}")
    if len(frame) == EXPECTED_ROWS:
        if (
            timestamps.iloc[0].strftime("%H:%M") != EXPECTED_START
            or timestamps.iloc[-1].strftime("%H:%M") != EXPECTED_END
        ):
            raise ValueError(f"standard session boundary mismatch: {path}")
        if not (timestamps.diff().dropna() == pd.Timedelta(minutes=1)).all():
            raise ValueError(f"standard session cadence mismatch: {path}")
    observed_dates = sorted(set(timestamps.dt.date.astype(str)))
    if observed_dates != [session_date]:
        raise ValueError(f"session date mismatch path={path} observed={observed_dates}")
    observed_symbols = sorted(set(frame["symbol"].astype(str).str.upper().str.strip()))
    if len(observed_symbols) != 1:
        raise ValueError(f"source contains multiple symbols: {path}")


def build_manifest(corpus_dir: str | Path) -> dict:
    corpus = Path(corpus_dir).expanduser().resolve()
    if not corpus.is_dir():
        raise ValueError(f"corpus directory is missing: {corpus}")
    records: list[dict] = []
    exclusions: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(corpus.glob("*/underlying/*.parquet")):
        symbol, session_date = _session_metadata(path)
        identity = (symbol.upper(), session_date)
        if identity in seen:
            raise ValueError(f"duplicate symbol/session source: {identity}")
        seen.add(identity)
        frame = pd.read_parquet(path)
        _verify_frame(frame, symbol=symbol, session_date=session_date, path=path)
        logical = _logical_path(corpus, path)
        if len(frame) != EXPECTED_ROWS:
            reason = (
                "MUHURAT_TRADING_SESSION"
                if session_date in {"2024-11-01", "2025-10-21"}
                else "NON_STANDARD_OR_INCOMPLETE_SESSION"
            )
            exclusions.append(
                {
                    "policy": "EXCLUDE_SPECIAL_SESSION_WITH_RECORDED_REASON",
                    "session_date": session_date,
                    "symbol": symbol,
                    "expected_rows": EXPECTED_ROWS,
                    "actual_rows": int(len(frame)),
                    "reason": reason,
                    "logical_path": logical,
                    "actual_sha256": sha256_file(path),
                }
            )
            continue
        digest = sha256_file(path)
        records.append(
            {
                "logical_path": logical,
                "symbol": symbol,
                "session_date": session_date,
                "actual_sha256": digest,
                "byte_size": int(path.stat().st_size),
                "row_count": int(len(frame)),
                "source_record_id": f"{symbol}_{session_date}",
                "inventory_record_identity": {
                    "actual_sha256": digest,
                    "byte_size": int(path.stat().st_size),
                    "logical_path": logical,
                    "row_count": int(len(frame)),
                },
            }
        )
    records.sort(
        key=lambda item: (
            item["session_date"],
            item["logical_path"],
            item["actual_sha256"],
        )
    )
    exclusions.sort(key=lambda item: (item["session_date"], item["logical_path"]))
    if not records:
        raise ValueError("manifest would contain no complete sessions")
    return {
        "source_manifest_version": "v2.1",
        "source_authority_logical_root": "runtime/upstox_candidate_replay",
        "session_contract": {
            "timezone": "Asia/Kolkata",
            "bar_interval_minutes": 1,
            "standard_rows": EXPECTED_ROWS,
            "standard_start": EXPECTED_START,
            "standard_end": EXPECTED_END,
        },
        "special_session_policies": exclusions,
        "record_count": len(records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic V2.1 certified source manifest"
    )
    parser.add_argument("--corpus-dir", required=True)
    parser.add_argument("--out-manifest", required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.corpus_dir)
    output = Path(args.out_manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    digest = sha256_file(output)
    Path(f"{output}.sha256").write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
