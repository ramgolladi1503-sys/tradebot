"""Read-only evidence sidecar for PR890 MarketSessionStore.

This module never imports broker, order, strategy, ranking, or risk code. It
only reads the core session-memory interface and writes append/atomic evidence
outside the repository.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

AUTHORITY = "/Volumes/TradeBotData"
SAFETY = {"read_only": True, "broker_write_authority": False, "order_authority": False,
          "paper_authorized": False, "live_authorized": False, "execution_status": "advisory_only"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2, default=str)
            handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(raw, path)
    except BaseException:
        try: os.unlink(raw)
        except OSError: pass
        raise


def evidence_dir(session_id: str, *, root: str | Path = AUTHORITY, day: str | None = None) -> Path:
    if not str(session_id).strip(): raise ValueError("session_id_missing")
    if not str(root).startswith(AUTHORITY): raise ValueError("external_storage_authority_required")
    session_day = day or datetime.now().astimezone().strftime("%Y%m%d")
    return Path(root) / "market-session-memory-sidecar" / session_day / str(session_id)


def capture_preflight(*, session_id: str, source_sha: str, core_sha: str, sidecar_sha: str,
                      storage_epoch: str, storage_writable: bool, session_memory_available: bool,
                      output_root: str | Path = AUTHORITY) -> dict[str, Any]:
    blocked = []
    if not storage_writable: blocked.append("storage_not_writable")
    if not session_memory_available: blocked.append("session_memory_authority_unavailable")
    result = {"schema_version": 1, "session_id": session_id, "source_sha": source_sha,
              "core_pr890_head_sha": core_sha, "sidecar_sha": sidecar_sha,
              "generated_at": datetime.now().astimezone().isoformat(),
              "storage_authority": str(output_root), "storage_epoch": storage_epoch,
              "session_memory_db_available": session_memory_available,
              "outcome": "BLOCKED" if blocked else "PASS", "blockers": blocked, **SAFETY,
              "broker_api_called": False, "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0}
    _atomic_json(evidence_dir(session_id, root=output_root) / "preflight.json", result)
    return result


def checkpoint(*, store: Any, symbol: str, as_of: Any, session_id: str, source_sha: str,
               core_sha: str, sidecar_sha: str, seq: int) -> dict[str, Any]:
    if seq < 0: raise ValueError("checkpoint_sequence_invalid")
    context = dict(store.build_context(symbol, as_of=as_of))
    result = {"checkpoint_seq": seq, "checkpoint_timestamp": str(as_of), "session_id": session_id,
              "source_sha": source_sha, "core_pr890_head_sha": core_sha, "sidecar_sha": sidecar_sha,
              "symbol": symbol, "bar_count_1m": context.get("bars", {}).get("1m", 0),
              "latest_completed_bar_timestamp": context.get("authoritative_up_to_ist"),
              "missing_minute_count": context.get("missing_1m_bars"),
              "derived_5m_count": context.get("bars", {}).get("5m", 0),
              "derived_15m_count": context.get("bars", {}).get("15m", 0),
              "derived_30m_count": context.get("bars", {}).get("30m", 0),
              "derived_60m_count": context.get("bars", {}).get("60m", 0),
              "session_context": context, "storage_state": "EXTERNAL", **SAFETY}
    return result


def compare_replay(*, original: Mapping[str, Any], replay: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("bars", "missing_1m_bars", "coverage_pct", "session_date", "symbol", "as_of_ist")
    for field in fields:
        if original.get(field) != replay.get(field):
            return {"status": "REPLAY_MISMATCH", "first_divergent_primitive": field, **SAFETY}
    return {"status": "REPLAY_MATCH", "compared_fields": list(fields), **SAFETY}


def verify_evidence(root: str | Path, *, session_id: str) -> dict[str, Any]:
    directory = evidence_dir(session_id, root=root)
    preflight = directory / "preflight.json"
    if not preflight.exists(): return {"status": "BLOCKED", "reason": "preflight_missing", **SAFETY}
    payload = json.loads(preflight.read_text(encoding="utf-8"))
    if payload.get("session_id") != session_id or payload.get("storage_authority") != str(root):
        return {"status": "FAIL", "reason": "identity_mismatch", **SAFETY}
    if any(payload.get(key) is not value for key, value in (("read_only", True), ("broker_write_authority", False), ("order_authority", False), ("paper_authorized", False), ("live_authorized", False))):
        return {"status": "FAIL", "reason": "unsafe_authority_flags", **SAFETY}
    return {"status": "PASS" if payload.get("outcome") == "PASS" else "BLOCKED", "session_id": session_id, **SAFETY}
