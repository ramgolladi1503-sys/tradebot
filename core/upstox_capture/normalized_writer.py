import os
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA

logger = logging.getLogger("normalized_writer")

class NormalizedWriter:
    def __init__(self, output_dir: Path, run_id: str, max_buffer_size: int = 1000, flush_interval_sec: float = 5.0):
        self.output_dir = output_dir
        self.run_id = run_id
        self.max_buffer_size = max_buffer_size
        self.flush_interval_sec = flush_interval_sec

        self.buffers: dict[str, list[dict]] = {}
        self.sequence_map: dict[str, int] = {}
        self.last_flush_time = time.time()

        self.accepted_rows_count = 0
        self.durable_rows_count = 0
        self.write_errors_count = 0

        self.manifest_path = self.output_dir / "normalized_chunk_manifest.jsonl"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        schema_bytes = str(NORMALIZED_TICK_SCHEMA).encode("utf-8")
        self.schema_sha256 = hashlib.sha256(schema_bytes).hexdigest()

    def _get_partition_info(self, record: dict) -> tuple[str, str, str, str, str]:
        ts_str = record.get('receive_wall_ts_utc') or datetime.now(timezone.utc).isoformat()
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)

        trade_date = dt.strftime("%Y-%m-%d")
        provider = record.get('provider') or 'upstox'

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
        self.accepted_rows_count += 1
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

        if len(self.buffers[partition_key]) >= self.max_buffer_size:
            self.flush_partition(partition_key)

    def check_periodic_flush(self):
        now = time.time()
        if now - self.last_flush_time >= self.flush_interval_sec:
            self.flush_all()
            self.last_flush_time = now

    def flush_partition(self, partition_key: str):
        records = self.buffers.get(partition_key, [])
        if not records:
            return

        self.buffers[partition_key] = []
        partition_dir = self.output_dir / "normalized" / partition_key
        partition_dir.mkdir(parents=True, exist_ok=True)

        seq = self.sequence_map.get(partition_key, 0) + 1
        self.sequence_map[partition_key] = seq

        tmp_path = partition_dir / f"ticks_{self.run_id}_{seq}.parquet.tmp"
        final_path = partition_dir / f"ticks_{self.run_id}_{seq}.parquet"

        try:
            df = pd.DataFrame(records)

            for field in NORMALIZED_TICK_SCHEMA:
                col = field.name
                if col not in df.columns:
                    df[col] = None
                t = field.type
                if pa.types.is_float64(t) or pa.types.is_float32(t):
                    df[col] = pd.to_numeric(df[col], errors='coerce').astype('float64')
                elif pa.types.is_integer(t):
                    # PRESERVE NULLS: Do not use fillna(0)
                    df[col] = pd.to_numeric(df[col], errors='coerce').round().astype('Int64')
                elif pa.types.is_string(t):
                    df[col] = df[col].astype(str).replace({'None': None, '<NA>': None, 'nan': None})

            df = df[NORMALIZED_TICK_SCHEMA.names]
            table = pa.Table.from_pandas(df, schema=NORMALIZED_TICK_SCHEMA)

            # Write to temporary file first
            pq.write_table(table, tmp_path, compression='snappy')

            # Fsync file
            try:
                fd = os.open(tmp_path, os.O_RDONLY)
                os.fsync(fd)
                os.close(fd)
            except Exception:
                pass

            # Atomic rename to final path
            os.replace(tmp_path, final_path)

            file_size = final_path.stat().st_size
            file_sha = hashlib.sha256(final_path.read_bytes()).hexdigest()

            first_src = records[0].get("source_exchange_ts")
            last_src = records[-1].get("source_exchange_ts")
            first_rec = records[0].get("receive_wall_ts_utc")
            last_rec = records[-1].get("receive_wall_ts_utc")

            rel_path = str(final_path.relative_to(self.output_dir))
            manifest_row = {
                "run_id": self.run_id,
                "partition": partition_key,
                "chunk_sequence": seq,
                "relative_path": rel_path,
                "row_count": len(records),
                "size_bytes": file_size,
                "sha256": file_sha,
                "first_source_timestamp": first_src,
                "last_source_timestamp": last_src,
                "first_receive_timestamp": first_rec,
                "last_receive_timestamp": last_rec,
                "schema_sha256": self.schema_sha256,
                "write_timestamp": datetime.now(timezone.utc).isoformat()
            }

            with open(self.manifest_path, "a") as f:
                f.write(json.dumps(manifest_row) + "\n")

            self.durable_rows_count += len(records)
            logger.debug(f"Flushed chunk {rel_path} with {len(records)} records.")

        except Exception as e:
            self.write_errors_count += 1
            logger.error(f"Failed to flush immutable chunk for {partition_key}: {e}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def flush_all(self):
        for partition_key in list(self.buffers.keys()):
            self.flush_partition(partition_key)

    def close(self):
        self.flush_all()

    def get_reconciliation_report(self) -> dict:
        pending_rows = sum(len(buf) for buf in self.buffers.values())
        return {
            "run_id": self.run_id,
            "accepted_rows": self.accepted_rows_count,
            "durable_rows": self.durable_rows_count,
            "pending_rows": pending_rows,
            "write_errors": self.write_errors_count,
            "reconciled": (self.accepted_rows_count == self.durable_rows_count + pending_rows)
        }
