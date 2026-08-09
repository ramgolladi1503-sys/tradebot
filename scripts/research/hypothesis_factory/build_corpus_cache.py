#!/usr/bin/env python3
"""Build a reusable canonical OHLC cache from TradeBot research corpus files.

Purpose:
- scan expensive/raw corpus files once;
- normalize usable OHLC/tick data once;
- cache per-file normalized rows;
- skip unchanged files on later runs;
- emit canonical per-instrument CSVs for fast repeated hypothesis screening.

Research-only. Never certifies edge and never grants runtime/broker authority.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNNER_PATH = HERE / "run_corpus_screen.py"
spec = importlib.util.spec_from_file_location("run_corpus_screen", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

CACHE_SCHEMA = "tradebot-canonical-corpus-cache-v2"
CANONICAL_FIELDS = [
    "timestamp", "instrument", "raw_instrument", "open", "high", "low", "close",
    "volume", "vwap", "bid", "ask", "is_fallback", "source_path",
]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in CANONICAL_FIELDS})


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def file_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def cache_key(path: Path) -> str:
    import hashlib
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]


def load_one(path: Path, max_rows: int | None) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return runner.load_csv(path, max_rows)
    if suffix == ".parquet":
        return runner.load_parquet(path, max_rows)
    return [], {}, "unsupported extension"


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate exact contract/timestamp/OHLC/source rows without fabricating aggregation."""
    seen: set[tuple[str, ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("is_fallback", "")).strip().lower() in {"true", "1", "yes", "fallback", "recovered_fallback"}:
            continue
        key = (
            str(row.get("instrument", "")), str(row.get("raw_instrument", "")), str(row.get("timestamp", "")),
            str(row.get("open", "")), str(row.get("high", "")), str(row.get("low", "")), str(row.get("close", "")),
            str(row.get("source_path", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    out.sort(key=lambda r: (str(r.get("instrument", "")), str(r.get("raw_instrument", "")), str(r.get("timestamp", "")), str(r.get("source_path", ""))))
    return out


def build(args: argparse.Namespace) -> dict[str, Any]:
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    file_cache_dir = cache_dir / "files"
    canonical_dir = cache_dir / "canonical"
    index_path = cache_dir / "corpus_index.json"
    prior = read_json(index_path, {})
    prior_files = prior.get("files", {}) if isinstance(prior, dict) else {}
    prior_schema = str(prior.get("schema_version", "")) if isinstance(prior, dict) else ""
    schema_matches = prior_schema == CACHE_SCHEMA

    roots = runner.discover_roots(args.corpus_root, not args.no_known_roots, not args.no_gdrive_discovery)
    files = runner.discover_files(roots, args.pattern or runner.DEFAULT_GLOBS, args.max_files)

    index_files: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    reused = 0
    reparsed = 0
    errors = 0
    usable_files = 0

    for idx, path in enumerate(files, 1):
        pkey = str(path.resolve())
        sig = file_signature(path)
        ckey = cache_key(path)
        cached_rows_path = file_cache_dir / f"{ckey}.csv"
        old = prior_files.get(pkey, {}) if schema_matches else {}
        unchanged = old.get("signature") == sig
        can_reuse = unchanged and old.get("status") == "USABLE" and cached_rows_path.exists()
        can_reuse_bad = unchanged and old.get("status") == "UNUSABLE"

        rows: list[dict[str, Any]] = []
        meta: dict[str, Any] = dict(old.get("meta") or {})
        error: str | None = old.get("error")
        status = old.get("status", "UNSEEN")

        if can_reuse:
            rows = read_rows(cached_rows_path)
            reused += 1
            status = "USABLE"
        elif can_reuse_bad and not args.recheck_unusable:
            reused += 1
            status = "UNUSABLE"
        else:
            rows, meta, error = load_one(path, args.max_rows_per_file)
            reparsed += 1
            rows = dedupe_rows(rows)
            if rows:
                write_rows(cached_rows_path, rows)
                status = "USABLE"
            else:
                status = "UNUSABLE"
                if cached_rows_path.exists():
                    cached_rows_path.unlink()

        if status == "USABLE":
            usable_files += 1
            all_rows.extend(rows)
        if error:
            errors += 1

        index_files[pkey] = {
            "signature": sig,
            "status": status,
            "cache_file": str(cached_rows_path) if status == "USABLE" else None,
            "loaded_rows": len(rows) if status == "USABLE" else int(old.get("loaded_rows", 0) if can_reuse_bad else 0),
            "error": error,
            "meta": meta,
        }

        if args.progress_every and idx % args.progress_every == 0:
            print(f"indexed={idx}/{len(files)} reusable={reused} reparsed={reparsed} usable={usable_files}", flush=True)

    all_rows = dedupe_rows(all_rows)
    by_instrument: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        instrument = str(row.get("instrument", "UNKNOWN")).upper()
        if args.instrument and instrument not in args.instrument:
            continue
        by_instrument.setdefault(instrument, []).append(row)

    canonical_outputs: dict[str, Any] = {}
    for instrument, rows in sorted(by_instrument.items()):
        out = canonical_dir / f"{instrument}.csv"
        write_rows(out, rows)
        canonical_outputs[instrument] = {
            "path": str(out),
            "rows": len(rows),
            "sha256": runner.sha256_file(out),
        }

    manifest = {
        "schema_version": CACHE_SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "certification": "NOT_CERTIFIED",
        "roots": [str(p) for p in roots],
        "files_discovered": len(files),
        "files_reused": reused,
        "files_reparsed": reparsed,
        "files_usable": usable_files,
        "files_with_errors": errors,
        "canonical_rows": sum(v["rows"] for v in canonical_outputs.values()),
        "canonical_outputs": canonical_outputs,
        "files": index_files,
    }
    write_json(index_path, manifest)
    write_json(cache_dir / "cache_manifest.json", {k: v for k, v in manifest.items() if k != "files"})
    return manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--corpus-root", action="append", default=[])
    p.add_argument("--pattern", action="append", default=[])
    p.add_argument("--instrument", action="append", default=[])
    p.add_argument("--cache-dir", default="research/hypotheses/corpus_cache")
    p.add_argument("--max-files", type=int, default=3000)
    p.add_argument("--max-rows-per-file", type=int, default=100000)
    p.add_argument("--progress-every", type=int, default=100)
    p.add_argument("--recheck-unusable", action="store_true")
    p.add_argument("--no-known-roots", action="store_true")
    p.add_argument("--no-gdrive-discovery", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    args.instrument = [x.strip().upper() for x in args.instrument if x.strip()]
    result = build(args)
    print(json.dumps({
        "files_discovered": result["files_discovered"],
        "files_reused": result["files_reused"],
        "files_reparsed": result["files_reparsed"],
        "files_usable": result["files_usable"],
        "files_with_errors": result["files_with_errors"],
        "canonical_rows": result["canonical_rows"],
        "canonical_outputs": result["canonical_outputs"],
        "runtime_authority": result["runtime_authority"],
    }, indent=2))
    return 0 if result["canonical_rows"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
