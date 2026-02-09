import json
import time
from pathlib import Path
from typing import Dict

from config import config as cfg
from core.audit_log import append_event


INCIDENTS_PATH = Path(getattr(cfg, "INCIDENTS_LOG_PATH", "logs/incidents.jsonl"))
SEV1 = "SEV1"
SEV2 = "SEV2"
SEV3 = "SEV3"
SEV4 = "SEV4"


def create_incident(sev: str, code: str, context: Dict) -> str:
    incident_id = f"inc-{int(time.time())}-{code}"
    record = {
        "incident_id": incident_id,
        "sev": sev,
        "code": code,
        "context": context,
        "ts_epoch": time.time(),
    }
    INCIDENTS_PATH.parent.mkdir(exist_ok=True)
    with INCIDENTS_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
    append_event({"event": "INCIDENT", "sev": sev, "code": code, "context": context})
    return incident_id


def close_incident(incident_id: str, resolution: str):
    record = {
        "incident_id": incident_id,
        "resolution": resolution,
        "ts_epoch": time.time(),
    }
    INCIDENTS_PATH.parent.mkdir(exist_ok=True)
    with INCIDENTS_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
    append_event({"event": "INCIDENT_CLOSED", "incident_id": incident_id, "resolution": resolution})


def trigger_audit_chain_fail(context: Dict) -> str:
    from core import risk_halt
    incident_id = create_incident(SEV1, "AUDIT_CHAIN_FAIL", context)
    try:
        risk_halt.set_halt("audit_chain_fail", {"incident_id": incident_id, **context})
    except Exception as exc:
        print(f"[INCIDENT_ERROR] audit_chain_fail halt err={exc}")
    return incident_id


def trigger_db_write_fail(context: Dict) -> str:
    from core import risk_halt
    incident_id = create_incident(SEV1, "DB_WRITE_FAIL", context)
    try:
        risk_halt.set_halt("db_write_fail", {"incident_id": incident_id, **context})
    except Exception as exc:
        print(f"[INCIDENT_ERROR] db_write_fail halt err={exc}")
    return incident_id


def trigger_feed_stale(context: Dict) -> str:
    incident_id = create_incident(SEV2, "FEED_STALE", context)
    try:
        live_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE"
        pilot_mode = bool(getattr(cfg, "LIVE_PILOT_MODE", False))
        if live_mode or pilot_mode:
            from core import risk_halt
            risk_halt.set_halt("feed_stale", {"incident_id": incident_id, **context})
    except Exception as exc:
        print(f"[INCIDENT_ERROR] feed_stale halt err={exc}")
    return incident_id


def trigger_hard_halt(context: Dict) -> str:
    return create_incident(SEV1, "HARD_HALT", context)
