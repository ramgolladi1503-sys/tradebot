#!/usr/bin/env python3
"""Reaggregate canonical corpus rows by logical capture stream before reconciliation.

Why this exists:
- raw runtime data can be split into many tiny parquet shards;
- the same physical capture can be mirrored under bridge/authority paths;
- treating every file as an independent source creates false same-minute OHLC conflicts.

This tool canonicalizes mirror paths into a logical stream id and then combines all
rows for the same instrument/raw_instrument/date/logical_stream/minute into one
OHLC observation. It does not choose between genuinely different logical streams.

Research-only. Never certifies edge or grants runtime/broker authority.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

FIELDS = [
    "timestamp", "instrument", "raw_instrument", "open", "high", "low", "close",
    "volume", "vwap", "bid", "ask", "is_fallback", "source_path", "logical_stream",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDS})


def logical_stream_id(source_path: str) -> str:
    text = str(source_path or "").replace("\\", "/")
    # authority/bridge are mirrors of the same captured shard hierarchy.
    text = text.replace("/.mros-agent-bridge/authority/", "/.mros-agent-bridge/MIRROR/")
    text = text.replace("/.mros-agent-bridge/bridge/", "/.mros-agent-bridge/MIRROR/")
    # Shard epoch suffix is a file-part identifier, not a distinct market-data source.
    text = re.sub(r"/ticks_\d+\.parquet$", "/ticks_SHARD.parquet", text)
    text = re.sub(r"/[^/]*ticks[^/]*_\d+\.parquet$", "/ticks_SHARD.parquet", text)
    return text


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "fallback", "recovered_fallback"}


def f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def reaggregate(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    fallback_rows = 0
    mirror_rows = 0
    for row in rows:
        if truthy(row.get("is_fallback")):
            fallback_rows += 1
            continue
        source = str(row.get("source_path", ""))
        stream = logical_stream_id(source)
        if "/.mros-agent-bridge/MIRROR/" in stream:
            mirror_rows += 1
        key = (
            str(row.get("instrument", "")).upper(),
            str(row.get("raw_instrument", "")),
            str(row.get("timestamp", "")),
            stream,
        )
        groups[key].append(row)

    output: list[dict[str, Any]] = []
    max_rows_per_stream_minute = 0
    for (instrument, raw_instrument, timestamp, stream), group in sorted(groups.items()):
        max_rows_per_stream_minute = max(max_rows_per_stream_minute, len(group))
        # Canonical input rows are already minute observations. Multiple rows from shard
        # files in one logical stream are combined conservatively using OHLC envelope and
        # deterministic close from lexical source order.
        ordered = sorted(group, key=lambda r: str(r.get("source_path", "")))
        open_ = f(ordered[0].get("open"))
        close = f(ordered[-1].get("close"))
        high = max(f(r.get("high")) for r in ordered)
        low = min(f(r.get("low")) for r in ordered)
        volume = sum(max(0.0, f(r.get("volume"))) for r in ordered)
        vwap_vals = [f(r.get("vwap")) for r in ordered if f(r.get("vwap")) > 0]
        bid_vals = [f(r.get("bid")) for r in ordered if f(r.get("bid")) > 0]
        ask_vals = [f(r.get("ask")) for r in ordered if f(r.get("ask")) > 0]
        output.append({
            "timestamp": timestamp,
            "instrument": instrument,
            "raw_instrument": raw_instrument,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "vwap": (sum(vwap_vals) / len(vwap_vals)) if vwap_vals else close,
            "bid": bid_vals[-1] if bid_vals else 0.0,
            "ask": ask_vals[-1] if ask_vals else 0.0,
            "is_fallback": "false",
            "source_path": " || ".join(sorted({str(r.get("source_path", "")) for r in group})),
            "logical_stream": stream,
        })

    summary = {
        "input_rows": len(rows),
        "fallback_rows_excluded": fallback_rows,
        "logical_stream_minute_groups": len(groups),
        "output_rows": len(output),
        "rows_collapsed": len(rows) - fallback_rows - len(output),
        "mirror_rows_seen": mirror_rows,
        "max_rows_per_logical_stream_minute": max_rows_per_stream_minute,
        "logical_streams": len({row["logical_stream"] for row in output}),
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "certification": "NOT_CERTIFIED",
    }
    return output, summary


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)

    src = Path(args.input)
    out = Path(args.output)
    manifest = Path(args.manifest)
    rows, summary = reaggregate(read_rows(src))
    write_rows(out, rows)
    payload = {
        "schema_version": "tradebot-logical-stream-reaggregation-v1",
        "source_path": str(src),
        "source_sha256": sha256_file(src),
        "output_path": str(out),
        "output_sha256": sha256_file(out),
        "summary": summary,
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "certification": "NOT_CERTIFIED",
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
