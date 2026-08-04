import time
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
from datetime import datetime, timezone
import logging

import config.config as cfg
from core.tick_store import insert_tick, init_ticks
from core.depth_store import depth_store

logger = logging.getLogger("replay_adapter")

class ReplayAdapter:
    def __init__(self, run_dir: Path, replay_db_path: Path, mode: str = "MAX_SPEED"):
        self.run_dir = run_dir
        self.replay_db_path = replay_db_path
        self.mode = mode  # MAX_SPEED, RAW_FAITHFUL, ACCELERATED

        self.df = None
        self.original_db_path = None

    def load_data(self):
        normalized_dir = self.run_dir / "normalized"
        if not normalized_dir.exists():
            raise FileNotFoundError(f"Normalized directory does not exist at {normalized_dir}")

        parquet_files = list(normalized_dir.glob("**/*.parquet"))
        if not parquet_files:
            raise FileNotFoundError(f"No normalized parquet files found in {normalized_dir}")

        logger.info(f"Loading {len(parquet_files)} parquet files from {normalized_dir}...")
        tables = [pq.read_table(f, partitioning=None) for f in parquet_files]
        self.df = pd.concat([t.to_pandas() for t in tables], ignore_index=True)
        
        # Build token mapping from complete.json
        import json
        master_path = Path("/Users/madhuram/tradebot-upstox-replay-quality-capture-v1/runtime/upstox_instruments/complete.json")
        key_to_token = {}
        if master_path.exists():
            logger.info(f"Loading BOD master from {master_path} for token resolution...")
            with open(master_path) as f:
                master = json.load(f)
                for item in master:
                    ikey = item.get("instrument_key")
                    etoken = item.get("exchange_token")
                    if ikey and etoken and etoken.isdigit():
                        key_to_token[ikey] = int(etoken)
        self.key_to_token = key_to_token

        # Sort deterministically
        # Primary: receive_wall_ts_utc (represented as float or string)
        # Secondary: source_exchange_ts when valid
        # Tertiary: connection_id
        # Quaternary: local_sequence
        self.df['sort_ts'] = pd.to_datetime(self.df['receive_wall_ts_utc'], format='ISO8601').astype('int64')
        self.df['source_ts'] = self.df['source_exchange_ts'].fillna(0).astype('int64')
        
        self.df.sort_values(
            by=['sort_ts', 'source_ts', 'connection_id', 'local_sequence'],
            ascending=[True, True, True, True],
            inplace=True
        )
        logger.info(f"Loaded and sorted {len(self.df)} records for replay.")

    def run(self):
        if self.df is None:
            self.load_data()

        # Redirect tick/depth DB writes to replay DB
        self.original_db_path = getattr(cfg, "TRADE_DB_PATH", None)
        cfg.TRADE_DB_PATH = str(self.replay_db_path)
        logger.info(f"Redirecting DB writes to replay database: {self.replay_db_path}")

        # Initialize tables in replay DB
        init_ticks()

        last_record_time = None
        start_time = time.time()

        for idx, row in self.df.iterrows():
            # Handle speed controls
            current_time = row['sort_ts'] / 1e9  # nanoseconds to seconds
            if last_record_time is not None:
                gap = current_time - last_record_time
                if gap > 0:
                    if self.mode == "RAW_FAITHFUL":
                        time.sleep(gap)
                    elif self.mode == "ACCELERATED":
                        time.sleep(min(gap, 0.01))  # Compress idle gap to max 10ms

            last_record_time = current_time

            # Parse common fields
            ikey = row['instrument_key']
            token = self.key_to_token.get(ikey)
            if token is None:
                token_str = row['exchange_token']
                if not token_str or pd.isna(token_str):
                    continue
                try:
                    token = int(token_str)
                except ValueError:
                    continue

            # Check if this is a tick update
            ltp = row['ltp']
            volume = row['volume']
            oi = row['open_interest']
            
            # Determine source timestamp epoch
            source_exchange_ts = row['source_exchange_ts']
            if pd.notna(source_exchange_ts) and source_exchange_ts > 0:
                ts_epoch = float(source_exchange_ts) / 1000.0
            else:
                ts_epoch = current_time

            if pd.notna(ltp):
                insert_tick(
                    ts_epoch=ts_epoch,
                    instrument_token=token,
                    last_price=float(ltp),
                    volume=int(volume) if pd.notna(volume) else 0,
                    oi=int(oi) if pd.notna(oi) else 0
                )

            # Check if this has depth L2 info
            has_depth = False
            depth = {"buy": [], "sell": []}
            for i in range(1, 6):
                bp = row[f'bid_price_{i}']
                bq = row[f'bid_quantity_{i}']
                if pd.notna(bp) and pd.notna(bq):
                    depth["buy"].append({"price": float(bp), "quantity": int(bq), "orders": 0})
                    has_depth = True

                ap = row[f'ask_price_{i}']
                aq = row[f'ask_quantity_{i}']
                if pd.notna(ap) and pd.notna(aq):
                    depth["sell"].append({"price": float(ap), "quantity": int(aq), "orders": 0})
                    has_depth = True

            if has_depth:
                # Update memory cache and write to DB
                depth_store.update(token, depth)

        duration = time.time() - start_time
        logger.info(f"Replay completed. Processed {len(self.df)} events in {duration:.2f}s.")
        
        # Restore configuration
        if self.original_db_path:
            cfg.TRADE_DB_PATH = self.original_db_path
