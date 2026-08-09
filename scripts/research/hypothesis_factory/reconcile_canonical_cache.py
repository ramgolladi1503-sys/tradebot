#!/usr/bin/env python3
"""Reconcile canonical corpus rows across multiple source files.

The canonical cache preserves broad family labels (NIFTY/BANKNIFTY) plus
`raw_instrument` contract identity. Reconciliation therefore operates on
instrument family + raw instrument + timestamp:

- collapses identical OHLC observations across sources for the same contract;
- excludes same-contract/timestamp OHLC conflicts (fail closed);
- never treats different option contracts at the same minute as conflicts;
- excludes fallback rows;
- preserves contributing source paths in the output provenance field;
- writes a separate reconciled dataset; the original cache is untouched.

Research-only. Never certifies edge or grants runtime/broker authority.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIELDS = ["timestamp", "instrument", "raw_instrument", "open", "high", "low", "close", "volume", "vwap", "bid", "ask", "is_fallback", "source_path"]


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "fallback", "recovered_fallback"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDS})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def market_signature(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(row.get(k, "")) for k in ("open", "high", "low", "close"))


def contract_identity(row: dict[str, Any]) -> str:
    raw = str(row.get("raw_instrument", "")).strip()
    return raw if raw else "MISSING_RAW_INSTRUMENT"


def reconcile_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    fallback_rows = 0
    missing_raw_identity_rows = 0
    for row in rows:
        if truthy(row.get("is_fallback")):
            fallback_rows += 1
            continue
        raw_id = contract_identity(row)
        if raw_id == "MISSING_RAW_INSTRUMENT":
            missing_raw_identity_rows += 1
        key = (
            str(row.get("instrument", "")).upper(),
            raw_id,
            str(row.get("timestamp", "")),
        )
        groups[key].append(row)

    reconciled: list[dict[str, Any]] = []
    duplicate_groups = 0
    duplicate_rows_removed = 0
    conflict_groups = 0
    conflict_rows_excluded = 0
    source_overlap_groups = 0
    max_sources_for_observation = 0
    conflicts: list[dict[str, Any]] = []

    for (instrument, raw_instrument, timestamp), group in sorted(groups.items()):
        signatures: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
        for row in group:
            signatures[market_signature(row)].append(row)
        sources = sorted({str(row.get("source_path", "")) for row in group if row.get("source_path")})
        max_sources_for_observation = max(max_sources_for_observation, len(sources))
        if len(sources) > 1:
            source_overlap_groups += 1

        if len(signatures) > 1:
            conflict_groups += 1
            conflict_rows_excluded += len(group)
            if len(conflicts) < 100:
                conflicts.append({
                    "instrument": instrument,
                    "raw_instrument": raw_instrument,
                    "timestamp": timestamp,
                    "rows": len(group),
                    "sources": sources,
                    "ohlc_signatures": [list(sig) for sig in signatures.keys()],
                })
            continue

        representative = dict(group[0])
        representative["raw_instrument"] = raw_instrument
        if len(group) > 1:
            duplicate_groups += 1
            duplicate_rows_removed += len(group) - 1
        representative["source_path"] = " || ".join(sources)
        representative["is_fallback"] = "false"
        reconciled.append(representative)

    reconciled.sort(key=lambda r: (str(r.get("instrument", "")), str(r.get("raw_instrument", "")), str(r.get("timestamp", ""))))
    summary = {
        "input_rows": len(rows),
        "fallback_rows_excluded": fallback_rows,
        "missing_raw_identity_rows": missing_raw_identity_rows,
        "unique_contract_timestamps": len(groups),
        "reconciled_rows": len(reconciled),
        "duplicate_groups_collapsed": duplicate_groups,
        "duplicate_rows_removed": duplicate_rows_removed,
        "source_overlap_groups": source_overlap_groups,
        "max_sources_for_observation": max_sources_for_observation,
        "conflict_groups_excluded": conflict_groups,
        "conflict_rows_excluded": conflict_rows_excluded,
        "conflict_examples": conflicts,
    }
    return reconciled, summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache-dir", default="research/hypotheses/corpus_cache")
    p.add_argument("--instrument", action="append", default=[])
    p.add_argument("--output-dir", default="")
    args = p.parse_args(argv)

    cache_dir = Path(args.cache_dir).expanduser().resolve()
    manifest_path = cache_dir / "cache_manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"cache manifest missing: {manifest_path}")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("schema_version") != "tradebot-canonical-corpus-cache-v2":
        raise SystemExit("canonical cache schema v2 required; rebuild cache before reconciliation")
    instruments = [x.strip().upper() for x in args.instrument if x.strip()] or sorted(source_manifest.get("canonical_outputs", {}).keys())
    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else cache_dir / "reconciled_v2"

    outputs: dict[str, Any] = {}
    total_conflicts = 0
    total_removed = 0
    for instrument in instruments:
        info = source_manifest.get("canonical_outputs", {}).get(instrument)
        if not info:
            continue
        src = Path(info["path"])
        rows = read_rows(src)
        reconciled, summary = reconcile_rows(rows)
        out = out_dir / f"{instrument}.csv"
        write_rows(out, reconciled)
        total_conflicts += summary["conflict_groups_excluded"]
        total_removed += summary["duplicate_rows_removed"]
        outputs[instrument] = {
            "source_path": str(src),
            "source_sha256": sha256_file(src),
            "path": str(out),
            "sha256": sha256_file(out),
            "rows": len(reconciled),
            "summary": summary,
        }

    result = {
        "schema_version": "tradebot-reconciled-canonical-cache-v2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_cache_manifest": str(manifest_path),
        "source_cache_manifest_sha256": sha256_file(manifest_path),
        "outputs": outputs,
        "total_duplicate_rows_removed": total_removed,
        "total_conflict_groups_excluded": total_conflicts,
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }
    out_manifest = out_dir / "reconciled_manifest.json"
    write_json(out_manifest, result)
    print(json.dumps({
        "outputs": {k: {"rows": v["rows"], "sha256": v["sha256"], "summary": {kk: vv for kk, vv in v["summary"].items() if kk != "conflict_examples"}} for k, v in outputs.items()},
        "total_duplicate_rows_removed": total_removed,
        "total_conflict_groups_excluded": total_conflicts,
        "runtime_authority": "NONE",
    }, indent=2))
    return 0 if outputs else 2


if __name__ == "__main__":
    raise SystemExit(main())
