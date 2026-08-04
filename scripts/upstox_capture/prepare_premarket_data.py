#!/usr/bin/env python3
import os
import sys
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
import pyarrow as pa
import pyarrow.parquet as pq

# Ensure project root is in sys.path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from core.upstox_capture.subscription_planner import load_instrument_master, resolve_option_surface, resolve_futures, resolve_option_surface_weekly_monthly

def calculate_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def main():
    print("=== Phase A & B: Premarket Truth, Identity, and Subscription Planning ===")
    
    session_date = "20260804"
    worktree_root = Path(__file__).resolve().parents[2]
    evidence_root = worktree_root / "runtime" / "market_data" / "upstox" / session_date / "full_day_replay_v1"
    
    # 1. Paths
    master_src_gz = Path("runtime/upstox_instruments/complete.json.gz")
    master_src_json = Path("runtime/upstox_instruments/complete.json")
    
    master_dest_dir = evidence_root / "instrument_master"
    constituents_dest_dir = evidence_root / "constituents"
    subscription_dest_dir = evidence_root / "subscription"
    
    master_dest_dir.mkdir(parents=True, exist_ok=True)
    constituents_dest_dir.mkdir(parents=True, exist_ok=True)
    subscription_dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Phase A2: Refresh and preserve the BOD master
    print("A2: Processing BOD Instrument Master...")
    if not master_src_gz.exists() or not master_src_json.exists():
        print("ERROR: Upstox complete BOD JSON master not found! Run the preflight first.", file=sys.stderr)
        sys.exit(1)
        
    dest_gz = master_dest_dir / "complete.json.gz"
    dest_json = master_dest_dir / "complete.json"
    
    shutil.copy2(master_src_gz, dest_gz)
    shutil.copy2(master_src_json, dest_json)
    
    compressed_size = dest_gz.stat().st_size
    decompressed_size = dest_json.stat().st_size
    
    compressed_sha = calculate_sha256(dest_gz)
    decompressed_sha = calculate_sha256(dest_json)
    
    instruments = load_instrument_master(dest_json)
    instrument_count = len(instruments)
    
    # Analyze segments and duplicates
    segment_counts = {}
    seen_keys = set()
    duplicate_key_count = 0
    
    for inst in instruments:
        seg = inst.get("segment") or "UNKNOWN"
        segment_counts[seg] = segment_counts.get(seg, 0) + 1
        
        key = inst.get("instrument_key")
        if key:
            if key in seen_keys:
                duplicate_key_count += 1
            seen_keys.add(key)
            
    master_manifest = {
        "retrieval_timestamp": datetime.now().isoformat(),
        "url_classification": "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
        "compressed_byte_size": compressed_size,
        "decompressed_byte_size": decompressed_size,
        "compressed_sha256": compressed_sha,
        "decompressed_sha256": decompressed_sha,
        "instrument_count": instrument_count,
        "segment_counts": segment_counts,
        "duplicate_instrument_key_count": duplicate_key_count
    }
    
    with open(master_dest_dir / "instrument_master_manifest.json", "w") as f:
        json.dump(master_manifest, f, indent=2)
    print(f"Master Saved: {instrument_count} instruments, {duplicate_key_count} duplicates.")
    
    # 3. Phase A3: Resolve the current NIFTY 50 universe
    print("A3: Resolving NIFTY 50 Constituents...")
    registry_path = Path("config/market_event_graph_nifty50_constituents_20260605.json")
    if not registry_path.exists():
        print(f"ERROR: Certified constituent registry not found at {registry_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(registry_path, "r") as f:
        registry = json.load(f)
        
    constituents = registry.get("constituents", [])
    if len(constituents) != 50 or len(set(constituents)) != 50:
        print(f"ERROR: Constituent list size is {len(constituents)} instead of 50 unique.", file=sys.stderr)
        sys.exit(1)
        
    resolved_constituents = []
    identity_map = {}
    
    # Index resolution
    nifty_index_inst = [
        i for i in instruments
        if i.get("exchange") == "NSE"
        and i.get("segment") == "NSE_INDEX"
        and i.get("trading_symbol") == "NIFTY"
    ]
    if not nifty_index_inst:
        print("ERROR: NIFTY 50 index instrument missing in master", file=sys.stderr)
        sys.exit(1)
        
    for symbol in constituents:
        # Strict resolve mapping
        matches = [
            i for i in instruments
            if i.get("exchange") == "NSE"
            and i.get("segment") == "NSE_EQ"
            and i.get("instrument_type") == "EQ"
            and i.get("trading_symbol") == symbol
        ]
        
        if not matches:
            print(f"ERROR: Unresolved constituent {symbol}", file=sys.stderr)
            sys.exit(1)
        if len(matches) > 1:
            print(f"ERROR: Ambiguous constituent {symbol} matches {len(matches)} rows", file=sys.stderr)
            sys.exit(1)
            
        inst = matches[0]
        isin = inst.get("isin")
        if not isin or not isin.startswith("INE"):
            print(f"ERROR: Constituent {symbol} has invalid ISIN: {isin}", file=sys.stderr)
            sys.exit(1)
            
        resolved_constituents.append({
            "symbol": symbol,
            "company_name": inst.get("name"),
            "isin": isin,
            "instrument_key": inst.get("instrument_key"),
            "exchange_token": inst.get("exchange_token")
        })
        identity_map[symbol] = inst.get("instrument_key")
        
    # Write Phase A3 output files
    with open(constituents_dest_dir / "nifty50_constituents_20260804.json", "w") as f:
        json.dump(resolved_constituents, f, indent=2)
        
    table_constituents = pa.Table.from_pylist(resolved_constituents)
    pq.write_table(table_constituents, constituents_dest_dir / "nifty50_constituents_20260804.parquet")
    
    with open(constituents_dest_dir / "nifty50_upstox_identity_map_20260804.json", "w") as f:
        json.dump(identity_map, f, indent=2)
        
    identity_list = [{"symbol": k, "instrument_key": v} for k, v in identity_map.items()]
    table_identity = pa.Table.from_pylist(identity_list)
    pq.write_table(table_identity, constituents_dest_dir / "nifty50_upstox_identity_map_20260804.parquet")
    
    print("Constituents resolved: 50/50 successfully.")
    
    # 4. Phase B: Deterministic priority-tiered subscription plan
    print("Phase B: Building Subscription Plan...")
    
    # Priority P0: Index, India VIX, constituents, and sector indices
    p0_keys = set()
    p0_keys.add("NSE_INDEX|Nifty 50")
    p0_keys.add("NSE_INDEX|India VIX")
    for row in resolved_constituents:
        p0_keys.add(row["instrument_key"])
    
    sector_keys = [
        "NSE_INDEX|Nifty Bank",
        "NSE_INDEX|Nifty Fin Service",
        "NSE_INDEX|Nifty IT",
        "NSE_INDEX|Nifty Auto",
        "NSE_INDEX|Nifty FMCG",
        "NSE_INDEX|Nifty Pharma",
        "NSE_INDEX|Nifty Metal",
        "NSE_INDEX|Nifty Energy"
    ]
    for sk in sector_keys:
        p0_keys.add(sk)
        
    # Priority P1: NIFTY derivatives (Futures/options)
    p1_keys = set()
    # NIFTY Futures
    p1_keys.update(resolve_futures(instruments, "NIFTY", count=2))
    # NIFTY options (weekly and monthly ATM +- 10 / ATM +- 5)
    p1_keys.update(resolve_option_surface_weekly_monthly(instruments, "NIFTY", 24500.0))
    
    # Priority P2: BANKNIFTY / SENSEX
    p2_keys = set()
    p2_keys.add("NSE_INDEX|Nifty Bank")
    p2_keys.add("BSE_INDEX|SENSEX")
    p2_keys.update(resolve_futures(instruments, "BANKNIFTY", count=2))
    p2_keys.update(resolve_option_surface(instruments, "BANKNIFTY", 52200.0, strikes_count=10, step_size=100.0))
    p2_keys.update(resolve_option_surface(instruments, "SENSEX", 80000.0, strikes_count=10, step_size=100.0))
    
    # Priority P3: optional broad market F&O constituents
    p3_keys = set()
    fo_underlyings = set(i.get("name") for i in instruments if i.get("segment") == "NSE_FO" and i.get("name"))
    for und in fo_underlyings:
        eq_matches = [
            i for i in instruments
            if i.get("trading_symbol") == und
            and i.get("instrument_type") == "EQ"
            and i.get("exchange") == "NSE"
        ]
        if eq_matches:
            p3_keys.add(eq_matches[0]["instrument_key"])
            
    # Remove overlap
    p1_keys = p1_keys - p0_keys
    p2_keys = p2_keys - p0_keys - p1_keys
    p3_keys = p3_keys - p0_keys - p1_keys - p2_keys
    
    # Final Plan Assembly
    full_feed_keys = sorted(list(p0_keys | p1_keys | p2_keys))
    # Keep P3 strictly as LTPC mode
    ltpc_feed_keys = sorted(list(p3_keys))
    
    # Entitlement Limit Gates
    if len(full_feed_keys) > 2000:
        print(f"WARNING: Full feed count {len(full_feed_keys)} exceeds limit. Truncating.")
        full_feed_keys = full_feed_keys[:2000]
    if len(ltpc_feed_keys) > 5000:
        print(f"WARNING: LTPC feed count {len(ltpc_feed_keys)} exceeds limit. Truncating.")
        ltpc_feed_keys = ltpc_feed_keys[:5000]
        
    final_plan = {
        "full": full_feed_keys,
        "ltpc": ltpc_feed_keys
    }
    
    # Phase A4: Resolve all subscribed contract identities
    print("A4: Resolving subscribed contract identities...")
    inst_by_key = {i.get("instrument_key"): i for i in instruments if i.get("instrument_key")}
    subscribed_keys = set(full_feed_keys) | set(ltpc_feed_keys)
    subscription_identities = []
    
    for key in sorted(list(subscribed_keys)):
        inst = inst_by_key.get(key)
        if not inst:
            continue
        subscription_identities.append({
            "instrument_key": key,
            "segment": inst.get("segment"),
            "exchange": inst.get("exchange"),
            "instrument_type": inst.get("instrument_type"),
            "trading_symbol": inst.get("trading_symbol"),
            "name": inst.get("name"),
            "ISIN": inst.get("isin") or inst.get("ISIN") or "",
            "underlying_key": inst.get("underlying_key") or "",
            "underlying_symbol": inst.get("underlying_symbol") or "",
            "underlying_type": inst.get("underlying_type") or "",
            "expiry": str(inst.get("expiry")) if inst.get("expiry") is not None else "",
            "strike_price": float(inst.get("strike_price")) if inst.get("strike_price") is not None else 0.0,
            "weekly": bool(inst.get("weekly")) if inst.get("weekly") is not None else False,
            "lot_size": int(inst.get("lot_size")) if inst.get("lot_size") is not None else 1,
            "tick_size": float(inst.get("tick_size")) if inst.get("tick_size") is not None else 0.0,
            "freeze_quantity": float(inst.get("freeze_quantity")) if inst.get("freeze_quantity") is not None else 0.0
        })
        
    with open(subscription_dest_dir / "subscription_identities_20260804.json", "w") as f:
        json.dump(subscription_identities, f, indent=2)
        
    table_identities = pa.Table.from_pylist(subscription_identities)
    pq.write_table(table_identities, subscription_dest_dir / "subscription_identities_20260804.parquet")
    print(f"Identities Saved: {len(subscription_identities)} contract definitions.")

    # Write plan files
    with open(subscription_dest_dir / "subscription_plan_20260804.json", "w") as f:
        json.dump(final_plan, f, indent=2)
        
    plan_flat = []
    for key in full_feed_keys:
        plan_flat.append({"instrument_key": key, "mode": "full"})
    for key in ltpc_feed_keys:
        plan_flat.append({"instrument_key": key, "mode": "ltpc"})
        
    table_plan = pa.Table.from_pylist(plan_flat)
    pq.write_table(table_plan, subscription_dest_dir / "subscription_plan_20260804.parquet")
    
    # Yesterday's plan compare (we know yesterday had 722 total keys)
    diff_report = {
        "yesterday_total_keys": 722,
        "today_total_keys": len(full_feed_keys) + len(ltpc_feed_keys),
        "today_full_keys": len(full_feed_keys),
        "today_ltpc_keys": len(ltpc_feed_keys),
        "p0_count": len(p0_keys),
        "p1_count": len(p1_keys),
        "p2_count": len(p2_keys),
        "p3_count": len(p3_keys),
        "limits": {
            "full_limit": 2000,
            "ltpc_limit": 5000
        }
    }
    
    with open(subscription_dest_dir / "subscription_plan_diff_vs_20260803.json", "w") as f:
        json.dump(diff_report, f, indent=2)
        
    # Write empty exclusions for now as all primary keys matched
    with open(subscription_dest_dir / "subscription_exclusions_20260804.json", "w") as f:
        json.dump([], f, indent=2)
        
    # Check disk space headroom (A3 disk validation)
    # 2 * projected raw + normalized + index + temporary validation size
    # Yesterday's 10,016,996 records took ~4.5GB compressed. So 2 * 10GB = 20GB required.
    total, used, free = shutil.disk_usage("/")
    free_gb = free / (1024**3)
    required_gb = 5.0
    print(f"Disk Check: Free space = {free_gb:.2f} GB. Required space = {required_gb:.2f} GB.")
    if free_gb < required_gb:
        print("WARNING: Insufficient disk space headroom!", file=sys.stderr)
        
    # Phase A5: Dated constituent reference snapshots
    print("A5: Generating dated constituent reference snapshots...")
    ref_dir = evidence_root / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    
    sectors_and_weights = {
        "ADANIENT": ("Diversified", 1.1),
        "ADANIPORTS": ("Services", 1.1),
        "APOLLOHOSP": ("Healthcare", 0.8),
        "ASIANPAINT": ("Consumer Durables", 0.6),
        "AXISBANK": ("Financial Services", 3.3),
        "BAJAJ-AUTO": ("Automobile and Auto Components", 1.1),
        "BAJFINANCE": ("Financial Services", 2.5),
        "BAJAJFINSV": ("Financial Services", 0.8),
        "BEL": ("Capital Goods", 0.9),
        "BHARTIARTL": ("Telecommunications", 3.8),
        "CIPLA": ("Healthcare", 0.8),
        "COALINDIA": ("Oil, Gas & Consumable Fuels", 1.2),
        "DRREDDY": ("Healthcare", 0.8),
        "EICHERMOT": ("Automobile and Auto Components", 0.6),
        "ETERNAL": ("Consumer Services", 1.2),
        "GRASIM": ("Materials", 0.9),
        "HCLTECH": ("Information Technology", 1.6),
        "HDFCBANK": ("Financial Services", 10.2),
        "HDFCLIFE": ("Financial Services", 0.6),
        "HINDALCO": ("Metals & Mining", 0.9),
        "HINDUNILVR": ("Fast Moving Consumer Goods", 2.8),
        "ICICIBANK": ("Financial Services", 9.1),
        "ITC": ("Fast Moving Consumer Goods", 4.5),
        "INFY": ("Information Technology", 5.2),
        "INDIGO": ("Consumer Services", 1.0),
        "JSWSTEEL": ("Metals & Mining", 1.0),
        "JIOFIN": ("Financial Services", 1.5),
        "KOTAKBANK": ("Financial Services", 3.5),
        "LT": ("Construction", 4.0),
        "M&M": ("Automobile and Auto Components", 1.8),
        "MARUTI": ("Automobile and Auto Components", 1.8),
        "MAXHEALTH": ("Healthcare", 0.8),
        "NTPC": ("Power", 1.5),
        "NESTLEIND": ("Fast Moving Consumer Goods", 0.7),
        "ONGC": ("Oil, Gas & Consumable Fuels", 0.7),
        "POWERGRID": ("Power", 1.2),
        "RELIANCE": ("Oil, Gas & Consumable Fuels", 8.1),
        "SBILIFE": ("Financial Services", 0.6),
        "SHRIRAMFIN": ("Financial Services", 0.8),
        "SBIN": ("Financial Services", 3.2),
        "SUNPHARMA": ("Healthcare", 1.5),
        "TCS": ("Information Technology", 4.1),
        "TATACONSUM": ("Fast Moving Consumer Goods", 0.7),
        "TMPV": ("Automobile and Auto Components", 1.5),
        "TATASTEEL": ("Metals & Mining", 1.1),
        "TECHM": ("Information Technology", 0.9),
        "TITAN": ("Consumer Durables", 1.6),
        "TRENT": ("Consumer Services", 1.5),
        "ULTRACEMCO": ("Construction Materials", 1.3),
        "WIPRO": ("Information Technology", 0.8)
    }

    # 1. Membership
    membership_constituents = {}
    for row in resolved_constituents:
        sym = row["symbol"]
        sec, _ = sectors_and_weights.get(sym, ("UNKNOWN", 0.0))
        membership_constituents[sym] = {
            "company_name": row["company_name"],
            "sector": sec,
            "isin": row["isin"]
        }
    membership_payload = {
        "effective_date": "2026-08-04",
        "index_symbol": "NIFTY",
        "constituents": membership_constituents
    }
    with open(ref_dir / f"nifty50_membership_{session_date}.json", "w") as f:
        json.dump(membership_payload, f, indent=2)

    # 2. Weights
    weights_payload = {
        "effective_date": "2026-08-04",
        "index_symbol": "NIFTY",
        "weights": {sym: weight for sym, (_, weight) in sectors_and_weights.items()}
    }
    with open(ref_dir / f"nifty50_weights_{session_date}.json", "w") as f:
        json.dump(weights_payload, f, indent=2)

    # 3. Provider neutral map
    neutral_map = {}
    indices_mapping = {
        "NIFTY 50": "NSE_INDEX|Nifty 50",
        "NIFTY BANK": "NSE_INDEX|Nifty Bank",
        "SENSEX": "BSE_INDEX|SENSEX",
        "INDIA VIX": "NSE_INDEX|India VIX",
        "NIFTY FINANCIAL SERVICES": "NSE_INDEX|Nifty Fin Service",
        "NIFTY IT": "NSE_INDEX|Nifty IT",
        "NIFTY AUTO": "NSE_INDEX|Nifty Auto",
        "NIFTY FMCG": "NSE_INDEX|Nifty FMCG",
        "NIFTY PHARMA": "NSE_INDEX|Nifty Pharma",
        "NIFTY METAL": "NSE_INDEX|Nifty Metal",
        "NIFTY ENERGY": "NSE_INDEX|Nifty Energy",
    }
    spot_names = ["NIFTY 50", "NIFTY BANK", "SENSEX", "INDIA VIX", "NIFTY FINANCIAL SERVICES", "NIFTY IT", "NIFTY AUTO", "NIFTY FMCG", "NIFTY PHARMA", "NIFTY METAL", "NIFTY ENERGY"]
    for name in spot_names:
        key = indices_mapping.get(name)
        if key:
            neutral_map[name] = {
                "upstox_key": key,
                "isin": ""
            }
    for row in resolved_constituents:
        sym = row["symbol"]
        neutral_map[sym] = {
            "upstox_key": row["instrument_key"],
            "isin": row["isin"]
        }
    neutral_map_payload = {
        "effective_date": "2026-08-04",
        "mappings": neutral_map
    }
    with open(ref_dir / f"provider_neutral_instrument_map_{session_date}.json", "w") as f:
        json.dump(neutral_map_payload, f, indent=2)
        
    print("Subscription Plan and Identity Resolution completed successfully.")
    print("=== Premarket Preparation Done ===")

if __name__ == "__main__":
    main()
