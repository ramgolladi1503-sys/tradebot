import json
import hashlib
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from config import config as cfg
from core.time_utils import now_utc_epoch, now_ist


AUDIT_LOG = Path(getattr(cfg, "AUDIT_LOG_PATH", "logs/audit_log.jsonl"))
GENESIS = "GENESIS"


def _canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _read_last_hash() -> str:
    if not AUDIT_LOG.exists():
        return GENESIS
    try:
        with AUDIT_LOG.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return GENESIS
            offset = min(size, 16384)
            f.seek(-offset, 2)
            lines = f.read().splitlines()
            for raw in reversed(lines):
                if not raw:
                    continue
                try:
                    evt = json.loads(raw.decode("utf-8"))
                except Exception:
                    continue
                if evt.get("event_hash"):
                    return evt["event_hash"]
            return GENESIS
    except Exception:
        return GENESIS


def _compute_hash(event: Dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def append_event(event: Dict[str, Any]) -> str:
    AUDIT_LOG.parent.mkdir(exist_ok=True)
    event.setdefault("ts_epoch", now_utc_epoch())
    event.setdefault("ts_ist", now_ist().isoformat())
    event.setdefault("desk_id", getattr(cfg, "DESK_ID", "DEFAULT"))
    prev = _read_last_hash()
    event["prev_hash"] = prev
    event["event_hash"] = _compute_hash(event)
    with AUDIT_LOG.open("a") as f:
        f.write(_canonical_json(event) + "\n")
    return event["event_hash"]


def verify_chain(path: Path = AUDIT_LOG) -> Tuple[bool, str, int]:
    if not path.exists():
        return False, "missing_log", 0
    prev = GENESIS
    count = 0
    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                return False, "invalid_json", count
            if "prev_hash" not in event or "event_hash" not in event:
                return False, "missing_hash_fields", count
            if event["prev_hash"] != prev:
                return False, "prev_hash_mismatch", count
            if _compute_hash(event) != event["event_hash"]:
                return False, "event_hash_mismatch", count
            prev = event["event_hash"]
            count += 1
    return True, prev, count


def export_audit_bundle(out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts_epoch": time.time(),
        "audit_log": AUDIT_LOG.read_text() if AUDIT_LOG.exists() else "",
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path
