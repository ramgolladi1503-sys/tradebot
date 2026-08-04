import os
import time
import hashlib
import struct
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard as zstd
from datetime import datetime, timezone
import logging

from core.upstox_capture.schemas import RAW_INDEX_SCHEMA

logger = logging.getLogger("raw_writer")

class RawWriter:
    def __init__(self, output_dir: Path, connection_id: str, max_chunk_size_bytes: int = 10 * 1024 * 1024):
        self.output_dir = output_dir / "raw" / connection_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.connection_id = connection_id
        self.max_chunk_size_bytes = max_chunk_size_bytes

        self.chunk_index = 1
        self.frame_sequence = 1
        self.current_bin_file = None
        self.current_zstd_writer = None
        self.current_bytes_written = 0
        self.index_records = []

        self._init_chunk()

    def _init_chunk(self):
        self.current_chunk_id = f"frames_{self.chunk_index:06d}"
        self.bin_path = self.output_dir / f"{self.current_chunk_id}.bin.zst"
        self.current_bin_file = open(self.bin_path, "wb")
        cctx = zstd.ZstdCompressor()
        self.current_zstd_writer = cctx.stream_writer(self.current_bin_file)
        self.current_bytes_written = 0
        self.index_records.clear()
        logger.info(f"Initialized new raw chunk {self.current_chunk_id} at {self.bin_path}")

    def write_frame(self, raw_bytes: bytes, message_class: str, decode_success: bool):
        # 1. Calculate fields
        byte_length = len(raw_bytes)
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        receive_monotonic = time.monotonic_ns()
        receive_wall_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # 2. Write length-prefixed record to zstd writer
        # We write length as 4-byte unsigned integer (big-endian)
        length_header = struct.pack(">I", byte_length)
        self.current_zstd_writer.write(length_header)
        self.current_zstd_writer.write(raw_bytes)

        self.current_bytes_written += 4 + byte_length

        # 3. Save index record
        self.index_records.append({
            'provider': 'upstox',
            'feed_version': 'v3',
            'connection_id': self.connection_id,
            'frame_sequence': self.frame_sequence,
            'receive_monotonic_ns': receive_monotonic,
            'receive_wall_ts_utc': receive_wall_utc,
            'raw_byte_length': byte_length,
            'checksum_sha256': checksum,
            'message_class': message_class,
            'decode_status': 'success' if decode_success else 'failed',
            'output_chunk_id': self.current_chunk_id
        })

        self.frame_sequence += 1

        # 4. Check for rotation
        if self.current_bytes_written >= self.max_chunk_size_bytes:
            self.rotate()

    def rotate(self):
        self.flush()
        self.chunk_index += 1
        self._init_chunk()

    def flush(self):
        if self.current_zstd_writer:
            self.current_zstd_writer.flush()
        if self.current_bin_file:
            self.current_bin_file.flush()

        if self.index_records:
            index_path = self.output_dir / f"{self.current_chunk_id}.index.parquet"
            df = pd.DataFrame(self.index_records)
            table = pa.Table.from_pandas(df, schema=RAW_INDEX_SCHEMA)
            pq.write_table(table, index_path, compression='snappy')
            logger.info(f"Flushed index of {len(self.index_records)} frames to {index_path}")

    def close(self):
        self.flush()
        if self.current_zstd_writer:
            try:
                self.current_zstd_writer.close()
            except Exception:
                pass
        if self.current_bin_file:
            try:
                self.current_bin_file.close()
            except Exception:
                pass
        logger.info(f"Closed RawWriter for connection {self.connection_id}")
