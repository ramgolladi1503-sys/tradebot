import json
import os
import time
import hashlib
from pathlib import Path
from typing import Dict, Any

from config import config as cfg
from core.audit_log import append_event
from core.incidents import create_incident, SEV2
from core.time_utils import now_utc_epoch


FLAGS_PATH = Path(getattr(cfg, "FEATURE_FLAGS_PATH", "config/feature_flags.json"))
OVERRIDE_PATH = Path(getattr(cfg, "FEATURE_FLAGS_OVERRIDE_PATH", "logs/feature_flags_override.json"))
SNAPSHOT_PATH = Path(getattr(cfg, "FEATURE_FLAGS_SNAPSHOT_PATH", "logs/feature_flags_snapshot.json"))

_FLAGS_CACHE: Dict[str, Any] | None = None


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        print(f"[FLAGS_ERROR] read_failed path={path} err={exc}")
        return {}


def _env_overrides() -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    for key, val in os.environ.items():
        if key.startswith("FLAG_"):
            overrides[key[5:]] = val
    if "EXPERIMENT_ID" in os.environ:
        overrides["EXPERIMENT_ID"] = os.environ["EXPERIMENT_ID"]
    for key in [
        "CANARY_PERCENT",
        "CANARY_WINDOW_MIN",
        "CANARY_MIN_DECISIONS",
        "CANARY_HALT_RATE_THRESHOLD",
        "CANARY_ERROR_RATE_THRESHOLD",
        "CANARY_AUTO_ROLLBACK",
    ]:
        if key in os.environ:
            overrides[key] = os.environ[key]
    return overrides


