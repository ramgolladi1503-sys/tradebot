from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
ENV_RUN_ID = "TRADEBOT_RUN_ID"
ENV_BOOT_EPOCH = "TRADEBOT_BOOT_EPOCH"


@dataclass(frozen=True)
class RuntimeBootIdentity:
    run_id: str
    boot_epoch: float
    pid: int


def get_runtime_boot_identity() -> RuntimeBootIdentity:
    run_id = os.environ.get(ENV_RUN_ID)
    if not run_id:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        os.environ[ENV_RUN_ID] = run_id

    raw_boot_epoch = os.environ.get(ENV_BOOT_EPOCH)
    try:
        boot_epoch = float(raw_boot_epoch) if raw_boot_epoch is not None else time.time()
    except (TypeError, ValueError):
        boot_epoch = time.time()

    os.environ[ENV_BOOT_EPOCH] = str(boot_epoch)

    return RuntimeBootIdentity(
        run_id=run_id,
        boot_epoch=boot_epoch,
        pid=os.getpid(),
    )


def stamp_runtime_payload(payload: Mapping[str, Any] | None, *, writer: str) -> dict[str, Any]:
    identity = get_runtime_boot_identity()
    stamped = dict(payload or {})

    stamped.setdefault("ts_epoch", time.time())
    stamped["run_id"] = identity.run_id
    stamped["boot_epoch"] = identity.boot_epoch
    stamped["pid"] = identity.pid
    stamped["writer"] = writer
    stamped["schema_version"] = SCHEMA_VERSION

    return stamped


def classify_runtime_payload_freshness(
    payload: Mapping[str, Any] | None,
    *,
    path: str | Path | None = None,
    current: RuntimeBootIdentity | None = None,
) -> dict[str, Any]:
    current = current or get_runtime_boot_identity()
    data = dict(payload or {})
    reasons: list[str] = []

    payload_run_id = data.get("run_id")
    if not payload_run_id:
        reasons.append("missing_run_id")
    elif payload_run_id != current.run_id:
        reasons.append("run_id_mismatch")

    try:
        payload_boot_epoch = float(data.get("boot_epoch"))
    except (TypeError, ValueError):
        payload_boot_epoch = None
        reasons.append("missing_or_invalid_boot_epoch")

    if payload_boot_epoch is not None and payload_boot_epoch < current.boot_epoch:
        reasons.append("older_than_current_boot")

    if not data.get("writer"):
        reasons.append("missing_writer")

    try:
        schema_version = int(data.get("schema_version"))
    except (TypeError, ValueError):
        schema_version = None

    if schema_version != SCHEMA_VERSION:
        reasons.append("schema_version_mismatch")

    if path is not None:
        target = Path(path)
        if target.exists() and target.stat().st_mtime < current.boot_epoch:
            reasons.append("mtime_older_than_current_boot")

    return {
        "is_current_run": not reasons,
        "freshness_reasons": reasons,
        "payload_run_id": payload_run_id,
        "current_run_id": current.run_id,
        "payload_boot_epoch": data.get("boot_epoch"),
        "current_boot_epoch": current.boot_epoch,
        "payload_pid": data.get("pid"),
        "current_pid": current.pid,
        "payload_writer": data.get("writer"),
        "schema_version": data.get("schema_version"),
    }
