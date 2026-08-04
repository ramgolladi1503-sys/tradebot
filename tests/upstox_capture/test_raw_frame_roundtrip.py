import struct
import zstandard as zstd
from pathlib import Path
import pytest
import pyarrow.parquet as pq
from core.upstox_capture.raw_writer import RawWriter

def test_raw_frame_roundtrip(tmp_path):
    connection_id = "test_conn"
    writer = RawWriter(tmp_path, connection_id=connection_id)

    # 1. Write dummy binary frames
    frame1 = b"\x00\x01\x02\x03hello"
    frame2 = b"world\xff\xfe\xfd"

    writer.write_frame(frame1, message_class="FeedResponse", decode_success=True)
    writer.write_frame(frame2, message_class="FeedResponse", decode_success=True)
    writer.close()

    # 2. Verify parquet index is written
    index_file = tmp_path / "raw" / connection_id / "frames_000001.index.parquet"
    bin_file = tmp_path / "raw" / connection_id / "frames_000001.bin.zst"

    assert index_file.exists()
    assert bin_file.exists()

    table = pq.read_table(index_file)
    df = table.to_pandas()
    assert len(df) == 2
    assert df.loc[0, 'raw_byte_length'] == len(frame1)
    assert df.loc[1, 'raw_byte_length'] == len(frame2)

    # 3. Decompress and read length-prefixed bytes back
    records = []
    with open(bin_file, "rb") as fh:
        dctx = zstd.ZstdDecompressor()
        with dctx.stream_reader(fh) as reader:
            while True:
                len_bytes = reader.read(4)
                if not len_bytes:
                    break
                length = struct.unpack(">I", len_bytes)[0]
                payload = reader.read(length)
                records.append(payload)

    assert len(records) == 2
    assert records[0] == frame1
    assert records[1] == frame2
