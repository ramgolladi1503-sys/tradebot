#!/usr/bin/env python3
import sys
import json
import hashlib
from pathlib import Path
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent.parent))

from core.market_event_graph_constituent_source import (
    DEFAULT_MANIFEST_PATH,
    resolve_constituent_tokens,
    _build_completed_return_row,
)
from core.market_event_graph_tick_reader import read_last_ticks_by_minute
from core.market_event_graph_breadth_producer import (
    produce_completed_constituent_breadth_snapshots,
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
)

def main():
    db_path = Path("runtime/market_data/upstox/20260804/full_day_replay_v1/replay_verification.db")
    if not db_path.exists():
        print(f"Error: Replay database does not exist at {db_path}", file=sys.stderr)
        sys.exit(1)

    # 1. Load manifest and calculate hash
    manifest_bytes = DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8")
    manifest = json.loads(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes.encode("utf-8")).hexdigest()
    print(f"Loaded Nifty 50 manifest. SHA256: {manifest_sha}")

    # 2. Load complete instrument list to resolve tokens
    master_path = Path("runtime/upstox_instruments/complete.json")
    if not master_path.exists():
        print(f"Error: complete.json master does not exist at {master_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(master_path) as f:
        instrument_rows = json.load(f)
    
    # 3. Resolve tokens
    normalized_rows = []
    for item in instrument_rows:
        ts = item.get("trading_symbol")
        if item.get("segment") == "NSE_INDEX" and ts == "NIFTY":
            ts = "NIFTY 50"
        normalized_rows.append({
            "exchange": item.get("exchange"),
            "tradingsymbol": ts,
            "instrument_type": item.get("instrument_type"),
            "instrument_token": item.get("exchange_token"),
        })

    resolution = resolve_constituent_tokens(manifest, normalized_rows)
    if resolution["status"] != "READY":
        print(f"Error: Token resolution failed: {resolution['reason']}", file=sys.stderr)
        sys.exit(1)
    
    constituent_tokens = resolution["constituent_tokens"]
    index_token = resolution["index_token"]
    print(f"Resolved index token: {index_token}, and {len(constituent_tokens)} constituent tokens.")

    # 4. Generate minute end boundaries (09:31:00 to 15:30:00 IST)
    # 09:30:00 IST = 1785816000
    # 09:31:00 IST = 1785816060
    # 15:30:00 IST = 1785837600
    start_boundary = 1785816060
    end_boundary = 1785837600
    minute_ends = list(range(start_boundary, end_boundary + 60, 60))
    all_query_ends = [start_boundary - 60] + minute_ends
    all_tokens = sorted({int(index_token), *[int(t) for t in constituent_tokens.values()]})

    print(f"Querying ticks from SQLite DB for {len(minute_ends)} minute intervals...")
    ticks_by_minute = read_last_ticks_by_minute(
        tokens=all_tokens,
        minute_end_epochs=all_query_ends,
        db_path=db_path,
    )
    print(f"Loaded tick updates for {len(ticks_by_minute)} distinct minute markers.")

    # 5. Build completed constituent bars
    bars = []
    skipped_count = 0
    for minute_end in minute_ends:
        row, debug_info = _build_completed_return_row(
            minute_end=minute_end,
            session_date="2026-08-04",
            index_token=index_token,
            constituent_tokens=constituent_tokens,
            ticks_by_minute=ticks_by_minute,
            manifest_sha256=manifest_sha,
        )
        if row is not None:
            bars.append(row)
        else:
            skipped_count += 1
            if skipped_count <= 5:
                print(f"Skipped minute boundary {minute_end}: {debug_info}")
    
    print(f"Generated {len(bars)} completed constituent return bars (skipped {skipped_count} boundaries).")

    # 6. Save completed bars to Parquet format
    meg_dir = Path("meg")
    meg_dir.mkdir(exist_ok=True)
    parquet_path = meg_dir / "nifty50_constituent_bars_1m.parquet"
    
    # Flatten dicts for DataFrame conversion
    # Exclude constituent_ret1_by_symbol from parquet storage for schema simplicity
    df_bars = []
    for b in bars:
        b_copy = dict(b)
        if "constituent_ret1_by_symbol" in b_copy:
            del b_copy["constituent_ret1_by_symbol"]
        df_bars.append(b_copy)
    
    df = pd.DataFrame(df_bars)
    df.to_parquet(parquet_path, index=False)
    print(f"Persisted completed constituent bars to {parquet_path}")

    # 7. Run shadow event breadth producer
    metadata = {
        **frozen_threshold_metadata(),
        "market_event_graph_runtime_state": initial_market_event_graph_runtime_state("2026-08-04"),
        "completed_constituent_bars": bars,
    }
    
    events = produce_completed_constituent_breadth_snapshots(metadata)
    print(f"Shadow Breadth Producer evaluated. Generated {len(events)} graph event entries.")

    # 8. Save shadow graph events to JSON evidence
    evidence_path = meg_dir / "meg_replay_evidence_20260804.json"
    with open(evidence_path, "w") as f:
        json.dump(events, f, indent=2)
    print(f"Saved MEG shadow events to {evidence_path}")

if __name__ == "__main__":
    main()
