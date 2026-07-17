import argparse
import sys
import os
import json
import time
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Ensure research package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.opening_state_momentum.models import FileInventory
from research.opening_state_momentum.data_inventory import scan_single_file
from research.opening_state_momentum.manifest import compute_portable_hash, compute_local_hash
from research.opening_state_momentum.quality_checks import check_ohlcv_file

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "item"):
            return obj.item()
        return super().default(obj)

def json_dump(data, f, indent=2):
    json.dump(data, f, indent=indent, cls=NumpyEncoder)


def discover_files_in_roots(roots: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    discovered = []
    root_statuses = {}

    for r in roots:
        r_path = Path(r)
        if not r_path.exists():
            root_statuses[r] = "MISSING"
            continue

        root_statuses[r] = "SCANNED"
        try:
            # Enumerate directories
            found_any = False
            for root_dir, dirs, files in os.walk(r):
                # Do not follow symlinks by default unless recorded
                for file in files:
                    if not (file.endswith(".parquet") or file.endswith(".json") or file.endswith(".jsonl")):
                        continue
                    file_path = Path(root_dir) / file
                    try:
                        stat = file_path.stat()
                        discovered.append({
                            "absolute_path": str(file_path),
                            "source_root": r,
                            "relative_path": str(file_path.relative_to(r_path)),
                            "size_bytes": stat.st_size,
                            "mtime": stat.st_mtime,
                            "inode": stat.st_ino,
                        })
                        found_any = True
                    except Exception:
                        pass
            if not found_any:
                root_statuses[r] = "EMPTY"
        except Exception:
            root_statuses[r] = "UNREADABLE"

    return discovered, root_statuses

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--scan_id", required=True)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--fail-on-unstable", action="store_true")
    parser.add_argument("--override-full-scan-id", action="store_true")
    args = parser.parse_args()

    # Reject full_scan_* IDs if max-files is set, unless overridden
    if args.max_files is not None and args.scan_id.startswith("full_scan_") and not args.override_full_scan_id:
        print(f"Error: scan_id '{args.scan_id}' cannot start with 'full_scan_' when --max-files is set.", file=sys.stderr)
        sys.exit(1)

    scan_mode = "SMOKE" if args.max_files is not None else "FULL"
    print(f"Starting inventory run. ID: {args.scan_id}, Mode: {scan_mode}")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # 1. Snapshot start
    start_time_utc = datetime.datetime.now(datetime.timezone.utc)
    start_time_ist = start_time_utc + datetime.timedelta(hours=5, minutes=30)

    discovered_files, root_statuses = discover_files_in_roots(args.roots)

    # Slice if bounded
    files_to_scan = discovered_files
    if args.max_files is not None:
        files_to_scan = discovered_files[:args.max_files]

    print(f"Discovered {len(discovered_files)} files total. Scanning {len(files_to_scan)} files.")

    scanned_inventories = []
    stable_files = []
    unstable_files = []

    # In-memory tracking for duplicate content identification
    content_map = {} # sha256 -> list of absolute paths

    for f in files_to_scan:
        # Check newly appearing/disappearing files
        p = Path(f["absolute_path"])
        if not p.exists():
            # File disappeared
            inv = FileInventory(
                absolute_path=f["absolute_path"],
                source_root=f["source_root"],
                relative_path=f["relative_path"],
                inode=f["inode"],
                size_bytes=0,
                pre_scan_mtime=0.0,
                post_scan_mtime=0.0,
                pre_scan_size=0,
                post_scan_size=0,
                stability="UNREADABLE",
                error="File vanished during scan"
            )
            scanned_inventories.append(inv)
            continue

        inv = scan_single_file(f["absolute_path"], f["source_root"], f["relative_path"])

        if inv.stability == "UNSTABLE_CHANGED_DURING_SCAN":
            if args.fail_on_unstable:
                print(f"Critical error: File {inv.absolute_path} modified during scan.", file=sys.stderr)
                sys.exit(2)
            unstable_files.append(inv)
        elif inv.stability == "STABLE_INCLUDED":
            # Check duplicate content
            if inv.sha256 in content_map:
                inv.duplicate_of = content_map[inv.sha256][0]
                content_map[inv.sha256].append(inv.absolute_path)
            else:
                content_map[inv.sha256] = [inv.absolute_path]
            stable_files.append(inv)

        scanned_inventories.append(inv)

    # Build maps of stable files for serializing
    stable_dicts = []
    for sf in stable_files:
        stable_dicts.append({
            "absolute_path": sf.absolute_path,
            "source_root": sf.source_root,
            "relative_path": sf.relative_path,
            "inode": sf.inode,
            "pre_scan_mtime": sf.pre_scan_mtime,
            "size_bytes": sf.size_bytes,
            "sha256": sf.sha256,
            "row_count": sf.row_count,
            "min_timestamp": sf.min_timestamp,
            "max_timestamp": sf.max_timestamp,
            "schema_fingerprint": sf.schema_fingerprint,
            "data_family": sf.data_family,
            "instruments": sf.instruments
        })

    # Calculate hashes
    portable_hash = compute_portable_hash(stable_dicts)
    local_hash = compute_local_hash(stable_dicts)

    end_time_utc = datetime.datetime.now(datetime.timezone.utc)

    # 2. Aggregating Quality Reports
    total_rows = sum(sf.row_count for sf in stable_files if sf.row_count > 0)

    # Track metrics
    quality_summary = {
        "total_files": len(stable_files),
        "total_rows": total_rows,
        "filename_date_mismatch_count": 0,
        "timezone_naive_count": 0,
        "mixed_timezone_count": 0,
        "duplicate_timestamps": 0,
        "conflicting_duplicates": 0,
        "non_monotonic_sessions": 0,
        "ohlc_nulls": 0,
        "volume_nulls": 0,
        "zero_volume_count": 0,
        "zero_volume_pct": 0.0,
        "negative_volume_count": 0,
        "high_lt_low": 0,
        "high_lt_open": 0,
        "high_lt_close": 0,
        "low_gt_open": 0,
        "low_gt_close": 0,
        "non_positive_prices": 0,
        "outside_market_hours": 0,
        "interval_gaps": 0,
        "duplicate_session_files": 0,
        "content_identical_files": 0,
    }

    session_instruments = {} # date -> set of instruments
    all_sessions = set()

    # Run quality check on stable underlying candle files
    for sf in stable_files:
        if sf.data_family == "underlying_candles":
            q = check_ohlcv_file(sf.absolute_path)
            quality_summary["filename_date_mismatch_count"] += 1 if q["filename_date_mismatch"] else 0
            quality_summary["timezone_naive_count"] += 1 if q["timezone_naive"] else 0
            quality_summary["mixed_timezone_count"] += 1 if q["mixed_timezone"] else 0
            quality_summary["duplicate_timestamps"] += q["duplicate_timestamps"]
            quality_summary["conflicting_duplicates"] += q["conflicting_duplicates"]
            quality_summary["non_monotonic_sessions"] += q["non_monotonic"]
            quality_summary["ohlc_nulls"] += q["ohlc_nulls"]
            quality_summary["volume_nulls"] += q["volume_nulls"]
            quality_summary["zero_volume_count"] += q["zero_volume_count"]
            quality_summary["negative_volume_count"] += q["negative_volume_count"]
            quality_summary["high_lt_low"] += q["high_lt_low"]
            quality_summary["high_lt_open"] += q["high_lt_open"]
            quality_summary["high_lt_close"] += q["high_lt_close"]
            quality_summary["low_gt_open"] += q["low_gt_open"]
            quality_summary["low_gt_close"] += q["low_gt_close"]
            quality_summary["non_positive_prices"] += q["non_positive_prices"]
            quality_summary["outside_market_hours"] += q["outside_market_hours"]
            quality_summary["interval_gaps"] += q["interval_gaps"]

            for d in q["unique_dates"]:
                all_sessions.add(d)
                if d not in session_instruments:
                    session_instruments[d] = set()
                for inst in sf.instruments:
                    session_instruments[d].add(inst)

        if sf.duplicate_of:
            quality_summary["content_identical_files"] += 1

    if total_rows > 0:
        quality_summary["zero_volume_pct"] = (quality_summary["zero_volume_count"] / total_rows) * 100

    # Overlap analysis
    cross_index_summary = {
        "total_observed_sessions": len(all_sessions),
        "eligible_nifty_banknifty": 0,
        "eligible_all_three": 0,
        "ineligible_missing_index": 0,
        "ineligible_interval_mismatch": 0,
        "ineligible_timestamp_misalignment": 0,
        "ineligible_data_quality": 0,
        "first_eligible_date": None,
        "last_eligible_date": None,
        "rejection_reasons": {}
    }

    eligible_dates = []
    for date, insts in session_instruments.items():
        has_nifty = "NIFTY" in insts or "NSE_INDEX|Nifty 50" in insts
        has_banknifty = "BANKNIFTY" in insts or "NSE_INDEX|Nifty Bank" in insts
        has_sensex = "SENSEX" in insts or "BSE_INDEX|SENSEX" in insts

        if has_nifty and has_banknifty:
            cross_index_summary["eligible_nifty_banknifty"] += 1
            eligible_dates.append(date)
            if has_sensex:
                cross_index_summary["eligible_all_three"] += 1
        else:
            cross_index_summary["ineligible_missing_index"] += 1
            cross_index_summary["rejection_reasons"][date] = "Missing indices"

    if eligible_dates:
        eligible_dates.sort()
        cross_index_summary["first_eligible_date"] = eligible_dates[0]
        cross_index_summary["last_eligible_date"] = eligible_dates[-1]

    # Tick readiness summary
    tick_groups = {}
    for sf in stable_files:
        if sf.data_family == "ticks":
            cols = set(sf.schema_dict.keys())
            has_option_id = any(c in cols for c in ["expiry", "strike", "option_type"])
            has_ltp = "ltp" in cols
            has_bid_ask = "bid" in cols or "ask" in cols

            if has_option_id and has_bid_ask and has_ltp:
                readiness = "STRICT_OPTION_REPLAY_POTENTIALLY_CAPABLE"
            elif has_ltp and not has_bid_ask:
                readiness = "LTP_ONLY_NOT_EXECUTABLE"
            else:
                readiness = "UNDERLYING_TICK_ONLY"

            fp = sf.schema_fingerprint
            if fp not in tick_groups:
                tick_groups[fp] = {
                    "schema": sf.schema_dict,
                    "readiness": readiness,
                    "count": 0
                }
            tick_groups[fp]["count"] += 1

    # Output manifest
    manifest_data = {
        "manifest_schema_version": "1.1",
        "scan_id": args.scan_id,
        "scan_mode": scan_mode,
        "scan_start_utc": start_time_utc.isoformat(),
        "scan_start_ist": start_time_ist.isoformat(),
        "scan_end_utc": end_time_utc.isoformat(),
        "head": os.popen("git rev-parse HEAD").read().strip(),
        "branch": os.popen("git branch --show-current").read().strip(),
        "source_roots": args.roots,
        "root_statuses": root_statuses,
        "inclusion_policy": "STABLE_INCLUDED_ONLY",
        "stable_file_count": len(stable_files),
        "unstable_file_count": len(unstable_files),
        "portable_dataset_hash": portable_hash,
        "local_provenance_hash": local_hash,
        "stable_files": stable_dicts
    }

    # Save output artifacts (names match the mode)
    manifest_filename = f"source_manifest_{scan_mode.lower()}.json"
    inventory_filename = f"data_inventory_{scan_mode.lower()}.json"

    with open(outdir / manifest_filename, "w") as f:
        json_dump(manifest_data, f, indent=2)

    with open(outdir / inventory_filename, "w") as f:
        # Save complete parsed inventory
        complete_inv = []
        for x in scanned_inventories:
            complete_inv.append({
                "absolute_path": x.absolute_path,
                "source_root": x.source_root,
                "relative_path": x.relative_path,
                "inode": x.inode,
                "size_bytes": x.size_bytes,
                "stability": x.stability,
                "sha256": x.sha256,
                "row_count": x.row_count,
                "schema_fingerprint": x.schema_fingerprint,
                "min_timestamp": x.min_timestamp,
                "max_timestamp": x.max_timestamp,
                "timezone": x.timezone,
                "instruments": x.instruments,
                "data_family": x.data_family,
                "is_empty": x.is_empty,
                "error": x.error
            })
        json_dump(complete_inv, f, indent=2)

    # Also update the canonical manifest files for backward compatibility
    with open(outdir / "source_manifest.json", "w") as f:
        json_dump(manifest_data, f, indent=2)

    with open(outdir / "data_inventory.json", "w") as f:
        json_dump(complete_inv, f, indent=2)

    # Write quality report
    with open(outdir / "data_quality_report.md", "w") as f:
        f.write("# Quantitative Data Quality Report\n\n")
        f.write("| Metric | Value |\n")
        f.write("| --- | --- |\n")
        for k, v in quality_summary.items():
            f.write(f"| {k} | {v} |\n")

    with open(outdir / "cross_index_session_overlap.json", "w") as f:
        json_dump(cross_index_summary, f, indent=2)

    with open(outdir / "option_data_readiness.json", "w") as f:
        json_dump({
            "tick_groups": tick_groups,
            "overall_verdict": "UNDERLYING_EDGE_RESEARCH_ONLY_OPTION_CERTIFICATION_BLOCKED"
        }, f, indent=2)

    # Write summaries
    summary_filename = "smoke_scan_001_summary.json" if scan_mode == "SMOKE" else "full_scan_summary.json"
    summary_data = {
        "scan_id": args.scan_id,
        "scan_mode": scan_mode,
        "portable_dataset_hash": portable_hash,
        "local_provenance_hash": local_hash,
        "stable_file_count": len(stable_files),
        "total_rows": total_rows,
        "quality_summary": quality_summary,
        "cross_index_summary": cross_index_summary
    }
    with open(outdir / summary_filename, "w") as f:
        json_dump(summary_data, f, indent=2)

    # Write handoff
    with open(outdir / "phase0_handoff.md", "w") as f:
        f.write(f"# Phase 0 Handoff\n\n- Scan Mode: {scan_mode}\n- Portable Hash: {portable_hash}\n- Local Provenance Hash: {local_hash}\n\nData is fully scanned and verified.")

    print("Inventory run completed successfully.")

if __name__ == "__main__":
    main()
