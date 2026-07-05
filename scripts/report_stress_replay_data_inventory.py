import json
import pandas as pd
from pathlib import Path
import os

def load_instrument_master(roots):
    for root in roots:
        p = Path(root)
        if not p.exists():
            continue
        for f in p.rglob("*"):
            if f.is_file() and any(x in f.name.lower() for x in ["instrument", "kite", "upstox"]) and f.suffix.lower() == ".json":
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        if isinstance(data, list) and len(data) > 0 and "instrument_token" in data[0]:
                            mapping = {str(item["instrument_token"]): item for item in data}
                            return str(f), mapping
                except Exception:
                    pass
    return None, {}

def create_report():
    report = []
    roots = ["runtime", ".runtime", "data", "configs", "reports", "."]
    
    im_path, im_map = load_instrument_master(roots)
    
    # Check JSON/JSONL
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
                            "instrument_master_path": None,
                            "instrument_tokens_sampled": 0,
                            "instrument_tokens_resolved": 0,
                            "instrument_tokens_unresolved": 0,
                            "resolved_option_contracts_count": 0,
                            "resolved_underlying_symbols": [],
                            "metadata_blockers": ["DATA_BLOCKED_TOO_LARGE"],
                            "notes": "File too large"
                        })
                        continue
                except OSError:
                    pass
                    
        for f in p.rglob("*.parquet"):
            try:
                df = pd.read_parquet(f)
                rows_inspected = len(df)
                cols = set(df.columns)
                
                # evaluate fields
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
                tokens_unresolved = 0
                option_contracts = 0
                underlying_symbols = set()
                metadata_blockers = []
                instrument_metadata_verified = False

                if "instrument_token" in cols:
                    unique_tokens = df["instrument_token"].dropna().unique()
                    tokens_sampled = len(unique_tokens)
                    
                    if not im_map:
                        metadata_blockers.append("DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED")
                        tokens_unresolved = tokens_sampled
                    else:
                        for token in unique_tokens:
                            token_str = str(token)
                            if token_str in im_map:
                                tokens_resolved += 1
                                item = im_map[token_str]
                                
                                has_expiry = item.get("expiry") is not None
                                has_strike = item.get("strike") is not None and item.get("strike") > 0
                                is_option = item.get("instrument_type") in ["CE", "PE"] or item.get("segment") in ["NFO-OPT", "BFO-OPT"]
                                
                                if has_expiry and has_strike and is_option:
                                    option_contracts += 1
                                    instrument_metadata_verified = True
                                else:
                                    underlying_symbols.add(item.get("tradingsymbol", "UNKNOWN"))
                                    
                                if not has_expiry and "DATA_BLOCKED_OPTION_METADATA_MISSING" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_OPTION_METADATA_MISSING")
                                if not has_strike and "DATA_BLOCKED_OPTION_METADATA_MISSING" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_OPTION_METADATA_MISSING")
                                if not is_option and "DATA_BLOCKED_OPTION_METADATA_MISSING" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_OPTION_METADATA_MISSING")

                            else:
                                tokens_unresolved += 1
                                if "DATA_BLOCKED_INSTRUMENT_TOKEN_UNRESOLVED" not in metadata_blockers:
                                    metadata_blockers.append("DATA_BLOCKED_INSTRUMENT_TOKEN_UNRESOLVED")

                        if option_contracts == 0 and tokens_sampled > 0:
                            if "DATA_BLOCKED_NO_OPTION_CONTRACTS_RESOLVED" not in metadata_blockers:
                                metadata_blockers.append("DATA_BLOCKED_NO_OPTION_CONTRACTS_RESOLVED")
                else:
                    metadata_blockers.append("DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED")
                    
                if not has_bid_ask and "DATA_BLOCKED_BID_ASK_MISSING" not in metadata_blockers:
                    metadata_blockers.append("DATA_BLOCKED_BID_ASK_MISSING")
                # Depth missing might not block stress if bid/ask exists, but we add it to missing
                if not has_depth and "DATA_BLOCKED_DEPTH_MISSING" not in metadata_blockers:
                    metadata_blockers.append("DATA_BLOCKED_DEPTH_MISSING")

                classification = "MISSING"
                if unsafe_markers:
                    classification = "NON_CERTIFIABLE_SYNTHETIC_OR_PROXY"
                elif has_option_ltp and has_bid_ask and has_real_provenance and has_timestamp:
                    if instrument_metadata_verified and option_contracts > 0:
                        classification = "STRESS_REPLAY_CAPABLE"
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
                    "instrument_tokens_unresolved": tokens_unresolved,
                    "resolved_option_contracts_count": option_contracts,
                    "resolved_underlying_symbols": list(underlying_symbols),
                    "metadata_blockers": metadata_blockers,
                    "notes": ""
                })
                
            except Exception as e:
                pass
                
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "stress_replay_data_inventory_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    md_lines = ["# Stress Replay Data Inventory Report\n"]
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
    create_report()
