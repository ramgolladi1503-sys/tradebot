"""Fresh external session-root contract for Morning Readiness V1."""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionRootError(RuntimeError):
    pass


def create_session_root(*, external_root: Path, session_date: str, release_sha: str, evidence_root: Path | None = None) -> dict[str, Any]:
    external_root = external_root.resolve()
    if not external_root.is_absolute() or external_root == Path("/"):
        raise SessionRootError("external_root_invalid")
    if not release_sha or len(release_sha) != 40:
        raise SessionRootError("release_sha_invalid")
    external_root.mkdir(parents=True, exist_ok=True)
    if not os.access(external_root, os.W_OK):
        raise SessionRootError("external_root_not_writable")
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    session_id = f"{session_date}-{stamp}-{secrets.token_hex(4)}"
    root = external_root / "morning-sessions" / session_id
    if root.exists():
        raise SessionRootError("session_root_collision")
    root.mkdir(parents=True)
    paths = {name: root / name for name in ("evidence", "runtime", "db", "logs", "seals", "preflight")}
    for path in paths.values():
        path.mkdir()
    evidence = evidence_root.resolve() if evidence_root else paths["evidence"]
    if not str(evidence).startswith(str(external_root) + os.sep):
        raise SessionRootError("evidence_root_not_external")
    manifest = {
        "session_id": session_id,
        "session_date": session_date,
        "release_sha": release_sha,
        "root": str(root),
        "evidence_root": str(evidence),
        "root_preexisted": False,
        "root_created": True,
        "root_writable": True,
        "repository_local_live_writers": 0,
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "orders_placed": 0,
    }
    (paths["preflight"] / "session_root_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
