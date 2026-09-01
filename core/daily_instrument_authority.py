"""Fail-closed daily Kite instrument authority producer and consumer."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

CONTRACT_ID = "DAILY_INSTRUMENT_AUTHORITY_V1"
TIMEZONE = "Asia/Kolkata"
REQUIRED_FIELDS = {"exchange", "instrument_token", "tradingsymbol", "segment", "instrument_type", "expiry", "lot_size", "tick_size", "strike"}

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical_hash(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "artifact_sha256"}
    return sha256_bytes(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())

def _expiry(value: Any) -> bool:
    if value in (None, "", "null"):
        return True
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except ValueError:
        return False

def independent_verify(master: list[dict[str, Any]], required_tokens: list[int], *, index_token: int = 256265) -> dict[str, Any]:
    errors = 0
    token_counts: dict[int, int] = {}
    identities: set[tuple[str, str]] = set()
    index_ok = False
    for row in master:
        if not isinstance(row, dict) or not REQUIRED_FIELDS.issubset(row):
            errors += 1; continue
        try:
            token = int(row["instrument_token"]); exchange = str(row["exchange"]); symbol = str(row["tradingsymbol"])
            token_counts[token] = token_counts.get(token, 0) + 1
            identities.add((exchange, symbol))
            if token == index_token and symbol in {"NIFTY 50", "NIFTY"} and exchange == "NSE": index_ok = True
            # Kite index rows legitimately carry zero lot/tick metadata; those
            # fields are required only for tradable contract rows.
            if str(row["segment"]).upper() != "INDICES" and (int(row["lot_size"]) <= 0 or float(row["tick_size"]) <= 0): errors += 1
            if not _expiry(row["expiry"]): errors += 1
            if float(row["strike"]) < 0: errors += 1
        except (TypeError, ValueError):
            errors += 1
    missing = [int(t) for t in required_tokens if token_counts.get(int(t), 0) != 1]
    duplicate_tokens = sum(1 for n in token_counts.values() if n > 1)
    status = bool(master) and errors == 0 and not missing and duplicate_tokens == 0 and index_ok
    return {"status": "PASS" if status else "FAIL", "row_count": len(master), "parse_error_count": errors, "duplicate_token_count": duplicate_tokens, "index_identity_status": "PASS" if index_ok else "FAIL", "runtime_required_token_count": len(required_tokens), "runtime_required_token_found_count": len(required_tokens) - len(missing), "runtime_token_coverage_status": "PASS" if not missing else "FAIL", "missing_runtime_tokens": missing, "semantic_validation_status": "PASS" if status else "FAIL", "independent_verifier_status": "PASS" if status else "FAIL"}

def produce_authority(*, master_path: Path, output_path: Path, session_date: str, source_sha: str, required_tokens: list[int], previous: dict[str, Any] | None = None, reviewed_pass: bool = False) -> dict[str, Any]:
    raw = master_path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("instrument_master_must_be_list")
    verification = independent_verify(payload, required_tokens)
    material = "UNKNOWN"
    if verification["independent_verifier_status"] == "PASS":
        material = "REVIEWED_PASS" if reviewed_pass else "UNKNOWN"
    authority = {
        "contract_id": CONTRACT_ID, "session_date": session_date, "timezone": TIMEZONE, "source_sha": source_sha,
        "acquired_at": datetime.now().astimezone().isoformat(), "source": "Kite instruments read-only endpoint",
        "raw_master_sha256": sha256_bytes(raw), **verification, "material_change_status": material,
        "previous_session_authority_sha256": (previous or {}).get("artifact_sha256"),
        "authority_verdict": "PASS" if verification["independent_verifier_status"] == "PASS" and material in {"EXPECTED", "REVIEWED_PASS"} else "FAIL",
    }
    authority["artifact_sha256"] = canonical_hash(authority)
    if output_path.exists(): raise FileExistsError("dated_authority_artifact_exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=str(output_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(authority, handle, sort_keys=True, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, output_path)
    except Exception:
        try: os.unlink(temp)
        except FileNotFoundError: pass
        raise
    return authority

def validate_authority(*, artifact_path: Path, master_path: Path, session_date: str, source_sha: str, required_tokens: list[int]) -> dict[str, Any]:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    raw = master_path.read_bytes()
    ok = (artifact.get("contract_id") == CONTRACT_ID and artifact.get("session_date") == session_date and artifact.get("source_sha") == source_sha and artifact.get("raw_master_sha256") == sha256_bytes(raw) and artifact.get("authority_verdict") == "PASS" and artifact.get("independent_verifier_status") == "PASS" and artifact.get("runtime_token_coverage_status") == "PASS" and artifact.get("semantic_validation_status") == "PASS" and artifact.get("artifact_sha256") == canonical_hash(artifact))
    return {"ok": ok, "verdict": "PASS" if ok else "MORNING_BLOCKED_INSTRUMENT_AUTHORITY"}
