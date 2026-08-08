#!/usr/bin/env python3
"""Run the Strategy Certification Kernel against local/GDrive-synced corpus files.

This runner is intentionally research-only. It discovers CSV/Parquet files from
known local corpus roots or user-provided roots, loads normalized OHLC rows,
executes the cheap hypothesis screen, and writes a reproducible run directory.

It never certifies edge, never grants runtime authority, and never touches
TradeBot runtime/risk/execution/broker code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
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

REQUIRED_COLUMNS = {"timestamp", "instrument", "open", "high", "low", "close"}
DEFAULT_GLOBS = ("*.csv", "*.parquet")
KNOWN_CORPUS_ROOTS = (
    "/Users/madhuram/tradebot/runtime/upstox_candidate_replay",
    "/Users/madhuram/tradebot/runtime",
    "/Users/madhuram/tradebot/.runtime/market_data",
    "/Users/madhuram/tradebot-ml-evidence",
    "/Users/madhuram/tradebot-research-corpus",
)
GDRIVE_NAME_HINTS = ("tradebot_market_data", "upstox_market_data", "market_data", "kite_candidate_replay")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_google_drive_roots() -> list[Path]:
    roots: list[Path] = []
    cloud = Path.home() / "Library" / "CloudStorage"
    if not cloud.exists():
        return roots
    for candidate in cloud.glob("GoogleDrive-*"):
        for hint in GDRIVE_NAME_HINTS:
            roots.extend(p for p in candidate.rglob(hint) if p.is_dir())
    return sorted(set(roots))


def discover_roots(extra_roots: Iterable[str], include_known: bool, include_gdrive: bool) -> list[Path]:
    roots: list[Path] = []
    if include_known:
        roots.extend(Path(p).expanduser() for p in KNOWN_CORPUS_ROOTS)
    if include_gdrive:
        roots.extend(find_google_drive_roots())
    roots.extend(Path(p).expanduser() for p in extra_roots)
    return [p for p in sorted(set(roots)) if p.exists()]


def discover_files(roots: Iterable[Path], patterns: Iterable[str], max_files: int | None) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if root.is_file():
            found.append(root)
            continue
        for pattern in patterns:
            found.extend(p for p in root.rglob(pattern) if p.is_file())
    out = sorted(set(found))
    if max_files is not None:
        return out[:max_files]
    return out


def normalize_row(raw: dict[str, Any], source_path: Path) -> dict[str, Any] | None:
    lower = {str(k).strip().lower(): v for k, v in raw.items()}
    aliases = {
        "datetime": "timestamp",
        "time": "timestamp",
        "symbol": "instrument",
        "tradingsymbol": "instrument",
        "ticker": "instrument",
        "ltp": "close",
        "last_price": "close",
    }
    for src, dst in aliases.items():
        if dst not in lower and src in lower:
            lower[dst] = lower[src]
    if "open" not in lower and "close" in lower:
        lower["open"] = lower["close"]
    if "high" not in lower and "close" in lower:
        lower["high"] = lower["close"]
    if "low" not in lower and "close" in lower:
        lower["low"] = lower["close"]
    missing = REQUIRED_COLUMNS - lower.keys()
    if missing:
        return None
    lower["source_path"] = str(source_path)
    return lower


def load_csv(path: Path, max_rows: int | None) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = normalize_row(raw, path)
            if row is not None:
                rows.append(row)
            if max_rows is not None and len(rows) >= max_rows:
                break
    return rows, None


def load_parquet(path: Path, max_rows: int | None) -> tuple[list[dict[str, Any]], str | None]:
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local environment
        return [], f"pandas/pyarrow unavailable for parquet: {exc}"
    try:
        frame = pd.read_parquet(path)
        if max_rows is not None:
            frame = frame.head(max_rows)
        rows = []
        for raw in frame.to_dict(orient="records"):
            row = normalize_row(raw, path)
            if row is not None:
                rows.append(row)
        return rows, None
    except Exception as exc:  # pragma: no cover - depends on file contents
        return [], f"parquet load failed: {exc}"


def load_corpus(files: Iterable[Path], max_rows_total: int | None, max_rows_per_file: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_rows: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    for path in files:
        if max_rows_total is not None and len(all_rows) >= max_rows_total:
            break
        remaining = None if max_rows_total is None else max_rows_total - len(all_rows)
        per_file = max_rows_per_file if remaining is None else min(max_rows_per_file or remaining, remaining)
        if path.suffix.lower() == ".csv":
            rows, error = load_csv(path, per_file)
        elif path.suffix.lower() == ".parquet":
            rows, error = load_parquet(path, per_file)
        else:
            rows, error = [], "unsupported extension"
        file_info = {
            "path": str(path),
            "suffix": path.suffix.lower(),
            "sha256": sha256_file(path),
            "loaded_rows": len(rows),
            "error": error,
        }
        inventory.append(file_info)
        all_rows.extend(rows)
    return all_rows, inventory


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    keys = sorted({k for row in rows for k in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> dict[str, Any]:
    roots = discover_roots(args.corpus_root, not args.no_known_roots, not args.no_gdrive_discovery)
    files = discover_files(roots, args.pattern or DEFAULT_GLOBS, args.max_files)
    rows, inventory = load_corpus(files, args.max_rows_total, args.max_rows_per_file)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("RUN-%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir) / run_id
    instruments = [i.strip().upper() for i in args.instrument if i.strip()]
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

    write_json(out_dir / "generated_hypotheses.json", hypotheses)
    write_json(out_dir / "screen_results.json", ranked)
    write_csv(out_dir / "leaderboard.csv", ranked)
    write_json(out_dir / "strategy_passports.json", passports)
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
        },
        "inventory": inventory,
    }
    write_json(out_dir / "run_manifest.json", manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", action="append", default=[], help="Corpus root/file; repeatable")
    parser.add_argument("--pattern", action="append", default=[], help="Glob pattern; default *.csv and *.parquet")
    parser.add_argument("--instrument", action="append", default=["NIFTY", "BANKNIFTY"], help="Instrument universe; repeatable")
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
