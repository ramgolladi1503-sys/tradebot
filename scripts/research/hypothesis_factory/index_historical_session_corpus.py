#!/usr/bin/env python3
"""Inventory a local/synced historical market-data corpus by trading session.

The expected corpus shape is permissive, and supports date folders such as
YYYYMMDD/underlying/*.parquet and YYYY-MM-DD/underlying/*.parquet. The indexer
never assumes that the presence of a date folder means an instrument is
available. It classifies every file from its path/name and records exact
per-session coverage.

Research-only. It does not screen hypotheses, certify edge, or grant runtime or
broker authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMPACT_DATE_RE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
HYPHEN_DATE_RE = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)")
SUPPORTED_EXTENSIONS = {".parquet", ".csv"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def infer_date(path: Path) -> str:
    for part in reversed(path.parts):
        hyphen = HYPHEN_DATE_RE.search(part)
        if hyphen:
            return f"{hyphen.group(1)}-{hyphen.group(2)}-{hyphen.group(3)}"
        compact = COMPACT_DATE_RE.search(part)
        if compact:
            raw = compact.group(1)
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return "UNKNOWN"


def infer_instrument_family(path: Path) -> str:
    text = str(path).upper().replace("_", " ")
    name = path.name.upper()
    if "BANKNIFTY" in name or "NIFTY BANK" in text or "NSE INDEX|NIFTY BANK" in text:
        return "BANKNIFTY"
    if "SENSEX" in name or "BSE INDEX|SENSEX" in text:
        return "SENSEX"
    if "NIFTY" in name or "NSE INDEX|NIFTY" in text:
        return "NIFTY"
    return "UNKNOWN"


def infer_dataset_kind(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    text = path.name.lower()
    if "underlying" in parts:
        return "UNDERLYING"
    if "options" in parts or "option" in parts or "options" in text:
        return "OPTIONS"
    if "ticks" in parts or "tick" in text:
        return "TICKS"
    return "UNKNOWN"


def discover_candidate_roots(explicit_roots: list[str]) -> list[Path]:
    candidates = [Path(x).expanduser() for x in explicit_roots]
    cloud = Path.home() / "Library" / "CloudStorage"
    if cloud.exists():
        for provider in cloud.glob("GoogleDrive-*"):
            try:
                candidates.extend(p for p in provider.rglob("tradebot_historical_data") if p.is_dir())
            except (OSError, PermissionError):
                continue
    seen: set[str] = set()
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key not in seen and resolved.exists() and resolved.is_dir():
            seen.add(key)
            roots.append(resolved)
    return sorted(roots)


def inventory(roots: list[Path], hash_files: bool = False) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    per_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    family_counts = Counter()
    kind_counts = Counter()

    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            item = {
                "path": str(path),
                "root": str(root),
                "date": infer_date(path),
                "instrument_family": infer_instrument_family(path),
                "dataset_kind": infer_dataset_kind(path),
                "extension": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "sha256": sha256_file(path) if hash_files else None,
            }
            files.append(item)
            per_session[item["date"]].append(item)
            family_counts[item["instrument_family"]] += 1
            kind_counts[item["dataset_kind"]] += 1

    sessions = []
    for date, entries in sorted(per_session.items()):
        families = sorted({e["instrument_family"] for e in entries if e["instrument_family"] != "UNKNOWN"})
        kinds = sorted({e["dataset_kind"] for e in entries if e["dataset_kind"] != "UNKNOWN"})
        sessions.append({
            "date": date,
            "files": len(entries),
            "families": families,
            "dataset_kinds": kinds,
            "underlying_families": sorted({
                e["instrument_family"] for e in entries
                if e["dataset_kind"] == "UNDERLYING" and e["instrument_family"] != "UNKNOWN"
            }),
        })

    usable_underlying_sessions = {
        family: sorted({
            item["date"] for item in files
            if item["dataset_kind"] == "UNDERLYING"
            and item["instrument_family"] == family
            and item["date"] != "UNKNOWN"
        })
        for family in ("NIFTY", "BANKNIFTY", "SENSEX")
    }

    return {
        "schema_version": "tradebot-historical-session-corpus-index-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "roots": [str(r) for r in roots],
        "local_bytes_available": bool(files),
        "files": files,
        "sessions": sessions,
        "summary": {
            "files": len(files),
            "sessions": len([s for s in sessions if s["date"] != "UNKNOWN"]),
            "family_file_counts": dict(family_counts),
            "dataset_kind_counts": dict(kind_counts),
            "underlying_session_counts": {k: len(v) for k, v in usable_underlying_sessions.items()},
            "underlying_sessions": usable_underlying_sessions,
        },
        "status": "READY_LOCAL_CORPUS" if files else "HISTORICAL_CORPUS_NOT_LOCAL",
        "next_action": "BUILD_CACHE" if files else "SYNC_OR_MOUNT_DRIVE_FOLDER_OR_PASS_EXPLICIT_ROOT",
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--historical-root", action="append", default=[], help="Explicit local/synced historical corpus root; repeatable")
    p.add_argument("--output", default="research/hypotheses/historical_corpus/historical_session_index.json")
    p.add_argument("--hash-files", action="store_true")
    args = p.parse_args(argv)

    roots = discover_candidate_roots(args.historical_root)
    result = inventory(roots, hash_files=args.hash_files)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "roots": result["roots"],
        "files": result["summary"]["files"],
        "sessions": result["summary"]["sessions"],
        "underlying_session_counts": result["summary"]["underlying_session_counts"],
        "next_action": result["next_action"],
        "runtime_authority": "NONE",
    }, indent=2))
    return 0 if result["summary"]["files"] else 2


if __name__ == "__main__":
    raise SystemExit(main())