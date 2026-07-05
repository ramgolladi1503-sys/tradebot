import json
import pandas as pd
from pathlib import Path
import os
import argparse
import csv

def load_instrument_master(file_path):
    p = Path(file_path)
    if not p.exists():
        return None, {}
        
    mapping = {}
    try:
        if p.suffix.lower() == ".json":
            with open(p) as fh:
                data = json.load(fh)
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list):
                            items.extend(v)
                for item in items:
                    if isinstance(item, dict) and "instrument_token" in item:
                        mapping[str(item["instrument_token"])] = item
        elif p.suffix.lower() == ".csv":
            with open(p, newline="") as fh:
                reader = csv.DictReader(fh)
                for item in reader:
                    if "instrument_token" in item:
                        mapping[str(item["instrument_token"])] = item
        elif p.suffix.lower() == ".parquet":
            df = pd.read_parquet(p)
            for item in df.to_dict("records"):
                if "instrument_token" in item:
                    mapping[str(item["instrument_token"])] = item
    except Exception as e:
        print(f"Error loading instrument master {file_path}: {e}")
    
    if mapping:
        return str(p), mapping
    return None, {}

def create_report(instrument_master_path=None):
    report = []
    
    im_path, im_map = None, {}
    if instrument_master_path:
        im_path, im_map = load_instrument_master(instrument_master_path)
    
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    for root in ["runtime", ".runtime", "data", "reports"]:
        p = Path(root)
        if not p.exists():
            continue
            
        for f in p.rglob("*"):
            if f.suffix.lower() in {".json", ".jsonl"} and f.is_file():
                try:
                    if f.stat().st_size > 200_000_000:
                        report.append({
                            "path": str(f),
                            "format": f.suffix.lower()[1:],
                            "rows_inspected": 0,
                            "estimated_rows": None,
                            "classification": "TOO_LARGE_NOT_INSPECTED",
                            "has_option_ltp": False,
                            "has_bid_ask": False,
                            "has_depth": False,
                            "has_timestamp": False,
                            "has_real_provenance": False,
                            "unsafe_source_markers_found": [],
                            "missing_required_fields": [],
                            "instrument_metadata_verified": False,
                            "instrument_master_path": im_path,
                            "instrument_tokens_sampled": 0,
                            "instrument_tokens_resolved": 0,
                            "instrument_tokens_unresolved": 0,
                            "resolved_option_contracts_count": 0,
                            "resolved_underlying_symbols": [],
                            "resolved_option_contracts_sample": [],
                            "metadata_blockers": ["DATA_BLOCKED_TOO_LARGE"],
                            "notes": "File too large",
                            "stress_replay_capable": False,
                            "partial_stress_replay_capable": False,
                            "requires_token_filter": False,
                            "resolved_option_tokens": [],
                            "unresolved_tokens": [],
                            "non_option_tokens": [],
                            "usable_rows_count": 0,
                            "excluded_rows_count": 0,
                            "usable_dataset_path": None,
                            "usable_token_index_path": None
                        })
                        continue
                except OSError:
                    pass
                    
        for f in p.rglob("*.parquet"):
            # skip files we create in this script
            if "resolved_option_ticks" in f.name:
                continue

            try:
                df = pd.read_parquet(f)
                rows_inspected = len(df)
                cols = set(df.columns)
                
                has_option_ltp = "last_price" in cols or "option_ltp" in cols
                has_bid_ask = "best_bid" in cols and "best_ask" in cols
                has_depth = "depth_json" in cols
                has_timestamp = "local_ts" in cols or "exchange_timestamp" in cols or "date" in cols or "ts" in cols
                
                has_real_provenance = True
                unsafe_markers = []
                if "synthetic" in str(f).lower() or "mock" in str(f).lower() or "proxy" in str(f).lower() or "fallback" in str(f).lower():
                    has_real_provenance = False
                    unsafe_markers.append("filename_indicates_unsafe_source")
                    
                missing = []
                if not has_option_ltp: missing.append("option_ltp")
                if not has_bid_ask: missing.append("bid_ask")
                if not has_timestamp: missing.append("timestamp")
                if not has_depth: missing.append("depth")

                tokens_sampled = 0
                tokens_resolved = 0
                tokens_unresolved_count = 0
                option_contracts = 0
                underlying_symbols = set()
                option_contracts_sample = []
                metadata_blockers = []
                instrument_metadata_verified = False
                
                resolved_option_tokens_info = []
                unresolved_tokens_list = []
                non_option_tokens_list = []
                resolved_option_token_ids = set()

                if "instrument_token" in cols:
                    unique_tokens = df["instrument_token"].dropna().unique()
                    tokens_sampled = len(unique_tokens)
                    
                    if not instrument_master_path or not im_map:
                        metadata_blockers.append("DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED")
                        tokens_unresolved_count = tokens_sampled
                        unresolved_tokens_list = [str(t) for t in unique_tokens]
                    else:
                        for token in unique_tokens:
                            token_str = str(token)
                            if token_str in im_map:
                                tokens_resolved += 1
                                item = im_map[token_str]
                                
                                has_expiry = item.get("expiry") is not None and item.get("expiry") != ""
                                
                                strike_val = item.get("strike")
                                try:
                                    strike_val = float(strike_val)
                                except (TypeError, ValueError):
                                    strike_val = 0
                                has_strike = strike_val > 0
                                
                                is_option = item.get("instrument_type") in ["CE", "PE"] or item.get("segment") in ["NFO-OPT", "BFO-OPT"]
                                
                                has_trading_symbol = item.get("tradingsymbol") is not None and item.get("tradingsymbol") != ""
                                
                                if has_expiry and has_strike and is_option and has_trading_symbol:
                                    option_contracts += 1
                                    instrument_metadata_verified = True
                                    resolved_option_token_ids.add(token)
                                    resolved_option_tokens_info.append({
                                        "instrument_token": token_str,
                                        "tradingsymbol": item.get("tradingsymbol"),
                                        "expiry": item.get("expiry"),
                                        "strike": strike_val,
                                        "option_type": item.get("instrument_type"),
                                        "segment": item.get("segment")
                                    })
                                    if len(option_contracts_sample) < 5:
                                        option_contracts_sample.append(item.get("tradingsymbol"))
                                else:
                                    underlying_symbols.add(item.get("tradingsymbol", "UNKNOWN"))
                                    non_option_tokens_list.append(token_str)
                                    
                                if not has_expiry and "DATA_BLOCKED_OPTION_METADATA_MISSING" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_OPTION_METADATA_MISSING")
                                if not has_strike and "DATA_BLOCKED_OPTION_METADATA_MISSING" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_OPTION_METADATA_MISSING")
                                if not is_option and "DATA_BLOCKED_OPTION_METADATA_MISSING" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_OPTION_METADATA_MISSING")
                            else:
                                tokens_unresolved_count += 1
                                unresolved_tokens_list.append(token_str)
                                if "DATA_BLOCKED_INSTRUMENT_TOKEN_UNRESOLVED" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_INSTRUMENT_TOKEN_UNRESOLVED")

                        if option_contracts == 0 and tokens_sampled > 0:
                            if "DATA_BLOCKED_NO_OPTION_CONTRACTS_RESOLVED" not in metadata_blockers:
                                metadata_blockers.append("DATA_BLOCKED_NO_OPTION_CONTRACTS_RESOLVED")
                else:
                    metadata_blockers.append("DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED")
                    
                if not has_bid_ask and "DATA_BLOCKED_BID_ASK_MISSING" not in metadata_blockers:
                    metadata_blockers.append("DATA_BLOCKED_BID_ASK_MISSING")
                if not has_depth and "DATA_BLOCKED_DEPTH_MISSING" not in metadata_blockers:
                    metadata_blockers.append("DATA_BLOCKED_DEPTH_MISSING")

                classification = "MISSING"
                
                stress_replay_capable = False
                partial_stress_replay_capable = False
                requires_token_filter = False
                
                usable_rows_count = 0
                excluded_rows_count = 0
                usable_dataset_path = None
                usable_token_index_path = None

                if unsafe_markers:
                    classification = "NON_CERTIFIABLE_SYNTHETIC_OR_PROXY"
                elif has_option_ltp and has_bid_ask and has_real_provenance and has_timestamp:
                    if instrument_metadata_verified and option_contracts > 0:
                        if tokens_unresolved_count == 0 and len(non_option_tokens_list) == 0:
                            classification = "STRESS_REPLAY_CAPABLE"
                            stress_replay_capable = True
                            usable_rows_count = rows_inspected
                        else:
                            classification = "PARTIAL_STRESS_REPLAY_CAPABLE"
                            partial_stress_replay_capable = True
                            requires_token_filter = True
                            
                            # Build token index
                            index_data = {
                                "source_path": str(f),
                                "instrument_master_path": im_path,
                                "resolved_option_tokens_count": option_contracts,
                                "unresolved_tokens_count": tokens_unresolved_count + len(non_option_tokens_list),
                                "resolved_option_tokens": resolved_option_tokens_info,
                                "unresolved_tokens": unresolved_tokens_list + non_option_tokens_list,
                                "certification_use_rule": "ONLY_ROWS_WITH_RESOLVED_OPTION_TOKENS_ARE_CERTIFIABLE"
                            }
                            usable_token_index_path = out_dir / "stress_replay_resolved_option_token_index.json"
                            with open(usable_token_index_path, "w") as idx_f:
                                json.dump(index_data, idx_f, indent=2)
                            
                            # Attempt to build filtered dataset
                            usable_dataset_path = out_dir / f"resolved_option_ticks_{Path(f).stem.replace('index_ticks', '').strip('_')}.parquet"
                            if not usable_dataset_path.name.replace('resolved_option_ticks_', '').replace('.parquet', ''):
                                usable_dataset_path = out_dir / "resolved_option_ticks_20260702.parquet"
                                
                            try:
                                filtered_df = df[df["instrument_token"].isin(resolved_option_token_ids)]
                                usable_rows_count = len(filtered_df)
                                excluded_rows_count = rows_inspected - usable_rows_count
                                filtered_df.to_parquet(usable_dataset_path)
                            except Exception:
                                usable_dataset_path = None
                                usable_rows_count = 0
                                excluded_rows_count = rows_inspected
                    else:
                        classification = "STRESS_REPLAY_CANDIDATE_METADATA_BLOCKED"
                elif has_option_ltp and not has_bid_ask:
                    if instrument_metadata_verified and option_contracts > 0:
                        classification = "OPTION_CANDLE_ONLY"
                    else:
                        classification = "INSUFFICIENT_SCHEMA"
                elif "open" in cols and not has_option_ltp:
                    classification = "UNDERLYING_ONLY"
                elif option_contracts == 0 and tokens_resolved > 0 and len(underlying_symbols) > 0:
                    classification = "UNDERLYING_ONLY"
                else:
                    classification = "INSUFFICIENT_SCHEMA"
                    
                if not instrument_master_path:
                    im_path = None
                    
                report.append({
                    "path": str(f),
                    "format": "parquet",
                    "rows_inspected": rows_inspected,
                    "estimated_rows": rows_inspected,
                    "classification": classification,
                    "has_option_ltp": has_option_ltp,
                    "has_bid_ask": has_bid_ask,
                    "has_depth": has_depth,
                    "has_timestamp": has_timestamp,
                    "has_real_provenance": has_real_provenance,
                    "unsafe_source_markers_found": unsafe_markers,
                    "missing_required_fields": missing,
                    "instrument_metadata_verified": instrument_metadata_verified,
                    "instrument_master_path": im_path,
                    "instrument_tokens_sampled": tokens_sampled,
                    "instrument_tokens_resolved": tokens_resolved,
                    "instrument_tokens_unresolved": tokens_unresolved_count,
                    "resolved_option_contracts_count": option_contracts,
                    "resolved_underlying_symbols": list(underlying_symbols),
                    "resolved_option_contracts_sample": option_contracts_sample,
                    "metadata_blockers": metadata_blockers,
                    "notes": "",
                    "stress_replay_capable": stress_replay_capable,
                    "partial_stress_replay_capable": partial_stress_replay_capable,
                    "requires_token_filter": requires_token_filter,
                    "resolved_option_tokens": resolved_option_tokens_info,
                    "unresolved_tokens": unresolved_tokens_list,
                    "non_option_tokens": non_option_tokens_list,
                    "usable_rows_count": usable_rows_count,
                    "excluded_rows_count": excluded_rows_count,
                    "usable_dataset_path": str(usable_dataset_path) if usable_dataset_path else None,
                    "usable_token_index_path": str(usable_token_index_path) if usable_token_index_path else None
                })
                
            except Exception as e:
                pass
                
    with open(out_dir / "stress_replay_data_inventory_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    md_lines = ["# Stress Replay Data Inventory Report\n"]
    if not instrument_master_path:
        md_lines.append("**INSTRUMENT_MASTER_MISSING**: No instrument master was provided via --instrument-master. Option metadata cannot be verified.\n")
    for r in report:
        md_lines.append(f"## {r['path']}")
        md_lines.append(f"- Classification: {r['classification']}")
        md_lines.append(f"- Rows: {r['rows_inspected']}")
        md_lines.append(f"- Metadata Verified: {r['instrument_metadata_verified']}")
        md_lines.append(f"- Option Contracts: {r['resolved_option_contracts_count']}")
        md_lines.append(f"- Missing Fields: {r['missing_required_fields']}")
        md_lines.append(f"- Blockers: {r['metadata_blockers']}\n")
        
    with open(out_dir / "stress_replay_data_inventory_report.md", "w") as f:
        f.write("\n".join(md_lines))
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument-master", help="Path to instrument master JSON/CSV/Parquet")
    args = parser.parse_args()
    create_report(args.instrument_master)
