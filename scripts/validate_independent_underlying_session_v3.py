#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATA_ROOT = Path("/Users/madhuram/tradebot-data/independent_underlying_confirmation_v3")
RESEARCH_ROOT = Path("research/independent_underlying_confirmation_v3/data_acquisition")
SYMBOLS = ("NIFTY", "BANKNIFTY", "SENSEX")
SAFETY_FLAGS = {"read_only": True, "is_order_action": False, "broker_api_called": False, "execution_eligibility": False, "allowed_for_live_execution": False}
REQUIRED_COLUMNS = {
    "timestamp",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "source",
    "interval",
    "data_origin",
    "synthetic",
    "mock",
    "fallback",
    "provider",
    "source_endpoint_family",
    "fetch_timestamp_utc",
    "source_chunk_start",
    "source_chunk_end",
    "instrument_key_hash",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n")


def validate_frame(df: pd.DataFrame) -> str:
    if not REQUIRED_COLUMNS.issubset(df.columns):
        return "PROVENANCE_FAILURE"
    ts = pd.to_datetime(df["timestamp"])
    if getattr(ts.dt, "tz", None) is None:
        return "PROVENANCE_FAILURE"
    if not ts.is_monotonic_increasing or ts.duplicated().any():
        return "DUPLICATE_ROWS"
    for col in ["open", "high", "low", "close"]:
        if not pd.to_numeric(df[col], errors="coerce").map(lambda x: pd.notna(x) and x > 0).all():
            return "NONFINITE_VALUES"
    if not ((df["high"] >= df[["open", "close", "low"]].max(axis=1)) & (df["low"] <= df[["open", "close", "high"]].min(axis=1))).all():
        return "INVALID_OHLC"
    if bool(df[["synthetic", "mock", "fallback"]].any(axis=None)):
        return "PROVENANCE_FAILURE"
    return "ELIGIBLE_SYMBOL_FILE"


def _load_exhausted_sessions() -> set[str]:
    from research.prospective_structural_edge_v2.cycle5_failure_runner import development_sessions

    return set(development_sessions())


def _resolution() -> dict[str, dict[str, str]]:
    path = RESEARCH_ROOT / "underlying_instrument_resolution.json"
    data = json.loads(path.read_text())
    return data["resolved"]


def _canonical_frame(symbol: str, path: Path, resolution: dict[str, dict[str, str]], source_hash: str) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    records = []
    for candle in payload.get("data", {}).get("candles", []):
        ts = pd.Timestamp(candle[0])
        if ts.tzinfo is None:
            raise ValueError("naive timestamp rejected")
        ts = ts.tz_convert("Asia/Kolkata")
        records.append(
            {
                "timestamp": ts,
                "symbol": symbol,
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
                "oi": float(candle[6]) if len(candle) > 6 else 0.0,
                "source": "upstox",
                "interval": "1minute",
                "data_origin": "upstox_historical_v3",
                "synthetic": False,
                "mock": False,
                "fallback": False,
                "provider": "upstox",
                "source_endpoint_family": "historical-candle-v3",
                "fetch_timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
                "source_chunk_start": path.stem.split("_")[-2],
                "source_chunk_end": path.stem.split("_")[-1],
                "instrument_key_hash": resolution[symbol]["instrument_key_hash"],
                "data_type": "TRUSTED_UNDERLYING_1M_CANDLES",
                "source_chunk_hash": source_hash,
            }
        )
    df = pd.DataFrame.from_records(records)
    if not df.empty:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def split_from_staging() -> dict[str, Any]:
    resolution = _resolution()
    exhausted = _load_exhausted_sessions()
    by_symbol_date: dict[str, dict[str, pd.DataFrame]] = {symbol: {} for symbol in SYMBOLS}
    source_hashes: dict[str, str] = {}
    for symbol in SYMBOLS:
        for path in sorted((DATA_ROOT / "monthly_staging" / symbol).glob("*.json")):
            source_hashes[str(path)] = sha256_file(path)
            df = _canonical_frame(symbol, path, resolution, source_hashes[str(path)])
            if df.empty:
                continue
            for session_date, sdf in df.groupby(df["timestamp"].dt.strftime("%Y%m%d")):
                by_symbol_date[symbol][session_date] = sdf.reset_index(drop=True)

    all_dates = sorted(set().union(*(set(v) for v in by_symbol_date.values())))
    standard_counts = []
    for session in all_dates:
        if all(session in by_symbol_date[symbol] for symbol in SYMBOLS):
            grids = [tuple(by_symbol_date[symbol][session]["timestamp"].astype(str)) for symbol in SYMBOLS]
            if grids[0] == grids[1] == grids[2]:
                standard_counts.append(len(grids[0]))
    dominant_count = pd.Series(standard_counts).mode().iloc[0] if standard_counts else 0
    session_records = []
    validation_records = []
    for session in all_dates:
        if session in exhausted:
            classification = "EXHAUSTED_CORPUS_SESSION"
        elif not all(session in by_symbol_date[symbol] for symbol in SYMBOLS):
            classification = "INCOMPLETE_SYMBOL_SET"
        else:
            frames = {symbol: by_symbol_date[symbol][session] for symbol in SYMBOLS}
            verdicts = {symbol: validate_frame(df) for symbol, df in frames.items()}
            grids = {symbol: tuple(df["timestamp"].astype(str)) for symbol, df in frames.items()}
            if any(v != "ELIGIBLE_SYMBOL_FILE" for v in verdicts.values()):
                classification = next(v for v in verdicts.values() if v != "ELIGIBLE_SYMBOL_FILE")
            elif len({grids[symbol] for symbol in SYMBOLS}) != 1:
                classification = "CROSS_INDEX_GRID_MISMATCH"
            elif len(next(iter(grids.values()))) != dominant_count:
                classification = "NONSTANDARD_SPECIAL_SESSION"
            else:
                classification = "ELIGIBLE_INDEPENDENT_SESSION"
        validation_records.append({"session_date": session, "classification": classification})
        if classification == "ELIGIBLE_INDEPENDENT_SESSION":
            out_dir = DATA_ROOT / "sessions" / session / "underlying"
            manifest_dir = DATA_ROOT / "sessions" / session / "manifests"
            out_dir.mkdir(parents=True, exist_ok=True)
            manifest_dir.mkdir(parents=True, exist_ok=True)
            symbol_paths = {}
            row_counts = {}
            file_hashes = {}
            first_ts = None
            last_ts = None
            grid_hash = hashlib.sha256(json.dumps(list(grids[SYMBOLS[0]]), sort_keys=True).encode()).hexdigest()
            for symbol in SYMBOLS:
                out_path = out_dir / f"{symbol}_{session}.parquet"
                if out_path.exists():
                    old_hash = sha256_file(out_path)
                    tmp_path = out_dir / f".{symbol}_{session}.tmp.parquet"
                    by_symbol_date[symbol][session].to_parquet(tmp_path)
                    new_hash = sha256_file(tmp_path)
                    if old_hash != new_hash:
                        quarantine = DATA_ROOT / "quarantine" / "identity_drift"
                        quarantine.mkdir(parents=True, exist_ok=True)
                        tmp_path.rename(quarantine / tmp_path.name)
                        raise RuntimeError(f"IDENTITY_DRIFT {out_path}")
                    tmp_path.unlink()
                else:
                    by_symbol_date[symbol][session].to_parquet(out_path)
                symbol_paths[symbol] = str(out_path)
                file_hashes[symbol] = sha256_file(out_path)
                row_counts[symbol] = int(len(by_symbol_date[symbol][session]))
                first_ts = str(by_symbol_date[symbol][session]["timestamp"].iloc[0])
                last_ts = str(by_symbol_date[symbol][session]["timestamp"].iloc[-1])
            record = {
                "session_date": f"{session[:4]}-{session[4:6]}-{session[6:]}",
                "symbol_file_paths": symbol_paths,
                "row_counts": row_counts,
                "first_timestamp": first_ts,
                "last_timestamp": last_ts,
                "minute_grid_hash": grid_hash,
                "schema_hash": hashlib.sha256(json.dumps(sorted(REQUIRED_COLUMNS), sort_keys=True).encode()).hexdigest(),
                "file_sha256_hashes": file_hashes,
                "provider": "upstox",
                "instrument_key_hashes": {symbol: resolution[symbol]["instrument_key_hash"] for symbol in SYMBOLS},
                "source_chunk_identities": {
                    symbol: sorted(set(by_symbol_date[symbol][session]["source_chunk_hash"].tolist()))
                    for symbol in SYMBOLS
                },
                "synthetic": False,
                "mock": False,
                "fallback": False,
                "novelty_classification": "ELIGIBLE_INDEPENDENT_SESSION",
            }
            session_records.append(record)
            write_json(manifest_dir / f"session_manifest_{session}.json", record)
    ordered = sorted(session_records, key=lambda r: r["session_date"])
    manifest = {
        "sessions": ordered,
        "session_list_hash": hashlib.sha256(json.dumps(ordered, sort_keys=True).encode()).hexdigest(),
        "append_only": True,
        "opened": False,
        "safety_flags": SAFETY_FLAGS,
    }
    manifest_path = Path("research/independent_underlying_confirmation_v3/independent_session_manifest.json")
    write_json(manifest_path, manifest)
    write_text(Path("research/independent_underlying_confirmation_v3/independent_session_manifest.md"), f"# Independent Session Manifest\n\nEligible sessions: `{len(ordered)}`\n\nOpened: `NO`\n")
    summary = {
        "records": validation_records,
        "eligible_independent_sessions": len(ordered),
        "dominant_bar_count": int(dominant_count),
        "nonstandard_sessions_excluded": sum(1 for r in validation_records if r["classification"] == "NONSTANDARD_SPECIAL_SESSION"),
        "incomplete_sessions_excluded": sum(1 for r in validation_records if r["classification"] == "INCOMPLETE_SYMBOL_SET"),
        "exhausted_corpus_overlap": sum(1 for r in validation_records if r["classification"] == "EXHAUSTED_CORPUS_SESSION"),
        "old_lockbox_overlap": 0,
        "strategy_candidate_counts_calculated": False,
        "strategy_outcomes_calculated": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_json(RESEARCH_ROOT / "session_validation_summary.json", summary)
    write_text(RESEARCH_ROOT / "session_validation_summary.md", f"# Session Validation Summary\n\nEligible independent sessions: `{len(ordered)}`\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--from-staging", action="store_true")
    parser.add_argument("--output", default="research/independent_underlying_confirmation_v3/data_acquisition/session_validation_summary.json")
    args = parser.parse_args()
    if args.from_staging:
        split_from_staging()
        return 0
    records = []
    for raw in args.files:
        path = Path(raw)
        try:
            df = pd.read_parquet(path)
            verdict = validate_frame(df)
        except Exception as exc:
            verdict = f"SCHEMA_INCOMPATIBLE:{type(exc).__name__}"
        records.append({"path": str(path), "sha256": sha256_file(path) if path.exists() else None, "verdict": verdict})
    write_json(Path(args.output), {"records": records, "strategy_candidate_counts_calculated": False, "strategy_outcomes_calculated": False, "safety_flags": SAFETY_FLAGS})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
