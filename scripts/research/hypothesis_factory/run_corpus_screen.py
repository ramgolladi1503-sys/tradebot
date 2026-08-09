#!/usr/bin/env python3
"""Run the Strategy Certification Kernel against local/GDrive-synced corpus files.

This runner is intentionally research-only. It discovers CSV/Parquet files from
known local corpus roots or user-provided roots, loads either ready OHLC rows or
tick rows, converts valid tick rows into minute OHLC bars, executes the cheap
hypothesis screen, and writes a reproducible run directory.

It never certifies edge, never grants runtime authority, and never touches
TradeBot runtime/risk/execution/broker code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MODULE_PATH = Path(__file__).resolve().parent / "hypothesis_factory.py"
spec = importlib.util.spec_from_file_location("hypothesis_factory", MODULE_PATH)
hf = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = hf
spec.loader.exec_module(hf)

DEFAULT_GLOBS = ("*.csv", "*.parquet")
KNOWN_CORPUS_ROOTS = (
    "/Users/madhuram/tradebot/runtime/upstox_candidate_replay",
    "/Users/madhuram/tradebot/runtime",
    "/Users/madhuram/tradebot/.runtime/market_data",
    "/Users/madhuram/tradebot-ml-evidence",
    "/Users/madhuram/tradebot-research-corpus",
)
GDRIVE_NAME_HINTS = ("tradebot_market_data", "upstox_market_data", "market_data", "kite_candidate_replay")

TIMESTAMP_ALIASES = (
    "timestamp", "datetime", "time", "ts", "exchange_timestamp", "exchange_ts",
    "last_trade_time", "last_traded_time", "last_trade_timestamp", "ltt", "received_at",
)
INSTRUMENT_ALIASES = (
    "instrument", "symbol", "tradingsymbol", "trading_symbol", "ticker",
    "instrument_key", "instrument_token", "token", "exchange_token", "name",
)
OPEN_ALIASES = ("open", "o")
HIGH_ALIASES = ("high", "h")
LOW_ALIASES = ("low", "l")
CLOSE_ALIASES = ("close", "c")
PRICE_ALIASES = (
    "ltp", "last_price", "last_traded_price", "last_trade_price", "price", "last", "close", "c",
)
BID_ALIASES = ("bid", "best_bid", "bid_price", "best_bid_price", "depth_buy_price")
ASK_ALIASES = ("ask", "best_ask", "ask_price", "best_ask_price", "depth_sell_price")
VOLUME_ALIASES = ("volume", "vol", "ltq", "last_traded_quantity", "last_quantity", "qty", "quantity")
VWAP_ALIASES = ("vwap", "average_price", "avg_price", "avg_trade_price")
FALLBACK_ALIASES = ("is_fallback", "fallback", "recovered_fallback", "source_quality", "data_quality")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def lower_keys(raw: dict[str, Any]) -> dict[str, Any]:
    return {str(k).strip().lower(): v for k, v in raw.items()}


def pick(row: dict[str, Any], aliases: Iterable[str], default: Any = None) -> Any:
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "fallback", "recovered_fallback"}


def detect_fallback(row: dict[str, Any]) -> bool:
    for key in FALLBACK_ALIASES:
        value = row.get(key)
        if truthy(value):
            return True
        if isinstance(value, str) and value.strip().lower() in {"fallback", "recovered_fallback"}:
            return True
    return False


def derive_instrument(value: Any, source_path: Path) -> str:
    raw = str(value or "").upper()
    path = str(source_path).upper()
    text = raw or path
    if "BANKNIFTY" in text or "BANK_NIFTY" in text or "NIFTY BANK" in text or "BANK NIFTY" in text:
        return "BANKNIFTY"
    if "NIFTY" in text:
        return "NIFTY"
    return raw if raw else "UNKNOWN"


def raw_instrument_id(value: Any, source_path: Path, normalized_instrument: str | None = None) -> str:
    raw = str(value or "").strip()
    if raw:
        return raw
    if normalized_instrument and normalized_instrument != "UNKNOWN":
        return normalized_instrument
    return f"SOURCE::{source_path.name}"


def minute_stamp(value: Any) -> str:
    if value is None or value == "":
        return ""
    text = str(value).strip()
    if isinstance(value, (int, float)) or text.isdigit():
        raw = float(value)
        if raw > 10_000_000_000:
            raw = raw / 1000.0
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:00")
        except (OSError, OverflowError, ValueError):
            return ""
    text = text.replace(" ", "T")
    if len(text) >= 16:
        return text[:16] + ":00"
    return text


def has_explicit_ohlc(row: dict[str, Any]) -> bool:
    return (
        pick(row, OPEN_ALIASES) is not None
        and pick(row, HIGH_ALIASES) is not None
        and pick(row, LOW_ALIASES) is not None
        and pick(row, CLOSE_ALIASES) is not None
    )


def normalize_ohlc_row(raw: dict[str, Any], source_path: Path) -> dict[str, Any] | None:
    row = lower_keys(raw)
    if not has_explicit_ohlc(row):
        return None
    timestamp = pick(row, TIMESTAMP_ALIASES)
    instrument_value = pick(row, INSTRUMENT_ALIASES)
    open_ = as_float(pick(row, OPEN_ALIASES))
    high = as_float(pick(row, HIGH_ALIASES))
    low = as_float(pick(row, LOW_ALIASES))
    close = as_float(pick(row, CLOSE_ALIASES))
    stamp = minute_stamp(timestamp)
    instrument_name = derive_instrument(instrument_value, source_path)
    if not stamp or instrument_name == "UNKNOWN" or None in (open_, high, low, close):
        return None
    out = dict(row)
    out.update({
        "timestamp": stamp,
        "instrument": instrument_name,
        "raw_instrument": raw_instrument_id(instrument_value, source_path, instrument_name),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": as_float(pick(row, VOLUME_ALIASES), 0.0) or 0.0,
        "vwap": as_float(pick(row, VWAP_ALIASES), close) or close,
        "bid": as_float(pick(row, BID_ALIASES), 0.0) or 0.0,
        "ask": as_float(pick(row, ASK_ALIASES), 0.0) or 0.0,
        "source_path": str(source_path),
        "is_fallback": detect_fallback(row),
    })
    return out


def normalize_tick_row(raw: dict[str, Any], source_path: Path) -> dict[str, Any] | None:
    row = lower_keys(raw)
    price = as_float(pick(row, PRICE_ALIASES))
    stamp = minute_stamp(pick(row, TIMESTAMP_ALIASES))
    if price is None or price <= 0 or not stamp:
        return None
    instrument_value = pick(row, INSTRUMENT_ALIASES)
    instrument = derive_instrument(instrument_value, source_path)
    if instrument == "UNKNOWN":
        return None
    return {
        "timestamp": stamp,
        "instrument": instrument,
        "raw_instrument": raw_instrument_id(instrument_value, source_path, instrument),
        "price": price,
        "volume": as_float(pick(row, VOLUME_ALIASES), 0.0) or 0.0,
        "vwap": as_float(pick(row, VWAP_ALIASES), price) or price,
        "bid": as_float(pick(row, BID_ALIASES), 0.0) or 0.0,
        "ask": as_float(pick(row, ASK_ALIASES), 0.0) or 0.0,
        "is_fallback": detect_fallback(row),
        "source_path": str(source_path),
    }


def aggregate_ticks_to_minute_ohlc(ticks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for tick in ticks:
        if tick.get("is_fallback"):
            continue
        key = (str(tick["instrument"]), str(tick.get("raw_instrument", "")), str(tick["timestamp"]))
        price = float(tick["price"])
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "timestamp": tick["timestamp"],
                "instrument": tick["instrument"],
                "raw_instrument": tick.get("raw_instrument", ""),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": float(tick.get("volume") or 0.0),
                "vwap": float(tick.get("vwap") or price),
                "bid": float(tick.get("bid") or 0.0),
                "ask": float(tick.get("ask") or 0.0),
                "is_fallback": False,
                "source_path": tick.get("source_path", ""),
            }
        else:
            bucket["high"] = max(float(bucket["high"]), price)
            bucket["low"] = min(float(bucket["low"]), price)
            bucket["close"] = price
            bucket["volume"] = float(bucket.get("volume") or 0.0) + float(tick.get("volume") or 0.0)
            bucket["vwap"] = float(tick.get("vwap") or bucket.get("vwap") or price)
            bucket["bid"] = float(tick.get("bid") or bucket.get("bid") or 0.0)
            bucket["ask"] = float(tick.get("ask") or bucket.get("ask") or 0.0)
    return sorted(buckets.values(), key=lambda r: (str(r["instrument"]), str(r.get("raw_instrument", "")), str(r["timestamp"])))


def normalize_loaded_rows(raw_rows: list[dict[str, Any]], source_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ohlc_rows: list[dict[str, Any]] = []
    tick_rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        ohlc = normalize_ohlc_row(raw, source_path)
        if ohlc is not None:
            ohlc_rows.append(ohlc)
            continue
        tick = normalize_tick_row(raw, source_path)
        if tick is not None:
            tick_rows.append(tick)
    tick_ohlc = aggregate_ticks_to_minute_ohlc(tick_rows)
    rows = ohlc_rows + tick_ohlc
    rows.sort(key=lambda r: (str(r.get("instrument", "")), str(r.get("raw_instrument", "")), str(r.get("timestamp", ""))))
    return rows, {
        "raw_rows": len(raw_rows),
        "normalized_ohlc_rows": len(ohlc_rows),
        "normalized_tick_rows": len(tick_rows),
        "tick_ohlc_rows": len(tick_ohlc),
    }


def load_csv(path: Path, max_rows: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    try:
        raw_rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8", newline="", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader):
                if max_rows is not None and idx >= max_rows:
                    break
                raw_rows.append(row)
        normalized, meta = normalize_loaded_rows(raw_rows, path)
        meta["columns"] = list(raw_rows[0].keys()) if raw_rows else []
        return normalized, meta, None
    except Exception as exc:
        return [], {}, f"{type(exc).__name__}: {exc}"


def load_parquet(path: Path, max_rows: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    try:
        import pandas as pd
        df = pd.read_parquet(path)
        if max_rows is not None:
            df = df.head(max_rows)
        raw_rows = df.to_dict(orient="records")
        normalized, meta = normalize_loaded_rows(raw_rows, path)
        meta["columns"] = [str(c) for c in df.columns]
        return normalized, meta, None
    except Exception as exc:
        return [], {}, f"{type(exc).__name__}: {exc}"


def discover_roots(user_roots: list[str], include_known: bool = True, include_gdrive: bool = True) -> list[Path]:
    candidates: list[Path] = [Path(p).expanduser() for p in user_roots]
    if include_known:
        candidates.extend(Path(p) for p in KNOWN_CORPUS_ROOTS)
    if include_gdrive:
        for parent in (Path.home() / "Library/CloudStorage", Path.home() / "Google Drive", Path.home()):
            if not parent.exists():
                continue
            try:
                for path in parent.rglob("*"):
                    if path.is_dir() and path.name.lower() in GDRIVE_NAME_HINTS:
                        candidates.append(path)
            except (OSError, PermissionError):
                continue
    seen: set[str] = set()
    roots: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key not in seen and resolved.exists():
            seen.add(key)
            roots.append(resolved)
    return roots


def discover_files(roots: Iterable[Path], patterns: Iterable[str], max_files: int | None) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix.lower() in {".csv", ".parquet"}:
                found.append(root)
            continue
        for pattern in patterns:
            try:
                found.extend(p for p in root.rglob(pattern) if p.is_file())
            except (OSError, PermissionError):
                continue
    out = sorted(set(found))
    if max_files is not None:
        return out[:max_files]
    return out


def load_corpus(files: Iterable[Path], max_rows_total: int | None, max_rows_per_file: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_rows: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    for path in files:
        if max_rows_total is not None and len(all_rows) >= max_rows_total:
            break
        remaining = None if max_rows_total is None else max_rows_total - len(all_rows)
        per_file = max_rows_per_file if remaining is None else min(max_rows_per_file or remaining, remaining)
        if path.suffix.lower() == ".csv":
            rows, meta, error = load_csv(path, per_file)
        elif path.suffix.lower() == ".parquet":
            rows, meta, error = load_parquet(path, per_file)
        else:
            rows, meta, error = [], {}, "unsupported extension"
        if remaining is not None:
            rows = rows[:remaining]
        inventory.append({
            "path": str(path),
            "suffix": path.suffix.lower(),
            "sha256": sha256_file(path),
            "loaded_rows": len(rows),
            "error": error,
            **meta,
        })
        all_rows.extend(rows)
    return all_rows, inventory


def inventory_summary(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "files": len(inventory),
        "files_with_errors": sum(1 for item in inventory if item.get("error")),
        "files_with_loaded_rows": sum(1 for item in inventory if int(item.get("loaded_rows") or 0) > 0),
        "raw_rows": sum(int(item.get("raw_rows") or 0) for item in inventory),
        "normalized_ohlc_rows": sum(int(item.get("normalized_ohlc_rows") or 0) for item in inventory),
        "normalized_tick_rows": sum(int(item.get("normalized_tick_rows") or 0) for item in inventory),
        "tick_ohlc_rows": sum(int(item.get("tick_ohlc_rows") or 0) for item in inventory),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    roots = discover_roots(args.corpus_root, not args.no_known_roots, not args.no_gdrive_discovery)
    files = discover_files(roots, args.pattern or DEFAULT_GLOBS, args.max_files)
    rows, inventory = load_corpus(files, args.max_rows_total, args.max_rows_per_file)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("RUN-%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir) / run_id
    instruments = sorted({i.strip().upper() for i in args.instrument if i.strip()}) or ["NIFTY", "BANKNIFTY"]
    hypotheses = hf.generate_hypotheses(instruments=instruments)
    config = hf.ScreenConfig(
        max_hold_bars=args.max_hold_bars,
        min_trades=args.min_trades,
        spread_max_pct=args.spread_max_pct,
        cost_bps=args.cost_bps,
        min_net_expectancy_bps=args.min_net_expectancy_bps,
    )
    results = hf.screen_hypotheses(hypotheses, rows, config)
    ranked = sorted(results, key=lambda r: r.get("score", -1), reverse=True)
    passports = []
    by_id = {h["hypothesis_id"]: h for h in hypotheses}
    for row in ranked[: args.top_passports]:
        passports.append(hf.make_passport(by_id[row["hypothesis_id"]], row))

    hf.write_json(out_dir / "generated_hypotheses.json", hypotheses)
    hf.write_json(out_dir / "screen_results.json", ranked)
    hf.write_csv(out_dir / "leaderboard.csv", ranked)
    hf.write_json(out_dir / "strategy_passports.json", passports)
    hf.write_json(out_dir / "corpus_inventory.json", {"files": inventory})
    manifest = {
        "schema_version": "tradebot-hypothesis-corpus-run-v1",
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "certification": "NOT_CERTIFIED",
        "corpus_roots": [str(p) for p in roots],
        "discovered_files": len(files),
        "loaded_rows": len(rows),
        "hypotheses": len(hypotheses),
        "screen_results": len(ranked),
        "promising_not_certified": sum(1 for r in ranked if r.get("status") == "PROMISING_NOT_CERTIFIED"),
        "top_passports": len(passports),
        "config": vars(args),
        "outputs": {
            "generated_hypotheses": str(out_dir / "generated_hypotheses.json"),
            "screen_results": str(out_dir / "screen_results.json"),
            "leaderboard": str(out_dir / "leaderboard.csv"),
            "strategy_passports": str(out_dir / "strategy_passports.json"),
            "corpus_inventory": str(out_dir / "corpus_inventory.json"),
        },
        "inventory_summary": inventory_summary(inventory),
        "inventory": inventory,
    }
    hf.write_json(out_dir / "run_manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", action="append", default=[], help="Corpus root/file; repeatable")
    parser.add_argument("--pattern", action="append", default=[], help="Glob pattern; default *.csv and *.parquet")
    parser.add_argument("--instrument", action="append", default=[], help="Instrument universe; repeatable")
    parser.add_argument("--output-dir", default="research/hypotheses/corpus_runs")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--max-rows-total", type=int, default=250000)
    parser.add_argument("--max-rows-per-file", type=int, default=10000)
    parser.add_argument("--top-passports", type=int, default=10)
    parser.add_argument("--max-hold-bars", type=int, default=6)
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--spread-max-pct", type=float, default=0.02)
    parser.add_argument("--cost-bps", type=float, default=8.0)
    parser.add_argument("--min-net-expectancy-bps", type=float, default=0.0)
    parser.add_argument("--no-known-roots", action="store_true")
    parser.add_argument("--no-gdrive-discovery", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = run(args)
    print(json.dumps({k: manifest[k] for k in ("run_id", "loaded_rows", "hypotheses", "screen_results", "promising_not_certified")}, indent=2))
    return 0 if manifest["loaded_rows"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
