import json
import threading
from pathlib import Path
from datetime import datetime, timezone

class LifecycleLedger:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.output_dir / "session_lifecycle.jsonl"
        self.lock = threading.Lock()

    def _write_event(self, event_type: str, payload: dict):
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event_type": event_type,
            **payload
        }
        with self.lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

    def log_connection_event(self, status: str, details: str = "", reconnect_gen: int = 0):
        self._write_event("CONNECTION_LIFECYCLE", {
            "status": status,
            "details": details,
            "reconnect_generation": reconnect_gen
        })

    def log_subscription_event(self, instrument_key: str, mode: str, action: str, guid: str = "", reason: str = ""):
        self._write_event("SUBSCRIPTION_LIFECYCLE", {
            "instrument_key": instrument_key,
            "mode": mode,
            "action": action,
            "guid": guid,
            "reason": reason
        })
