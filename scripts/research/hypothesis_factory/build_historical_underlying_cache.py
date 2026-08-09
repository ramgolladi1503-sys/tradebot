#!/usr/bin/env python3
"""Build a canonical research cache from indexed historical underlying files only.

Consumes the output of index_historical_session_corpus.py and deliberately uses
only UNDERLYING files for the requested instrument family. This keeps options,
ticks, manifests, and unrelated families out of the hypothesis-underlying path.

Research-only. Never certifies edge or grants runtime/broker authority.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_PATH = HERE / "build_corpus_cache.py"
spec = importlib.util.spec_from_file_location("build_corpus_cache", CACHE_PATH)
cache = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = cache
spec.loader.exec_module(cache)


def load_index(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def select_files(index: dict, instrument: str) -> list[Path]:
    instrument = instrument.upper()
    selected = []
    for item in index.get("files", []):
        if item.get("dataset_kind") != "UNDERLYING":
            continue
        if str(item.get("instrument_family", "")).upper() != instrument:
            continue
        path = Path(str(item.get("path", "")))
        if path.exists() and path.is_file():
            selected.append(path)
    return sorted(set(selected))


def build(args: argparse.Namespace) -> dict:
    index_path = Path(args.index).expanduser().resolve()
    index = load_index(index_path)
    selected = select_files(index, args.instrument)
    min_sessions = int(args.min_sessions)
    sessions = sorted({
        str(item.get("date")) for item in index.get("files", [])
        if item.get("dataset_kind") == "UNDERLYING"
        and str(item.get("instrument_family", "")).upper() == args.instrument.upper()
        and item.get("date") not in (None, "", "UNKNOWN")
    })

    if len(sessions) < min_sessions:
        return {
            "status": "INSUFFICIENT_SESSION_COVERAGE",
            "instrument": args.instrument.upper(),
            "sessions": sessions,
            "session_count": len(sessions),
            "min_sessions": min_sessions,
            "selected_files": len(selected),
            "certification": "NOT_CERTIFIED",
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
        }

    if not selected:
        return {
            "status": "NO_USABLE_UNDERLYING_FILES",
            "instrument": args.instrument.upper(),
            "sessions": sessions,
            "session_count": len(sessions),
            "selected_files": 0,
            "certification": "NOT_CERTIFIED",
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
        }

    # Build from file paths directly; discover_roots supports file roots.
    cache_args = cache.parser().parse_args([])
    cache_args.corpus_root = [str(p) for p in selected]
    cache_args.pattern = []
    cache_args.instrument = [args.instrument.upper()]
    cache_args.cache_dir = args.cache_dir
    cache_args.max_files = max(len(selected), 1)
    cache_args.max_rows_per_file = args.max_rows_per_file
    cache_args.progress_every = args.progress_every
    cache_args.recheck_unusable = args.recheck_unusable
    cache_args.no_known_roots = True
    cache_args.no_gdrive_discovery = True

    result = cache.build(cache_args)
    return {
        "status": "CACHE_BUILT" if result.get("canonical_rows", 0) else "CACHE_EMPTY",
        "instrument": args.instrument.upper(),
        "sessions": sessions,
        "session_count": len(sessions),
        "min_sessions": min_sessions,
        "selected_files": len(selected),
        "cache_manifest": str(Path(args.cache_dir) / "cache_manifest.json"),
        "canonical_rows": result.get("canonical_rows", 0),
        "canonical_outputs": result.get("canonical_outputs", {}),
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", default="research/hypotheses/historical_corpus/historical_session_index.json")
    p.add_argument("--instrument", required=True, choices=["NIFTY", "BANKNIFTY", "SENSEX"])
    p.add_argument("--cache-dir", default="research/hypotheses/historical_corpus/cache")
    p.add_argument("--min-sessions", type=int, default=20)
    p.add_argument("--max-rows-per-file", type=int, default=100000)
    p.add_argument("--progress-every", type=int, default=25)
    p.add_argument("--recheck-unusable", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = build(args)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "CACHE_BUILT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
