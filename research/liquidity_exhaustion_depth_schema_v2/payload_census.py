from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

import pandas as pd

from .schema_probe import bounded_preview, normalize_depth_value, shape_signature


def census_depth_series(series: pd.Series) -> dict[str, Any]:
    row_count = int(len(series))
    null_rows = 0
    mapping_rows = 0
    malformed_rows = 0
    rows_with_nonempty_bids = 0
    rows_with_nonempty_asks = 0
    rows_with_both_sides = 0
    total_bid_entries = 0
    total_ask_entries = 0
    bid_entry_signatures: Counter[str] = Counter()
    ask_entry_signatures: Counter[str] = Counter()
    nonempty_examples: list[dict[str, Any]] = []

    for raw in series:
        value = normalize_depth_value(raw)
        if value is None:
            null_rows += 1
            continue
        if not isinstance(value, Mapping):
            malformed_rows += 1
            continue
        mapping_rows += 1
        bids = value.get("bids")
        asks = value.get("asks")
        if not isinstance(bids, list) or not isinstance(asks, list):
            malformed_rows += 1
            continue

        bid_count = len(bids)
        ask_count = len(asks)
        total_bid_entries += bid_count
        total_ask_entries += ask_count
        if bid_count:
            rows_with_nonempty_bids += 1
            for entry in bids:
                bid_entry_signatures[shape_signature(entry)] += 1
        if ask_count:
            rows_with_nonempty_asks += 1
            for entry in asks:
                ask_entry_signatures[shape_signature(entry)] += 1
        if bid_count and ask_count:
            rows_with_both_sides += 1
        if (bid_count or ask_count) and len(nonempty_examples) < 5:
            nonempty_examples.append(bounded_preview(value))

    return {
        "row_count": row_count,
        "null_rows": null_rows,
        "mapping_rows": mapping_rows,
        "malformed_rows": malformed_rows,
        "rows_with_nonempty_bids": rows_with_nonempty_bids,
        "rows_with_nonempty_asks": rows_with_nonempty_asks,
        "rows_with_both_sides": rows_with_both_sides,
        "total_bid_entries": total_bid_entries,
        "total_ask_entries": total_ask_entries,
        "bid_entry_signature_counts": dict(sorted(bid_entry_signatures.items())),
        "ask_entry_signature_counts": dict(sorted(ask_entry_signatures.items())),
        "nonempty_examples": nonempty_examples,
        "all_depth_sequences_empty": (
            mapping_rows > 0
            and malformed_rows == 0
            and total_bid_entries == 0
            and total_ask_entries == 0
        ),
    }
