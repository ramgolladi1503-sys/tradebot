"""Build one current-session subscription authority for read-only observation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


INDEX_REQUIREMENTS = (
    {"consumer_id": "regime", "identity": "NIFTY", "segment": "NSE", "mode": "quote", "reason": "regime/core index input"},
    {"consumer_id": "regime", "identity": "BANKNIFTY", "segment": "NSE", "mode": "quote", "reason": "regime/core index input"},
    {"consumer_id": "strategies", "identity": "NIFTY", "segment": "NSE", "mode": "quote", "reason": "canonical strategy market input"},
    {"consumer_id": "strategies", "identity": "BANKNIFTY", "segment": "NSE", "mode": "quote", "reason": "canonical strategy market input"},
    {"consumer_id": "cas_v2", "identity": "NIFTY", "segment": "NSE", "mode": "quote", "reason": "CAS_SW_RUNTIME_V2_1514 index input"},
    {"consumer_id": "cas_v2", "identity": "BANKNIFTY", "segment": "NSE", "mode": "quote", "reason": "CAS_SW_RUNTIME_V2_1514 index input"},
)


def _row_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row.get("name") or row.get("tradingsymbol") or "").upper().strip(),
            str(row.get("exchange") or row.get("segment") or "").upper().strip())


def build_subscription_authority(*, rows: list[Mapping[str, Any]], session_id: str,
                                 session_date: str, source_sha: str,
                                 instrument_authority: Mapping[str, Any],
                                 consumer_registry: Iterable[str],
                                 output_path: str | Path) -> dict[str, Any]:
    if not rows or not session_id or len(source_sha) != 40:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_INPUT_MISSING")
    if instrument_authority.get("session_date") != session_date:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_SESSION_MISMATCH")
    if instrument_authority.get("source_sha") != source_sha:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_SOURCE_SHA_MISMATCH")
    if instrument_authority.get("verdict") != "PASS":
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_INSTRUMENT_AUTHORITY_NOT_PASS")
    expected_consumers = set(consumer_registry)
    requirements = [dict(item) for item in INDEX_REQUIREMENTS]
    missing_consumers = sorted({item["consumer_id"] for item in requirements} - expected_consumers)
    if missing_consumers:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_CONSUMER_REGISTRY_MISMATCH:" + ",".join(missing_consumers))
    matches: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        matches.setdefault(_row_identity(row), []).append(row)
    token_rows: dict[int, dict[str, Any]] = {}
    for requirement in requirements:
        key = (requirement["identity"], requirement["segment"])
        candidates = [row for row in matches.get(key, []) if int(row.get("instrument_token") or 0) > 0]
        if not candidates:
            raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_REQUIRED_SYMBOL_MISSING:" + requirement["identity"])
        if len({int(row["instrument_token"]) for row in candidates}) != 1:
            raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_AMBIGUOUS_IDENTITY:" + requirement["identity"])
        row = candidates[0]
        token = int(row["instrument_token"])
        item = token_rows.setdefault(token, {"token": token, "identity": requirement["identity"],
                                             "segment": requirement["segment"], "mode": requirement["mode"],
                                             "instrument_authority_sha256": instrument_authority["raw_instrument_sha256"],
                                             "consumers": [], "source_row": dict(row)})
        item["consumers"].append(requirement["consumer_id"])
    payload = {
        "schema_version": 2, "session_id": session_id, "session_date": session_date,
        "source_sha": source_sha, "instrument_authority_sha256": instrument_authority["raw_instrument_sha256"],
        "generated_at": datetime.now(timezone.utc).isoformat(), "subscription_count": len(token_rows),
        "tokens": sorted(token_rows), "subscription_tokens": sorted(token_rows),
        "requirements": requirements, "consumers": sorted(expected_consumers), "segments": ["NSE"],
        "token_provenance": sorted(token_rows.values(), key=lambda item: item["token"]),
        "broker_write_authority": False, "order_authority": False, "live_authorized": False,
        "paper_authorized": False, "execution_status": "advisory_only", "verdict": "PASS",
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


def authority_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def validate_subscription_authority_payload(payload: Mapping[str, Any], *, session_date: str,
                                            source_sha: str) -> list[int]:
    if payload.get("session_date") != session_date:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_SESSION_MISMATCH")
    if payload.get("source_sha") != source_sha:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_SOURCE_SHA_MISMATCH")
    if payload.get("verdict") != "PASS" or payload.get("read_only", True) is False:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_NOT_PASS")
    if any(payload.get(field) is not False for field in ("broker_write_authority", "order_authority", "live_authorized", "paper_authorized")):
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_SAFETY_CONTRACT_INVALID")
    tokens = sorted({int(value) for value in payload.get("subscription_tokens") or () if int(value) > 0})
    provenance = payload.get("token_provenance") or ()
    if not tokens or payload.get("subscription_count") != len(tokens) or len(provenance) != len(tokens):
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_PROVENANCE_MISSING")
    if sorted(int(item.get("token") or 0) for item in provenance) != tokens:
        raise ValueError("CURRENT_SUBSCRIPTION_AUTHORITY_PROVENANCE_MISMATCH")
    return tokens
