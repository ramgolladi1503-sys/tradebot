import sqlite3
import pytest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA
from core.upstox_capture.replay_adapter import ReplayAdapter

@pytest.fixture
def mock_normalized_dataset(tmp_path):
    run_dir = tmp_path / "run_123"
    pq_dir = run_dir / "normalized" / "trade_date=2026-08-03" / "provider=upstox" / "segment=NSE_FO" / "instrument_family=NIFTY" / "hour=09"
    pq_dir.mkdir(parents=True, exist_ok=True)

    records = [
        {
            "schema_version": "1.0",
            "capture_run_id": "run_123",
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
            "receive_wall_ts_utc": "2026-08-03T09:15:00.000Z",
            "receive_monotonic_ns": 1000000000,
            "local_sequence": 1
        },
        {
            "schema_version": "1.0",
            "capture_run_id": "run_123",
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
            "receive_wall_ts_utc": "2026-08-03T09:15:05.000Z",
            "receive_monotonic_ns": 6000000000,
            "local_sequence": 2
        }
    ]

    df = pd.DataFrame(records)
    for col_name in NORMALIZED_TICK_SCHEMA.names:
        if col_name not in df.columns:
            df[col_name] = None
    df = df[NORMALIZED_TICK_SCHEMA.names]

    table = pa.Table.from_pandas(df, schema=NORMALIZED_TICK_SCHEMA)
    pq.write_table(table, pq_dir / "ticks_123.parquet", compression='snappy')
    return run_dir

def test_replay_determinism(mock_normalized_dataset, tmp_path):
    db1 = tmp_path / "replay1.db"
    db2 = tmp_path / "replay2.db"

    # Run replay 1
    adapter1 = ReplayAdapter(mock_normalized_dataset, db1, mode="MAX_SPEED")
    adapter1.run()

    # Run replay 2
    adapter2 = ReplayAdapter(mock_normalized_dataset, db2, mode="MAX_SPEED")
    adapter2.run()

    # Verify db counts match and are identical
    conn1 = sqlite3.connect(db1)
    conn2 = sqlite3.connect(db2)

    df1_ticks = pd.read_sql_query("SELECT * FROM ticks ORDER BY timestamp_epoch", conn1)
    df2_ticks = pd.read_sql_query("SELECT * FROM ticks ORDER BY timestamp_epoch", conn2)

    assert len(df1_ticks) == 2
    assert len(df2_ticks) == 2
    assert df1_ticks.equals(df2_ticks)

    conn1.close()
    conn2.close()
