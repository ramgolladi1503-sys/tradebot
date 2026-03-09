from core.paths import data_root, logs_dir
import json
import logging
import time
from pathlib import Path
from typing import Dict

from config import config as cfg
from core.audit_log import append_event


logger = logging.getLogger(__name__)


INCIDENTS_PATH = Path(getattr(cfg, "INCIDENTS_LOG_PATH", str(logs_dir() / "incidents.jsonl")))
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
    INCIDENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INCIDENTS_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
    append_event({"event": "INCIDENT", "sev": sev, "code": code, "context": context})
    try:
        from core.storage import emit_sla_violation_event

        emit_sla_violation_event(
            code=str(code or ""),
            context=dict(context or {}),
            severity=str(sev or ""),
        )
    except Exception:
        pass
    return incident_id


def close_incident(incident_id: str, resolution: str):
    record = {
        "incident_id": incident_id,
        "resolution": resolution,
        "ts_epoch": time.time(),
    }
    INCIDENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INCIDENTS_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
    append_event({"event": "INCIDENT_CLOSED", "incident_id": incident_id, "resolution": resolution})


def trigger_audit_chain_fail(context: Dict) -> str:
    from core import risk_halt
    incident_id = create_incident(SEV1, "AUDIT_CHAIN_FAIL", context)
    try:
        risk_halt.set_halt("audit_chain_fail", {"incident_id": incident_id, **context})
    except Exception as exc:
        logger.error("incident_audit_chain_fail_halt_error err=%s", exc)
    return incident_id


def trigger_db_write_fail(context: Dict) -> str:
    from core import risk_halt
    incident_id = create_incident(SEV1, "DB_WRITE_FAIL", context)
    try:
        risk_halt.set_halt("db_write_fail", {"incident_id": incident_id, **context})
    except Exception as exc:
        logger.error("incident_db_write_fail_halt_error err=%s", exc)
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
        logger.error("incident_feed_stale_halt_error err=%s", exc)
    return incident_id


def trigger_hard_halt(context: Dict) -> str:
    return create_incident(SEV1, "HARD_HALT", context)
