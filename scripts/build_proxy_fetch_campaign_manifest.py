#!/usr/bin/env python3
"""Inventory shared Upstox V3 raw files and isolate one frozen proxy campaign."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

FILE_RE = re.compile(r"^(?P<symbol>.+)_(?P<from>\d{4}-\d{2}-\d{2})_(?P<to>\d{4}-\d{2}-\d{2})\.json\.gz$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_fetch_manifest(path: Path) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    rows = json.loads(path.read_text())
    lookup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("symbol", "")).upper(),
            str(row.get("from_date", "")),
            str(row.get("to_date", "")),
            str(row.get("stored_file_sha256", "")),
        )
        lookup[key] = row
    return lookup


def inspect_file(path: Path, ownership: dict[tuple[str, str, str, str], dict[str, Any]]) -> dict[str, Any]:
    match = FILE_RE.match(path.name)
    file_hash = sha256(path)
    filename_symbol = match.group("symbol").upper() if match else None
    filename_from = match.group("from") if match else None
    filename_to = match.group("to") if match else None
    owner = ownership.get((filename_symbol or "", filename_from or "", filename_to or "", file_hash))
    row: dict[str, Any] = {
        "stored_path": str(path),
        "sha256": file_hash,
        "filename_symbol": filename_symbol,
        "symbol": str(owner.get("symbol", "")).upper() if owner else None,
        "from_date": str(owner.get("from_date", "")) if owner else filename_from,
        "to_date": str(owner.get("to_date", "")) if owner else filename_to,
        "response_status": None,
        "candle_count": 0,
        "timestamp_min": None,
        "timestamp_max": None,
        "instrument_key": None,
        "candle_shape": None,
        "campaign_ownership": "unknown",
        "ownership_source": "upstox_v3_fetch_manifest" if owner else None,
        "reject_reasons": [],
    }
    if not match:
        row["reject_reasons"].append("filename_not_traceable")
    if owner is None:
        row["reject_reasons"].append("missing_authoritative_ownership")
    try:
        with gzip.open(path, "rt") as handle:
            payload = json.load(handle)
    except Exception as exc:  # noqa: BLE001 - manifest must preserve corrupt-file reason.
        row["reject_reasons"].append(f"read_error:{type(exc).__name__}")
        return row
    row["response_status"] = payload.get("status")
    data = payload.get("data") or {}
    row["instrument_key"] = (owner or {}).get("instrument_key") or payload.get("instrument_key") or data.get("instrument_key")
    candles = data.get("candles")
    if not isinstance(candles, list):
        row["reject_reasons"].append("missing_candles")
        return row
    row["candle_count"] = len(candles)
    shapes = sorted({len(c) for c in candles if isinstance(c, list)})
    row["candle_shape"] = shapes
    timestamps = []
    for candle in candles:
        if isinstance(candle, list) and len(candle) == 7:
            try:
                timestamps.append(pd.Timestamp(candle[0]))
            except Exception:
                pass
    if timestamps:
        row["timestamp_min"] = min(timestamps).isoformat()
        row["timestamp_max"] = max(timestamps).isoformat()
    return row


def classify(row: dict[str, Any], start: pd.Timestamp, end: pd.Timestamp) -> bool:
    reasons = row["reject_reasons"]
    if row["response_status"] != "success":
        reasons.append("non_success_payload")
    if row["candle_count"] <= 0:
        reasons.append("empty_payload")
    if row["candle_shape"] != [7]:
        reasons.append("non_seven_field_candle")
    if row["symbol"] in {"BANKNIFTY"}:
        reasons.append("non_nifty_campaign_symbol")
    if not row["timestamp_min"] or not row["timestamp_max"]:
        reasons.append("missing_timestamp_range")
    else:
        min_session = pd.Timestamp(row["timestamp_min"]).tz_convert("Asia/Kolkata").date()
        max_session = pd.Timestamp(row["timestamp_max"]).tz_convert("Asia/Kolkata").date()
        if min_session < start.date() or max_session > end.date():
            reasons.append("outside_frozen_campaign_window")
    row["campaign_ownership"] = "proxy_campaign_2024_2025_v1" if not reasons else "rejected"
    return not reasons


def build(raw_dir: Path, output_root: Path, start_date: str, end_date: str, fetch_manifest: Path) -> dict[str, Any]:
    manifests = output_root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    ownership = load_fetch_manifest(fetch_manifest)
    rows = [inspect_file(path, ownership) for path in sorted(raw_dir.glob("*.json.gz"))]
    accepted = [row for row in rows if classify(row, start, end)]
    rejected = [row for row in rows if row["reject_reasons"]]
    summary = {
        "raw_dir": str(raw_dir),
        "fetch_manifest": str(fetch_manifest),
        "fetch_manifest_sha256": sha256(fetch_manifest),
        "campaign_root": str(output_root),
        "start_date": start_date,
        "end_date": end_date,
        "raw_files_discovered": len(rows),
        "raw_files_accepted": len(accepted),
        "raw_files_rejected": len(rejected),
        "accepted_symbols": sorted({r["symbol"] for r in accepted if r["symbol"]}),
        "rejection_counts": pd.Series([reason for r in rejected for reason in r["reject_reasons"]]).value_counts().to_dict(),
        "research_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
    }
    (manifests / "accepted_raw_files.json").write_text(json.dumps(accepted, indent=2, sort_keys=True) + "\n")
    (manifests / "rejected_raw_files.json").write_text(json.dumps(rejected, indent=2, sort_keys=True) + "\n")
    (manifests / "campaign_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2025-08-29")
    parser.add_argument("--fetch-manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.raw_dir, args.output_root, args.start_date, args.end_date, args.fetch_manifest), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
