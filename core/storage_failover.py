"""Governed one-way external-to-internal storage failover state machine."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from core.runtime_storage_authority import StorageAuthorityError


class FailoverError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmergencyAuthority:
    root: Path
    device_id: int


@dataclass
class StorageEpochState:
    session_id: str
    source_sha: str
    candidate_sha: str
    storage_epoch: int = 0
    storage_authority: str = "PRIMARY_EXTERNAL"
    failover_event_id: str | None = None
    failed_over: bool = False


def verify_cross_epoch(*, genesis: dict, records: list[dict], session_id: str, source_sha: str, candidate_sha: str) -> tuple[bool, tuple[str, ...]]:
    """Independently validate an epoch-0 -> epoch-1 reconstruction."""
    errors: list[str] = []
    required = ("session_id", "source_sha", "candidate_sha", "failover_event_id", "old_storage_epoch", "new_storage_epoch", "last_known_external_cycle_id", "first_internal_cycle_id", "prospective_admission_state", "advisory_state")
    errors.extend(f"GENESIS_MISSING:{key}" for key in required if key not in genesis)
    if errors:
        return False, tuple(errors)
    if (genesis["session_id"], genesis["source_sha"], genesis["candidate_sha"]) != (session_id, source_sha, candidate_sha):
        errors.append("IDENTITY_MISMATCH")
    if genesis["old_storage_epoch"] != 0 or genesis["new_storage_epoch"] != 1:
        errors.append("EPOCH_TRANSITION_INVALID")
    if genesis["prospective_admission_state"] != "INVALIDATED_BY_STORAGE_FAILOVER":
        errors.append("ADMISSION_NOT_INVALIDATED")
    if genesis["advisory_state"] != "NO_TRADE_STORAGE_FAILOVER":
        errors.append("ADVISORY_NOT_SUSPENDED")
    previous = -1
    for row in records:
        if row.get("session_id") != session_id or row.get("source_sha") != source_sha:
            errors.append("RECORD_IDENTITY_MISMATCH")
        epoch = row.get("storage_epoch")
        if not isinstance(epoch, int) or epoch < previous or epoch not in (0, 1):
            errors.append("EPOCH_NOT_MONOTONIC")
        previous = epoch if isinstance(epoch, int) else previous
        if epoch == 1 and row.get("failover_event_id") != genesis["failover_event_id"]:
            errors.append("FAILOVER_EVENT_MISMATCH")
    return not errors, tuple(dict.fromkeys(errors))


def preflight_emergency_root(*, session_id: str, base: Path | None = None) -> EmergencyAuthority:
    base = Path(base or Path.home() / ".tradebot" / "emergency-runtime")
    root = (base / session_id).expanduser()
    real_base = base.expanduser().resolve()
    if real_base == Path("/Volumes/TradeBotData") or str(real_base).startswith("/Volumes/TradeBotData/"):
        raise FailoverError("EMERGENCY_ROOT_MUST_NOT_BE_EXTERNAL")
    root.mkdir(parents=True, exist_ok=True)
    real_root = root.resolve(strict=True)
    if real_root == Path("/Volumes/TradeBotData") or str(real_root).startswith("/Volumes/TradeBotData/"):
        raise FailoverError("EMERGENCY_ROOT_MUST_NOT_BE_EXTERNAL")
    if str(real_root).startswith(str(Path.cwd().resolve())):
        raise FailoverError("EMERGENCY_ROOT_MUST_NOT_BE_CANONICAL_CHECKOUT")
    if str(real_root).endswith("/logs") or "/tradebot/logs/" in str(real_root):
        raise FailoverError("EMERGENCY_ROOT_MUST_NOT_BE_REPOSITORY_LOGS")
    if not stat.S_ISDIR(real_root.stat().st_mode):
        raise FailoverError("EMERGENCY_ROOT_NOT_DIRECTORY")
    with tempfile.NamedTemporaryFile(dir=real_root, prefix=".emergency-probe-", delete=True):
        pass
    os.statvfs(real_root)
    return EmergencyAuthority(real_root, int(real_root.stat().st_dev))


def begin_failover(state: StorageEpochState, *, emergency: EmergencyAuthority, reason: str, last_external_cycle_id: str | None) -> dict:
    if state.failed_over or state.storage_epoch != 0:
        raise FailoverError("ONE_WAY_FAILOVER_ALREADY_USED")
    if state.storage_authority != "PRIMARY_EXTERNAL":
        raise FailoverError("FAILOVER_REQUIRES_PRIMARY_EXTERNAL")
    event_id = str(uuid.uuid4())
    state.failover_event_id = event_id
    state.storage_epoch = 1
    state.storage_authority = "EMERGENCY_INTERNAL"
    state.failed_over = True
    first_cycle = f"{state.session_id}:epoch-1:first"
    return {
        "session_id": state.session_id, "source_sha": state.source_sha, "candidate_sha": state.candidate_sha,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "failover_event_id": event_id, "old_storage_root": "/Volumes/TradeBotData", "old_storage_device": None,
        "old_storage_epoch": 0, "new_storage_root": str(emergency.root), "new_storage_device": emergency.device_id,
        "new_storage_epoch": 1, "trigger_reason": reason, "last_known_external_cycle_id": last_external_cycle_id,
        "first_internal_cycle_id": first_cycle, "external_final_write_status": "UNAVAILABLE_DUE_STORAGE_LOSS",
        "prospective_admission_state": "INVALIDATED_BY_STORAGE_FAILOVER", "advisory_state": "NO_TRADE_STORAGE_FAILOVER",
        "broker_write_calls": 0, "broker_order_calls": 0, "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0,
    }


def write_genesis(emergency: EmergencyAuthority, payload: dict) -> Path:
    target = emergency.root / "failover_genesis.json"
    if target.exists():
        raise FailoverError("FAILOVER_GENESIS_ALREADY_EXISTS")
    with tempfile.NamedTemporaryFile("w", dir=emergency.root, prefix=".genesis-", delete=False, encoding="utf-8") as handle:
        tmp = Path(handle.name)
        handle.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    tmp.replace(target)
    return target
