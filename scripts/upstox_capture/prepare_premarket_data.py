#!/usr/bin/env python3
"""Premarket Data Preparation Script for Upstox V3 MEG Capture.

Prepares instrument masters, resolves constituent identities, plans subscription universes,
and generates dated reference metadata.

DISCLAIMERS:
- NO_STRUCTURAL_EDGE_CLAIM: Does not claim any structural trading edge.
- NO_PROFITABILITY_CLAIM: No profitability is implied or guaranteed.
- NOT_A_KITE_LIVE_CERTIFICATION: Not a Zerodha Kite live trading certification.
"""

import sys
import os
import json
import gzip
import shutil
import hashlib
import urllib.request
import logging
import csv
import argparse
import subprocess
from datetime import datetime, timezone, date
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

from core.upstox_capture.subscription_planner import (
    build_subscription_plan,
    load_instrument_master,
    NIFTY_50_CONSTITUENTS
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("prepare_premarket_data")

UPSTOX_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

def calculate_sha256(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()

def get_producer_commit() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "unknown"

def fetch_approved_nifty_spot() -> float:
    token = os.environ.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("No explicit --nifty-spot provided and UPSTOX_ACCESS_TOKEN is missing in environment")

    url = "https://api.upstox.com/v2/market-quote/quotes?instrument_key=NSE_INDEX%7CNifty%2050"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                d = data.get("data", {}).get("NSE_INDEX:Nifty 50", {})
                last_price = d.get("last_price")
                if last_price and float(last_price) > 0:
                    return float(last_price)
    except Exception as e:
        logger.error(f"Failed to fetch live premarket quote: {e}")

    raise RuntimeError("Failed to retrieve approved premarket quote for NIFTY spot price")

def parse_args():
    parser = argparse.ArgumentParser(description="Premarket Data Preparation for Upstox V3 MEG Capture")
    parser.add_argument("--session-date", help="Session date in YYYYMMDD format")
    parser.add_argument("--nifty-spot", type=float, help="NIFTY 50 spot price")
    parser.add_argument("--weights-file", type=Path, help="Path to official constituent weights CSV/JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run validation")
    return parser.parse_args()

def main():
    args = parse_args()
    print("=== Phase A & B: Premarket Truth, Identity, and Subscription Planning ===")

    # 1. Resolve Session Date
    if args.session_date:
        session_date = args.session_date
    else:
        session_date = datetime.now(timezone.utc).strftime("%Y%m%d")

    # 2. Resolve NIFTY Spot Price with strict precedence
    spot_price_timestamp = datetime.now(timezone.utc).isoformat()
    if args.nifty_spot is not None:
        nifty_spot = args.nifty_spot
        spot_price_source = "CLI_INPUT"
    else:
        try:
            nifty_spot = fetch_approved_nifty_spot()
            spot_price_source = "UPSTOX_API_QUOTE"
        except Exception as e:
            print(f"ERROR: NIFTY spot price resolution failed: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"Session Date: {session_date}")
    print(f"NIFTY Spot Price: {nifty_spot} (Source: {spot_price_source})")

    worktree_root = Path(__file__).resolve().parents[2]
    evidence_root = worktree_root / "runtime" / "market_data" / "upstox" / session_date / "full_day_replay_v1"
    
    master_dest_dir = evidence_root / "upstox_instruments"
    constituents_dest_dir = evidence_root / "constituents"
    subscription_dest_dir = evidence_root / "subscription"
    ref_dir = evidence_root / "reference"

    for d in [master_dest_dir, constituents_dest_dir, subscription_dest_dir, ref_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Copy/Download Master
    master_src_gz = Path("/Users/madhuram/tradebot-upstox-replay-quality-capture-v1/runtime/upstox_instruments/complete.json.gz")
    master_src_json = Path("/Users/madhuram/tradebot-upstox-replay-quality-capture-v1/runtime/upstox_instruments/complete.json")

    dest_gz = master_dest_dir / "complete.json.gz"
    dest_json = master_dest_dir / "complete.json"

    if master_src_gz.exists() and master_src_json.exists():
        shutil.copy2(master_src_gz, dest_gz)
        shutil.copy2(master_src_json, dest_json)
    else:
        logger.info(f"Downloading master from {UPSTOX_MASTER_URL}...")
        urllib.request.urlretrieve(UPSTOX_MASTER_URL, dest_gz)
        with gzip.open(dest_gz, "rb") as f_in:
            with open(dest_json, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

    compressed_sha = calculate_sha256(dest_gz)
    decompressed_sha = calculate_sha256(dest_json)
    instruments = load_instrument_master(dest_json)

    # Resolve Constituents
    print("A3: Resolving NIFTY 50 Constituents...")
    resolved_constituents = []
    identity_map = {}
    for symbol in NIFTY_50_CONSTITUENTS:
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
        inst = matches[0]
        resolved_constituents.append({
            "symbol": symbol,
            "company_name": inst.get("name"),
            "isin": inst.get("isin"),
            "instrument_key": inst.get("instrument_key"),
            "exchange_token": inst.get("exchange_token")
        })
        identity_map[symbol] = inst.get("instrument_key")

    with open(constituents_dest_dir / f"nifty50_constituents_{session_date}.json", "w") as f:
        json.dump(resolved_constituents, f, indent=2)

    # Build Subscription Plan
    print("Phase B: Building Subscription Plan...")
    ref_date_obj = datetime.strptime(session_date, "%Y%m%d").date()
    try:
        plan, budget_report = build_subscription_plan(
            dest_json, subscription_dest_dir, nifty_spot, reference_date=ref_date_obj, restrict_universe=True
        )
    except Exception as e:
        print(f"ERROR: Subscription planning failed: {e}", file=sys.stderr)
        sys.exit(1)

    universe_plan_path = subscription_dest_dir / "universe_plan.json"
    universe_sha = calculate_sha256(universe_plan_path)

    # Process Index Weights (Official vs Equal Weights)
    official_weights_available = False
    weights_dict = {}
    weight_provenance = {}

    if args.weights_file and args.weights_file.exists():
        logger.info(f"Loading official weights from {args.weights_file}...")
        try:
            # Parse weights file
            with open(args.weights_file, "r") as f:
                if args.weights_file.suffix == ".json":
                    w_data = json.load(f)
                    raw_weights = w_data.get("weights", w_data)
                else:
                    reader = csv.reader(f)
                    raw_weights = {row[0].strip(): float(row[1].strip()) for row in reader if row}

            matched_count = sum(1 for sym in NIFTY_50_CONSTITUENTS if sym in raw_weights)
            weight_sum = sum(float(v) for k, v in raw_weights.items() if k in NIFTY_50_CONSTITUENTS)

            if matched_count == 50 and abs(weight_sum - 100.0) < 1.0:
                official_weights_available = True
                weights_dict = {sym: float(raw_weights[sym]) for sym in NIFTY_50_CONSTITUENTS}
                weight_provenance = {
                    "source": "OFFICIAL_FILE",
                    "source_path": str(args.weights_file),
                    "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                    "effective_date": session_date,
                    "raw_source_sha256": calculate_sha256(args.weights_file),
                    "constituent_count": 50,
                    "weight_sum": weight_sum,
                    "unresolved_symbols": 0,
                    "duplicates": 0
                }
            else:
                logger.warning(f"Weights file validation failed: matched={matched_count}, sum={weight_sum}")
        except Exception as e:
            logger.error(f"Failed to load weights file: {e}")

    if not official_weights_available:
        print("OFFICIAL_WEIGHT_REFERENCE_UNAVAILABLE: Defaulting to equal-weighted constituent model.")
        weights_dict = {sym: 2.0 for sym in NIFTY_50_CONSTITUENTS}
        weight_provenance = {
            "source": "OFFICIAL_WEIGHT_REFERENCE_UNAVAILABLE",
            "effective_date": session_date,
            "constituent_count": 50,
            "weight_sum": 100.0,
            "unresolved_symbols": 0,
            "duplicates": 0
        }

    # Reference Snapshots
    membership_payload = {
        "effective_date": session_date,
        "index_symbol": "NIFTY",
        "constituents": {
            row["symbol"]: {
                "company_name": row["company_name"],
                "sector": "EQ",
                "isin": row["isin"]
            } for row in resolved_constituents
        }
    }
    with open(ref_dir / f"nifty50_membership_{session_date}.json", "w") as f:
        json.dump(membership_payload, f, indent=2)

    weights_payload = {
        "effective_date": session_date,
        "index_symbol": "NIFTY",
        "official_weights_available": official_weights_available,
        "provenance": weight_provenance,
        "weights": weights_dict
    }
    with open(ref_dir / f"nifty50_weights_{session_date}.json", "w") as f:
        json.dump(weights_payload, f, indent=2)

    # Premarket Manifest
    premarket_manifest = {
        "session_date": session_date,
        "spot_price": nifty_spot,
        "spot_price_source": spot_price_source,
        "spot_price_timestamp": spot_price_timestamp,
        "preparation_timestamp": datetime.now(timezone.utc).isoformat(),
        "producer_commit": get_producer_commit(),
        "instrument_master_sha256": decompressed_sha,
        "universe_sha256": universe_sha,
        "official_weights_available": official_weights_available,
        "surface_report": plan.get("surface_report"),
        "budget_report": budget_report
    }

    with open(subscription_dest_dir / "premarket_manifest.json", "w") as f:
        json.dump(premarket_manifest, f, indent=2)

    s_rep = plan.get("surface_report", {})
    print("\n--- PREMARKET PREPARATION SUMMARY ---")
    print(f"Session Date: {session_date}")
    print(f"Spot Price & Source: {nifty_spot} ({spot_price_source})")
    print(f"Instrument Master Hash: {decompressed_sha[:12]}...")
    print(f"Constituents: {len(resolved_constituents)} / 50")
    print(f"Sector Indices: 8")
    print(f"NIFTY Futures: 2 (Front & Next)")
    print(f"Weekly Expiry: {s_rep.get('weekly_expiry')} (CE: {s_rep.get('weekly_ce_count')}, PE: {s_rep.get('weekly_pe_count')})")
    print(f"Monthly Expiry: {s_rep.get('monthly_expiry')} (CE: {s_rep.get('monthly_ce_count')}, PE: {s_rep.get('monthly_pe_count')})")
    print(f"Subscription Mode: FULL={budget_report.get('requested_full')}, LTPC={budget_report.get('requested_ltpc')}")
    print(f"Omissions: {len(budget_report.get('omitted_instruments', []))}")
    print(f"Budget Verdict: {budget_report.get('budget_verdict')}")
    print("=====================================\n")

if __name__ == "__main__":
    main()
