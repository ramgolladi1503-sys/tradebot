"""Unit tests verifying tick data collector parquet finalization contract."""

import tempfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq


def test_parquet_writer_finalization_footer_magic_bytes():
    schema = pa.schema([
        ("ts", pa.float64()),
        ("token", pa.int64()),
        ("symbol", pa.string()),
        ("ltp", pa.float64()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("vol", pa.int64()),
    ])

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_ticks.parquet"
        writer = pq.ParquetWriter(test_file, schema)

        sample_data = {
            "ts": [1790760000.0, 1790760001.0],
            "token": [256265, 260105],
            "symbol": ["NIFTY 50", "NIFTY BANK"],
            "ltp": [25800.0, 54100.0],
            "bid": [25799.0, 54098.0],
            "ask": [25801.0, 54102.0],
            "vol": [1000, 2000],
        }
        table = pa.Table.from_pydict(sample_data, schema=schema)
        writer.write_table(table)
        writer.close()

        assert test_file.exists()
        assert test_file.stat().st_size >= 4
        with open(test_file, "rb") as f:
            f.seek(-4, 2)
            magic = f.read(4)
        assert magic == b"PAR1", f"Expected b'PAR1', found {magic!r}"

        # Ensure PyArrow Parquet reader reads without corruption
        read_back = pq.read_table(test_file)
        assert read_back.num_rows == 2
        assert read_back.column_names == ["ts", "token", "symbol", "ltp", "bid", "ask", "vol"]