def _coerce_flags(flags: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(flags)
    for key in ["CANARY_PERCENT", "CANARY_WINDOW_MIN", "CANARY_MIN_DECISIONS"]:
        if key in out:
            try:
                out[key] = int(out[key])
            except Exception:
                out[key] = int(getattr(cfg, key, 0))
    for key in ["CANARY_HALT_RATE_THRESHOLD", "CANARY_ERROR_RATE_THRESHOLD"]:
        if key in out:
            try:
                out[key] = float(out[key])
            except Exception:
                out[key] = float(getattr(cfg, key, 0.0))
    if "CANARY_AUTO_ROLLBACK" in out:
        val = out["CANARY_AUTO_ROLLBACK"]
        if isinstance(val, str):
            out["CANARY_AUTO_ROLLBACK"] = val.lower() == "true"
        else:
            out["CANARY_AUTO_ROLLBACK"] = bool(val)
    return out


def load_flags() -> Dict[str, Any]:
    base = {
        "CANARY_PERCENT": int(getattr(cfg, "CANARY_PERCENT", 0)),
        "CANARY_WINDOW_MIN": int(getattr(cfg, "CANARY_WINDOW_MIN", 30)),
        "CANARY_MIN_DECISIONS": int(getattr(cfg, "CANARY_MIN_DECISIONS", 20)),
        "CANARY_HALT_RATE_THRESHOLD": float(getattr(cfg, "CANARY_HALT_RATE_THRESHOLD", 0.05)),
        "CANARY_ERROR_RATE_THRESHOLD": float(getattr(cfg, "CANARY_ERROR_RATE_THRESHOLD", 0.03)),
        "CANARY_AUTO_ROLLBACK": bool(getattr(cfg, "CANARY_AUTO_ROLLBACK", True)),
    }
    if hasattr(cfg, "EXPERIMENT_ID"):
        base["EXPERIMENT_ID"] = getattr(cfg, "EXPERIMENT_ID")
    file_flags = _read_json(FLAGS_PATH)
    env_flags = _env_overrides()
    override_flags = _read_json(OVERRIDE_PATH)
    merged = {}
    merged.update(base)
    merged.update(file_flags)
    merged.update(env_flags)
    merged.update(override_flags)
    merged = _coerce_flags(merged)
    if merged.get("CANARY_PERCENT", 0) < 0:
        merged["CANARY_PERCENT"] = 0
    if merged.get("CANARY_PERCENT", 0) > 100:
        merged["CANARY_PERCENT"] = 100
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "ts_epoch": now_utc_epoch(),
        "flags": merged,
        "source": {
            "config": str(FLAGS_PATH),
            "override": str(OVERRIDE_PATH),
        },
    }
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2))
    append_event({"event": "FLAGS_SNAPSHOT", "flags": merged, "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})
    return merged


def init_flags() -> Dict[str, Any]:
    global _FLAGS_CACHE
    if _FLAGS_CACHE is None:
        _FLAGS_CACHE = load_flags()
    return _FLAGS_CACHE


def get_flags() -> Dict[str, Any]:
    return init_flags()


def _hash_trace(trace_id: str) -> int:
    digest = hashlib.sha256(trace_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def canary_allowed(trace_id: str, percent: int | None = None) -> bool:
    flags = get_flags()
    pct = int(percent if percent is not None else flags.get("CANARY_PERCENT", 0))
    if pct <= 0:
        return True
    if pct >= 100:
        return True
    if not trace_id:
        return False
    return _hash_trace(trace_id) < pct


def _read_incidents(window_sec: float) -> Dict[str, int]:
    path = Path(getattr(cfg, "INCIDENTS_LOG_PATH", "logs/incidents.jsonl"))
    counts = {"total": 0, "halt": 0, "error": 0}
    if not path.exists():
        return counts
    now_epoch = now_utc_epoch()
    for line in path.read_text().splitlines():
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts = row.get("ts_epoch")
        if ts is None or now_epoch - float(ts) > window_sec:
            continue
        counts["total"] += 1
        code = row.get("code") or ""
        if code == "HARD_HALT":
            counts["halt"] += 1
        if code in {"DB_WRITE_FAIL", "AUDIT_CHAIN_FAIL", "HARD_HALT"}:
            counts["error"] += 1
    return counts


def _count_decisions(window_sec: float) -> int:
    path = Path(getattr(cfg, "AUDIT_LOG_PATH", "logs/audit_log.jsonl"))
    if not path.exists():
        return 0
    now_epoch = now_utc_epoch()
    count = 0
    for line in path.read_text().splitlines():
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get("event") != "DECISION":
            continue
        ts = row.get("ts_epoch")
        if ts is None or now_epoch - float(ts) > window_sec:
            continue
        count += 1
    return count


def write_override(flags: Dict[str, Any], reason: str = "manual") -> None:
    OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(flags)
    payload["ts_epoch"] = now_utc_epoch()
    payload["reason"] = reason
    OVERRIDE_PATH.write_text(json.dumps(payload, indent=2))
    append_event({"event": "FLAGS_OVERRIDE", "flags": flags, "reason": reason, "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})


def maybe_auto_rollback() -> Dict[str, Any]:
    flags = get_flags()
    pct = int(flags.get("CANARY_PERCENT", 0))
    if pct <= 0:
        return {"rolled_back": False, "reason": "canary_disabled"}
    if not flags.get("CANARY_AUTO_ROLLBACK", True):
        return {"rolled_back": False, "reason": "auto_rollback_disabled"}
    window_min = float(flags.get("CANARY_WINDOW_MIN", 30))
    window_sec = window_min * 60.0
    decisions = _count_decisions(window_sec)
    min_decisions = int(flags.get("CANARY_MIN_DECISIONS", 20))
    if decisions < min_decisions:
        return {"rolled_back": False, "reason": "insufficient_decisions"}
    incidents = _read_incidents(window_sec)
    halt_rate = incidents["halt"] / max(decisions, 1)
    error_rate = incidents["error"] / max(decisions, 1)
    halt_thr = float(flags.get("CANARY_HALT_RATE_THRESHOLD", 0.05))
    err_thr = float(flags.get("CANARY_ERROR_RATE_THRESHOLD", 0.03))
    if halt_rate > halt_thr or error_rate > err_thr:
        write_override({"CANARY_PERCENT": 0}, reason="auto_rollback")
        try:
            create_incident(SEV2, "CANARY_ROLLBACK", {
                "halt_rate": halt_rate,
                "error_rate": error_rate,
                "decisions": decisions,
                "window_min": window_min,
            })
        except Exception as exc:
            print(f"[FLAGS_ERROR] rollback_incident_failed err={exc}")
        return {"rolled_back": True, "reason": "threshold_breach", "halt_rate": halt_rate, "error_rate": error_rate}
    return {"rolled_back": False, "reason": "within_threshold"}
