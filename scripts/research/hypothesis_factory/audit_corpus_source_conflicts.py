#!/usr/bin/env python3
"""Audit cross-source conflicts in canonical research cache without choosing a winner.

Research-only. This script does not certify data or strategy edge. It profiles
which source files contribute observations, how much they overlap, and where
same-timestamp OHLC values conflict so later source-cohort selection can be
explicit and evidence-backed rather than silently mixed.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def ohlc_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(row.get(k, "")) for k in ("open", "high", "low", "close"))


def analyze(path: Path) -> dict[str, Any]:
    rows = read_rows(path)
    by_ts: dict[str, list[dict[str, str]]] = defaultdict(list)
    source_rows = Counter()
    source_dates: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        ts = str(row.get("timestamp", ""))
        source = str(row.get("source_path", "UNKNOWN"))
        by_ts[ts].append(row)
        source_rows[source] += 1
        if len(ts) >= 10:
            source_dates[source].add(ts[:10])

    conflict_groups = 0
    agreeing_overlap_groups = 0
    exclusive_groups = 0
    source_conflicts = Counter()
    source_agreements = Counter()
    conflict_examples: list[dict[str, Any]] = []

    for ts, group in by_ts.items():
        sources = sorted({str(r.get("source_path", "UNKNOWN")) for r in group})
        variants = defaultdict(list)
        for row in group:
            variants[ohlc_key(row)].append(str(row.get("source_path", "UNKNOWN")))

        if len(sources) == 1:
            exclusive_groups += 1
            continue

        pairs = []
        for i, left in enumerate(sources):
            for right in sources[i + 1:]:
                pairs.append((left, right))

        if len(variants) == 1:
            agreeing_overlap_groups += 1
            for pair in pairs:
                source_agreements[pair] += 1
        else:
            conflict_groups += 1
            for pair in pairs:
                source_conflicts[pair] += 1
            if len(conflict_examples) < 25:
                conflict_examples.append({
                    "timestamp": ts,
                    "sources": sources,
                    "variants": [
                        {"ohlc": list(key), "sources": sorted(vals)}
                        for key, vals in variants.items()
                    ],
                })

    source_stats = []
    for source, count in source_rows.most_common():
        conflict_touch = sum(v for pair, v in source_conflicts.items() if source in pair)
        agreement_touch = sum(v for pair, v in source_agreements.items() if source in pair)
        source_stats.append({
            "source_path": source,
            "rows": count,
            "dates": len(source_dates[source]),
            "agreement_pair_events": agreement_touch,
            "conflict_pair_events": conflict_touch,
        })

    pair_stats = []
    all_pairs = set(source_conflicts) | set(source_agreements)
    for pair in sorted(all_pairs):
        agree = source_agreements[pair]
        conflict = source_conflicts[pair]
        total = agree + conflict
        pair_stats.append({
            "source_a": pair[0],
            "source_b": pair[1],
            "agreeing_groups": agree,
            "conflicting_groups": conflict,
            "agreement_rate": round(agree / total, 6) if total else 0.0,
        })
    pair_stats.sort(key=lambda x: (x["conflicting_groups"], -x["agreement_rate"]), reverse=True)

    return {
        "schema_version": "tradebot-corpus-source-conflict-audit-v1",
        "input_path": str(path),
        "input_rows": len(rows),
        "unique_timestamps": len(by_ts),
        "exclusive_timestamp_groups": exclusive_groups,
        "agreeing_overlap_groups": agreeing_overlap_groups,
        "conflict_groups": conflict_groups,
        "sources": source_stats,
        "source_pairs": pair_stats,
        "conflict_examples": conflict_examples,
        "authority": {
            "data_source_selection": "NOT_DECIDED",
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
            "certification": "NOT_CERTIFIED",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    result = analyze(Path(args.input))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "input_rows": result["input_rows"],
        "unique_timestamps": result["unique_timestamps"],
        "sources": len(result["sources"]),
        "conflict_groups": result["conflict_groups"],
        "agreeing_overlap_groups": result["agreeing_overlap_groups"],
        "runtime_authority": "NONE",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
