#!/usr/bin/env python3
"""Build a canonical research cache from Kite replay UNDERLYING parquet files.

This adapter is intentionally narrow. It consumes the historical-session index,
selects only UNDERLYING files for one requested family, supports Kite candle time
stored either in a `date`-like column or in the pandas index, and emits the same
canonical CSV schema used by the Strategy Certification Kernel.

It fails closed when expected session files cannot be normalized. It never reads
the OPTIONS cohort and never grants certification/runtime/broker authority.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUNNER_PATH = HERE / "run_corpus_screen.py"
spec = importlib.util.spec_from_file_location("run_corpus_screen", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

CANONICAL_FIELDS = [
    "timestamp", "instrument", "raw_instrument", "open", "high", "low", "close",
    "volume", "vwap", "bid", "ask", "is_fallback", "source_path",
]
TIME_COLUMNS = (
    "timestamp", "datetime", "time", "ts", "exchange_timestamp", "exchange_ts",
    "date", "candle_time", "candle_timestamp",
)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def prepare_dataframe(df):
    """Expose Kite candle time as a normal `timestamp` column without guessing prices."""
    import pandas as pd

    out = df.copy()
    lower = {str(c).strip().lower(): c for c in out.columns}
    found = next((lower[name] for name in TIME_COLUMNS if name in lower), None)
    if found is not None:
        if str(found).strip().lower() != "timestamp":
            out["timestamp"] = out[found]
        return out, "COLUMN"

    # Kite replay files may persist candle datetime as the parquet index.
    idx = out.index
    usable_index = not isinstance(idx, pd.RangeIndex)
    if usable_index:
        values = idx
        try:
            parsed = pd.to_datetime(values, errors="coerce")
            valid = int(parsed.notna().sum()) if hasattr(parsed, "notna") else 0
        except Exception:
            valid = 0
        if valid > 0:
            out = out.reset_index()
            index_col = out.columns[0]
            out["timestamp"] = out[index_col]
            return out, "INDEX"

    return out, "MISSING"


def normalize_parquet(path: Path, max_rows: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    try:
        import pandas as pd

        df = pd.read_parquet(path)
        if max_rows is not None:
            df = df.head(max_rows)
        prepared, time_source = prepare_dataframe(df)
        raw_rows = prepared.to_dict(orient="records")

        # Generic runner deliberately has a narrow timestamp vocabulary. The adapter
        # maps Kite's `date`/index semantics to timestamp before normalization.
        normalized, meta = runner.normalize_loaded_rows(raw_rows, path)
        meta.update({
            "columns": [str(c) for c in prepared.columns],
            "time_source": time_source,
            "input_rows": len(prepared),
        })
        return normalized, meta, None
    except Exception as exc:
        return [], {}, f"{type(exc).__name__}: {exc}"


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CANONICAL_FIELDS})


def build(args: argparse.Namespace) -> dict[str, Any]:
    index_path = Path(args.index).expanduser().resolve()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    instrument = args.instrument.upper()

    selected_items = [
        item for item in index.get("files", [])
        if item.get("dataset_kind") == "UNDERLYING"
        and str(item.get("instrument_family", "")).upper() == instrument
        and item.get("date") not in (None, "", "UNKNOWN")
    ]
    selected_items.sort(key=lambda x: (str(x.get("date")), str(x.get("path"))))
    sessions = sorted({str(item["date"]) for item in selected_items})

    if len(sessions) < args.min_sessions:
        return {
            "status": "INSUFFICIENT_SESSION_COVERAGE",
            "instrument": instrument,
            "session_count": len(sessions),
            "min_sessions": args.min_sessions,
            "selected_files": len(selected_items),
            "certification": "NOT_CERTIFIED",
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
        }

    all_rows: list[dict[str, Any]] = []
    file_results: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for idx, item in enumerate(selected_items, 1):
        path = Path(str(item["path"]))
        rows, meta, error = normalize_parquet(path, args.max_rows_per_file)
        session = str(item["date"])
        status = "USABLE" if rows else "UNUSABLE"
        result = {
            "date": session,
            "path": str(path),
            "status": status,
            "normalized_rows": len(rows),
            "error": error,
            "meta": meta,
        }
        file_results.append(result)
        if not rows:
            failed.append(result)
        else:
            for row in rows:
                key = (str(row.get("raw_instrument", "")), str(row.get("timestamp", "")))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                all_rows.append(row)
        if args.progress_every and idx % args.progress_every == 0:
            print(f"processed={idx}/{len(selected_items)} usable={idx-len(failed)} failed={len(failed)} rows={len(all_rows)}", flush=True)

    out_dir = Path(args.cache_dir).expanduser().resolve()
    canonical_dir = out_dir / "canonical"
    canonical_path = canonical_dir / f"{instrument}.csv"
    manifest_path = out_dir / "cache_manifest.json"
    diagnostics_path = out_dir / "file_diagnostics.json"
    out_dir.mkdir(parents=True, exist_ok=True)

    if failed or not all_rows:
        manifest = {
            "schema_version": "tradebot-kite-replay-underlying-cache-v1",
            "status": "NORMALIZATION_FAILED" if failed else "CACHE_EMPTY",
            "instrument": instrument,
            "session_count": len(sessions),
            "selected_files": len(selected_items),
            "usable_files": len(selected_items) - len(failed),
            "failed_files": len(failed),
            "canonical_rows": 0,
            "canonical_outputs": {},
            "diagnostics": str(diagnostics_path),
            "certification": "NOT_CERTIFIED",
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
        }
        diagnostics_path.write_text(json.dumps(file_results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest

    all_rows.sort(key=lambda r: str(r.get("timestamp", "")))
    write_rows(canonical_path, all_rows)
    manifest = {
        "schema_version": "tradebot-kite-replay-underlying-cache-v1",
        "status": "CACHE_BUILT",
        "instrument": instrument,
        "session_count": len(sessions),
        "selected_files": len(selected_items),
        "usable_files": len(selected_items),
        "failed_files": 0,
        "canonical_rows": len(all_rows),
        "canonical_outputs": {
            instrument: {
                "path": str(canonical_path),
                "rows": len(all_rows),
                "sha256": sha256_file(canonical_path),
            }
        },
        "diagnostics": str(diagnostics_path),
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }
    diagnostics_path.write_text(json.dumps(file_results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", required=True)
    p.add_argument("--instrument", required=True, choices=["NIFTY", "BANKNIFTY", "SENSEX"])
    p.add_argument("--cache-dir", required=True)
    p.add_argument("--min-sessions", type=int, default=400)
    p.add_argument("--max-rows-per-file", type=int, default=100000)
    p.add_argument("--progress-every", type=int, default=25)
    return p


def main(argv: list[str] | None = None) -> int:
    result = build(parser().parse_args(argv))
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "CACHE_BUILT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
