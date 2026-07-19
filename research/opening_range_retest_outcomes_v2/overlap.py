from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from research.opening_range_retest_outcomes_v2.contract import evidence_fields, safety_fields
from research.opening_range_retest_outcomes_v2.contract import canonical_json_bytes, sha256_bytes


def build_overlap(ledger: dict[str, Any]) -> dict[str, Any]:
    by_horizon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in ledger["records"]:
        entry = record.get("legal_entry") or {}
        if entry.get("status") != "LEGAL_ENTRY_FOUND":
            continue
        for horizon, payload in record.get("horizons", {}).items():
            if payload.get("status") != "MEASURED":
                continue
            by_horizon[horizon].append(
                {
                    "candidate_id": record["candidate_id"],
                    "symbol": record["candidate_core"]["symbol"],
                    "direction": record["candidate_core"]["direction"],
                    "session_date": record["candidate_core"]["session_date"],
                    "start": entry["start"],
                    "end": payload["terminal_end"],
                }
            )
    result = {}
    for horizon, intervals in by_horizon.items():
        events = []
        pairs = 0
        max_open = 0
        open_items: list[dict[str, Any]] = []
        for item in sorted(intervals, key=lambda x: (x["start"], x["end"], x["candidate_id"])):
            start = pd.Timestamp(item["start"])
            open_items = [active for active in open_items if pd.Timestamp(active["end"]) > start]
            pairs += len(open_items)
            open_items.append(item)
            max_open = max(max_open, len(open_items))
            events.append(item)
        result[horizon] = {
            "interval_count": len(intervals),
            "complete_interval_count": len(events),
            "complete_interval_set_hash": sha256_bytes(canonical_json_bytes(events)),
            "overlapping_pair_count": pairs,
            "max_simultaneous_candidates": max_open,
            "symbol_counts": dict(Counter(item["symbol"] for item in intervals)),
            "symbol_direction_counts": dict(Counter(f"{item['symbol']}:{item['direction']}" for item in intervals)),
            "session_cluster_counts": dict(Counter(item["session_date"] for item in intervals).most_common(25)),
            "sample_truncated": len(events) > 500,
            "sample_count": min(len(events), 500),
            "overlap_evidence_intervals": events[:500],
        }
    return {
        "schema_version": 1,
        **evidence_fields(
            mode="ORB_OUTCOME_OVERLAP_V2",
            decision="ORB_OUTCOME_OVERLAP_REPORTED",
            reason="reported half-open interval overlap diagnostics without filtering descriptive candidates",
            source="opening_range_retest_outcome_ledger_v2.json",
        ),
        "horizons": result,
        **safety_fields(),
    }
