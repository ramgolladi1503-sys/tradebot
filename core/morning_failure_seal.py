"""Preservation-first forensic seal for unexpected observer termination."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seal_partial(*, session_root: Path, reason: str, pid: int | None = None) -> dict[str, Any]:
    session_root = session_root.resolve()
    if not session_root.is_dir():
        raise ValueError("session_root_missing")
    files = []
    for path in sorted(session_root.rglob("*")):
        if path.is_file() and path.name != "FORENSIC_PARTIAL.json":
            files.append({"path": str(path.relative_to(session_root)), "sha256": _sha256(path), "bytes": path.stat().st_size})
    payload = {
        "seal_type": "FORENSIC_PARTIAL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "pid": pid,
        "governed_shutdown_completed": False,
        "queues_zero_proven": False,
        "checkpoint_proven": False,
        "workers_joined_proven": False,
        "live_session_verified": False,
        "originals_mutated": False,
        "files": files,
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "orders_placed": 0,
    }
    target = session_root / "FORENSIC_PARTIAL.json"
    if target.exists():
        raise FileExistsError("forensic_partial_already_sealed")
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
