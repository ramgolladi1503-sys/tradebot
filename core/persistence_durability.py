"""Read-only aggregate truth for durable persistence health."""

from datetime import datetime, timezone
import threading

_LOCK = threading.Lock()
_STATE = {"persistence_durability_degraded": False, "recovery_allowed": True,
          "degraded_authorities": set(), "first_degraded_ts_utc": None,
          "last_degraded_ts_utc": None, "last_degraded_reason": None}


def reset() -> None:
    with _LOCK:
        _STATE.update(persistence_durability_degraded=False, recovery_allowed=True,
                      degraded_authorities=set(), first_degraded_ts_utc=None,
                      last_degraded_ts_utc=None, last_degraded_reason=None)


def record_degradation(authority: str, reason: str, *, irrecoverable: bool = True) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        _STATE["persistence_durability_degraded"] = True
        _STATE["recovery_allowed"] = False if irrecoverable else _STATE["recovery_allowed"]
        _STATE["degraded_authorities"].add(str(authority))
        _STATE["first_degraded_ts_utc"] = _STATE["first_degraded_ts_utc"] or now
        _STATE["last_degraded_ts_utc"] = now
        _STATE["last_degraded_reason"] = str(reason)


def snapshot() -> dict:
    with _LOCK:
        degraded = bool(_STATE["persistence_durability_degraded"])
        return {**_STATE, "degraded_authorities": sorted(_STATE["degraded_authorities"]),
                "persistence_durability_ready": not degraded}


def execution_authority() -> dict:
    state = snapshot()
    return {"execution_authority": False if state["persistence_durability_degraded"] else False,
            "trade_emission_authority": False,
            "reason": "PERSISTENCE_DURABILITY_DEGRADED" if state["persistence_durability_degraded"] else "READ_ONLY"}
