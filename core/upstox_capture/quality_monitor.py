import os
import json
import time
import shutil
import threading
from pathlib import Path
from datetime import datetime, timezone
import psutil

class QualityMonitor:
    def __init__(self, output_dir: Path, interval_secs: float = 10.0):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.output_dir / "quality_metrics.jsonl"
        self.interval_secs = interval_secs

        self.lock = threading.Lock()
        self.last_check_time = time.time()
        self.last_msg_count = 0
        self.last_byte_count = 0
        self.process = psutil.Process(os.getpid())

    def record_metrics(self, current_msg_count: int, current_byte_count: int, queue_depth: int, decode_latencies: list[float]):
        now = time.time()
        elapsed = now - self.last_check_time
        if elapsed < self.interval_secs:
            return

        with self.lock:
            # 1. Throughput calculations
            msg_delta = current_msg_count - self.last_msg_count
            byte_delta = current_byte_count - self.last_byte_count

            msgs_per_sec = msg_delta / elapsed if elapsed > 0 else 0.0
            bytes_per_sec = byte_delta / elapsed if elapsed > 0 else 0.0

            self.last_msg_count = current_msg_count
            self.last_byte_count = current_byte_count
            self.last_check_time = now

            # 2. Latency statistics
            avg_decode_latency_ms = (sum(decode_latencies) / len(decode_latencies) * 1000) if decode_latencies else 0.0

            # 3. System resource checks
            try:
                cpu_pct = self.process.cpu_percent()
                rss_mem_bytes = self.process.memory_info().rss
            except Exception:
                cpu_pct = 0.0
                rss_mem_bytes = 0

            try:
                total_disk, used_disk, free_disk = shutil.disk_usage(self.output_dir)
            except Exception:
                free_disk = 0

            # 4. Log the quality record
            record = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event_type": "QUALITY_MONITOR",
                "msgs_per_sec": msgs_per_sec,
                "bytes_per_sec": bytes_per_sec,
                "avg_decode_latency_ms": avg_decode_latency_ms,
                "queue_depth": queue_depth,
                "cpu_percent": cpu_pct,
                "rss_memory_bytes": rss_mem_bytes,
                "free_disk_space_bytes": free_disk
            }

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
