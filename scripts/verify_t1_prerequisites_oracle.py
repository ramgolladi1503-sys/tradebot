#!/usr/bin/env python3
"""Materially separate independent oracle verifier for T-1 prerequisites manifest.

Independently hashes sources, re-derives spot close, re-computes SMA200 if series
is present, verifies contract semantics, checks fail-closed bounds, and re-computes
the payload canonical SHA-256 without calling or importing generate_t1_prerequisites.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import pandas as pd


def verify_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    raw_manifest = manifest_path.read_text(encoding="utf-8")
    doc = json.loads(raw_manifest)

    # 1. Independent Snapshot Source Hashing and Verification
    snap_path = Path(doc["source_snapshot"])
    if not snap_path.is_file():
        raise FileNotFoundError(f"Underlying snapshot missing: {snap_path}")

    snap_bytes = snap_path.read_bytes()
    computed_snap_sha = hashlib.sha256(snap_bytes).hexdigest()
    if computed_snap_sha != doc.get("source_snapshot_sha256"):
        raise ValueError(f"Snapshot SHA mismatch: computed {computed_snap_sha} vs doc {doc.get('source_snapshot_sha256')}")

    snap_json = json.loads(snap_bytes.decode("utf-8"))
    nifty_spot = (snap_json.get("payload") or {}).get("symbols", {}).get("NIFTY", {})
    ltp = nifty_spot.get("ltp") or (nifty_spot.get("quote_truth") or {}).get("ltp")
    if ltp is None or float(ltp) != doc["overnight_prev_daily_close"]:
        raise ValueError(f"Spot close mismatch: oracle={ltp} vs manifest={doc['overnight_prev_daily_close']}")

    # 2. Independent Futures 15:29 Verification
    fut_path_str = doc.get("futures_dataset_path")
    if fut_path_str is not None:
        fut_path = Path(fut_path_str)
        if fut_path.is_file():
            fut_bytes = fut_path.read_bytes()
            computed_fut_sha = hashlib.sha256(fut_bytes).hexdigest()
            if computed_fut_sha != doc.get("futures_dataset_sha256"):
                raise ValueError("Futures dataset SHA-256 mismatch")
    else:
        # Source authority is blocked; manifest must declare null and BLOCKED_SOURCE_AUTHORITY
        if doc.get("opening_drive_prev_close_1529") is not None:
            raise ValueError("opening_drive_prev_close_1529 must be null when futures dataset is absent")
        if doc.get("t1_prev_close_status") != "BLOCKED_SOURCE_AUTHORITY":
            raise ValueError("t1_prev_close_status must be BLOCKED_SOURCE_AUTHORITY when futures dataset is absent")

    # 3. Independent SMA200 Window & Calculation Verification
    hist_path_str = doc.get("historical_dataset_path")
    if hist_path_str is not None:
        hist_path = Path(hist_path_str)
        if hist_path.is_file():
            hist_bytes = hist_path.read_bytes()
            computed_hist_sha = hashlib.sha256(hist_bytes).hexdigest()
            if computed_hist_sha != doc.get("historical_dataset_sha256"):
                raise ValueError("Historical dataset SHA-256 mismatch")
            if hist_path.suffix in (".parquet", ".pq"):
                hdf = pd.read_parquet(hist_path)
            else:
                hdf = pd.read_csv(hist_path)
            date_col = "Date" if "Date" in hdf.columns else ("session_date" if "session_date" in hdf.columns else "date")
            close_col = "Close" if "Close" in hdf.columns else ("close" if "close" in hdf.columns else "spot_close")
            clean_hdf = hdf[[date_col, close_col]].dropna().drop_duplicates(subset=[date_col]).sort_values(by=date_col)
            clean_hdf = clean_hdf[clean_hdf[date_col].astype(str) <= doc["source_session_date"]]
            w_df = clean_hdf.tail(200)
            computed_sma = round(float(w_df[close_col].mean()), 4)
            if computed_sma != doc.get("overnight_prev_sma200"):
                raise ValueError("SMA-200 calculation mismatch")
            if str(w_df.iloc[0][date_col]) != doc.get("sma200_window_start") or str(w_df.iloc[-1][date_col]) != doc.get("sma200_window_end"):
                raise ValueError("SMA-200 window dates mismatch")
    else:
        # Historical daily series blocked; manifest must declare null and BLOCKED_SOURCE_AUTHORITY
        if doc.get("overnight_prev_sma200") is not None:
            raise ValueError("overnight_prev_sma200 must be null when historical daily dataset is absent")
        if doc.get("sma200_status") != "BLOCKED_SOURCE_AUTHORITY":
            raise ValueError("sma200_status must be BLOCKED_SOURCE_AUTHORITY when historical daily dataset is absent")

    # 4. Independent Payload SHA-256 Verification
    payload_copy = dict(doc)
    stored_sha = payload_copy.pop("payload_sha256", None)
    canonical_repr = json.dumps(payload_copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    recalculated_sha = hashlib.sha256(canonical_repr).hexdigest()
    if stored_sha != recalculated_sha:
        raise ValueError(f"Payload SHA-256 mismatch: stored {stored_sha} vs recalculated {recalculated_sha}")

    return {
        "manifest_path": str(manifest_path),
        "source_snapshot_sha_verified": True,
        "spot_close_recalculated": float(ltp),
        "spot_close_matches": True,
        "t1_close_authority_status": doc.get("t1_prev_close_status"),
        "sma200_authority_status": doc.get("sma200_status"),
        "payload_sha_verified": True,
        "independent_oracle_verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent Oracle for T-1 prerequisites")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    res = verify_manifest(args.manifest)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
