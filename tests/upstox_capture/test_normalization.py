from pathlib import Path
import pytest
import pyarrow.parquet as pq
from core.upstox_capture.normalized_writer import NormalizedWriter
from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA

def test_normalized_writer_partitioning(tmp_path):
    run_id = "test_run"
    writer = NormalizedWriter(tmp_path, run_id=run_id, flush_interval_secs=1, max_buffer_size=2)

    # 1. Write dummy normalized records
    record1 = {
        "schema_version": "1.0",
        "capture_run_id": run_id,
        "provider": "upstox",
        "feed_version": "v3",
        "connection_id": "conn_a",
        "segment": "NSE_FO",
        "instrument_key": "NSE_FO|50978",
        "tradingsymbol": "NIFTY 27000 CE 29 DEC 26",
        "exchange_token": "50978",
        "ltp": 24500.5,
        "volume": 1200,
        "open_interest": 45000,
        "receive_wall_ts_utc": "2026-08-03T09:15:00Z",
        "local_sequence": 1
    }

    record2 = {
        "schema_version": "1.0",
        "capture_run_id": run_id,
        "provider": "upstox",
        "feed_version": "v3",
        "connection_id": "conn_a",
        "segment": "NSE_FO",
        "instrument_key": "NSE_FO|50978",
        "tradingsymbol": "NIFTY 27000 CE 29 DEC 26",
        "exchange_token": "50978",
        "ltp": 24501.0,
        "volume": 1300,
        "open_interest": 45000,
        "receive_wall_ts_utc": "2026-08-03T09:15:05Z",
        "local_sequence": 2
    }

    writer.write_record(record1)
    writer.write_record(record2)  # Hits max_buffer_size and flushes partition

    # 2. Check that the partitioned parquet file is created
    # Partition path: trade_date=2026-08-03/provider=upstox/segment=NSE_FO/instrument_family=NIFTY/hour=09/ticks_test_run.parquet
    pq_dir = tmp_path / "normalized" / "trade_date=2026-08-03" / "provider=upstox" / "segment=NSE_FO" / "instrument_family=NIFTY" / "hour=09"
    pq_file = pq_dir / f"ticks_{run_id}.parquet"

    assert pq_file.exists()

    table = pq.read_table(pq_file, partitioning=None)
    assert len(table) == 2
    
    # Check schema matches NORMALIZED_TICK_SCHEMA
    assert table.schema.names == NORMALIZED_TICK_SCHEMA.names
