#!/usr/bin/env python3
"""Audit canonical v2 coverage at contract+minute granularity.

Research-only. This audit does not choose a source, merge conflicting bars,
certify data, or enable runtime/broker authority. It profiles whether multiple
source files contribute the same contract-minute and whether the resulting OHLC
bars agree, so partial/overlapping capture artifacts can be diagnosed before
hypothesis screening.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def sig(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return tuple(str(row.get(k, "")) for k in ("open", "high", "low", "close"))


def analyze(path: Path) -> dict[str, Any]:
    rows = read_rows(path)
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    contract_rows = Counter()
    contract_dates: dict[str, set[str]] = defaultdict(set)
    source_rows = Counter()
    source_dates: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        fam = str(row.get("instrument", "")).upper()
        raw = str(row.get("raw_instrument", "")).strip() or "MISSING_RAW_INSTRUMENT"
        ts = str(row.get("timestamp", ""))
        src = str(row.get("source_path", "UNKNOWN"))
        groups[(fam, raw, ts)].append(row)
        contract_rows[raw] += 1
        source_rows[src] += 1
        if len(ts) >= 10:
            contract_dates[raw].add(ts[:10])
            source_dates[src].add(ts[:10])

    conflict_groups = 0
    agreeing_overlap_groups = 0
    single_source_groups = 0
    overlap_source_counts = Counter()
    conflict_by_contract = Counter()
    overlap_by_contract = Counter()
    conflict_by_source = Counter()
    examples: list[dict[str, Any]] = []

    for (fam, raw, ts), group in groups.items():
        sources = sorted({str(r.get("source_path", "UNKNOWN")) for r in group})
        variants = {sig(r) for r in group}
        overlap_source_counts[len(sources)] += 1
        if len(sources) <= 1:
            single_source_groups += 1
            continue
        overlap_by_contract[raw] += 1
        if len(variants) == 1:
            agreeing_overlap_groups += 1
        else:
            conflict_groups += 1
            conflict_by_contract[raw] += 1
            for src in sources:
                conflict_by_source[src] += 1
            if len(examples) < 50:
                examples.append({
                    "instrument": fam,
                    "raw_instrument": raw,
                    "timestamp": ts,
                    "sources": sources,
                    "rows": len(group),
                    "ohlc_variants": [list(v) for v in sorted(variants)],
                })

    contracts = []
    for raw, count in contract_rows.most_common():
        overlaps = overlap_by_contract[raw]
        conflicts = conflict_by_contract[raw]
        contracts.append({
            "raw_instrument": raw,
            "rows": count,
            "dates": len(contract_dates[raw]),
            "overlap_groups": overlaps,
            "conflict_groups": conflicts,
            "conflict_rate_within_overlap": round(conflicts / overlaps, 6) if overlaps else 0.0,
        })

    sources = []
    for src, count in source_rows.most_common():
        sources.append({
            "source_path": src,
            "rows": count,
            "dates": len(source_dates[src]),
            "conflict_groups_touched": conflict_by_source[src],
        })

    return {
        "schema_version": "tradebot-contract-minute-coverage-audit-v1",
        "input_path": str(path),
        "input_rows": len(rows),
        "unique_contract_minutes": len(groups),
        "unique_contracts": len(contract_rows),
        "unique_sources": len(source_rows),
        "single_source_groups": single_source_groups,
        "agreeing_overlap_groups": agreeing_overlap_groups,
        "conflict_groups": conflict_groups,
        "overlap_source_count_distribution": {str(k): v for k, v in sorted(overlap_source_counts.items())},
        "contracts": contracts,
        "sources": sources,
        "conflict_examples": examples,
        "interpretation": {
            "source_selection": "NOT_DECIDED",
            "cross_source_ohlc_merge": "FORBIDDEN",
            "screening_allowed": False,
            "runtime_authority": "NONE",
            "broker_actions_allowed": False,
            "certification": "NOT_CERTIFIED",
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    result = analyze(Path(args.input))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "input_rows": result["input_rows"],
        "unique_contract_minutes": result["unique_contract_minutes"],
        "unique_contracts": result["unique_contracts"],
        "unique_sources": result["unique_sources"],
        "single_source_groups": result["single_source_groups"],
        "agreeing_overlap_groups": result["agreeing_overlap_groups"],
        "conflict_groups": result["conflict_groups"],
        "runtime_authority": "NONE",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
