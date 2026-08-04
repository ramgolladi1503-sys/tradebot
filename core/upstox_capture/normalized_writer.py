import os
import time
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timezone
import logging

from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA

logger = logging.getLogger("normalized_writer")

class NormalizedWriter:
    def __init__(self, output_dir: Path, run_id: str, flush_interval_secs: int = 60, max_buffer_size: int = 5000):
        self.output_dir = output_dir
        self.run_id = run_id
        self.flush_interval_secs = flush_interval_secs
        self.max_buffer_size = max_buffer_size

        self.buffers = {}  # partition_key -> list of records
        self.last_flush_time = time.time()

    def _get_partition_info(self, record: dict) -> tuple[str, str, str, str, str]:
        # Extract trade_date, provider, asset_class, instrument_family, hour
        ts_str = record.get('receive_wall_ts_utc') or datetime.now(timezone.utc).isoformat()
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)

        trade_date = dt.strftime("%Y-%m-%d")
        provider = record.get('provider') or 'upstox'
        
        # Derive asset_class
        inst_type = record.get('instrument_type') or ''
        segment = record.get('segment') or ''
        key = record.get('instrument_key') or ''
        
        if inst_type == "INDEX" or "NSE_INDEX" in key or "BSE_INDEX" in key or "INDEX" in segment:
            asset_class = "index"
        elif inst_type == "EQ" or "NSE_EQ" in key or "BSE_EQ" in key or "EQ" in segment:
            asset_class = "equity"
        elif inst_type == "FUT" or "FUT" in segment:
            asset_class = "future"
        elif inst_type in ["CE", "PE"] or "OPT" in segment:
            asset_class = "option"
        else:
            if "INDEX" in key or "Nifty" in key or "SENSEX" in key or "VIX" in key:
                asset_class = "index"
            else:
                asset_class = "equity"
        
        # Derive instrument_family
        underlying = record.get('underlying_symbol') or ''
        symbol = record.get('tradingsymbol') or ''

        if "NIFTY BANK" in symbol or "BANKNIFTY" in symbol or "BANKNIFTY" in underlying or "Nifty Bank" in key:
            family = "BANKNIFTY"
        elif "NIFTY" in symbol or "NIFTY" in underlying or "Nifty 50" in key:
            family = "NIFTY"
        elif "SENSEX" in symbol or "SENSEX" in underlying or "SENSEX" in key:
            family = "SENSEX"
        elif "VIX" in symbol or "VIX" in underlying or "VIX" in key:
            family = "INDIA_VIX"
        else:
            family = "OTHER"

        hour = dt.strftime("%H")
        return trade_date, provider, asset_class, family, hour

    def write_record(self, record: dict):
        partition_info = self._get_partition_info(record)
        partition_key = "/".join([
            f"asset_class={partition_info[2]}",
            f"trade_date={partition_info[0]}",
            f"provider={partition_info[1]}",
            f"instrument_family={partition_info[3]}",
            f"hour={partition_info[4]}"
        ])

        if partition_key not in self.buffers:
            self.buffers[partition_key] = []

        self.buffers[partition_key].append(record)

        # Trigger partition flush if buffer is full
        if len(self.buffers[partition_key]) >= self.max_buffer_size:
            self.flush_partition(partition_key)

    def flush_partition(self, partition_key: str):
        records = self.buffers.get(partition_key)
        if not records:
            return

        self.buffers[partition_key] = []

        partition_dir = self.output_dir / "normalized" / partition_key
        partition_dir.mkdir(parents=True, exist_ok=True)
        
        # Write to a parquet file specific to this run_id to avoid name collisions
        pq_path = partition_dir / f"ticks_{self.run_id}.parquet"

        df = pd.DataFrame(records)
        # Ensure all columns in schema are present
        for col_name in NORMALIZED_TICK_SCHEMA.names:
            if col_name not in df.columns:
                df[col_name] = None

        # Reorder and coerce to match Schema exactly
        df = df[NORMALIZED_TICK_SCHEMA.names]
        
        # Coerce types
        for field in NORMALIZED_TICK_SCHEMA:
            col = field.name
            t = field.type
            if pa.types.is_floating(t):
                df[col] = pd.to_numeric(df[col], errors='coerce').astype(float)
            elif pa.types.is_integer(t):
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                # If field was null, map 0 to None if nullable? Actually, let's keep integer as float/Int64 if we want nulls
                # But PyArrow allows nullable integers. In pandas, we can use 'Int64' type for nullable integers
                df[col] = df[col].astype('Int64')
            elif pa.types.is_string(t):
                df[col] = df[col].astype(str).replace('None', None).replace('<NA>', None)

        arrays = []
        for name in NORMALIZED_TICK_SCHEMA.names:
            field_type = NORMALIZED_TICK_SCHEMA.field(name).type
            arrays.append(pa.array(df[name], type=field_type))
        table = pa.Table.from_arrays(arrays, schema=NORMALIZED_TICK_SCHEMA)
        
        # Append or write
        # Note: PyArrow does not natively append to an existing parquet file easily.
        # So we check if file exists, read it, concat, and rewrite, OR write to a new file index
        # Since each run_id has its own file, we can write a sequence index or read-concat-write
        if pq_path.exists():
            try:
                existing_table = pq.read_table(pq_path, partitioning=None)
                table = pa.concat_tables([existing_table, table])
            except Exception as e:
                logger.error(f"Failed to concat with existing parquet file {pq_path}: {e}")

        pq.write_table(table, pq_path, compression='snappy')

    def flush_all(self):
        for partition_key in list(self.buffers.keys()):
            self.flush_partition(partition_key)
        self.last_flush_time = time.time()

    def check_periodic_flush(self):
        if time.time() - self.last_flush_time >= self.flush_interval_secs:
            self.flush_all()
