"""Fail-closed producer for PR815 live-session attestations.

Trust is derived from Kite WebSocket subscription lifecycle evidence, never from
caller-supplied OHLC bars. This module has no broker/order/paper/live execution
authority; it only signs read-only evidence after the completed trading session.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
SCHEMA = "tradebot-live-session-attestation-v1"
SOURCE = "tradebot_live_runtime_bridge"
STATUS = "VERIFIED_LIVE_SESSION"
PROVIDER = "kite"
TOKEN_DOMAIN = "kite_instrument_token"
TRUSTED_INDEX_TOKENS = {
    "NIFTY": 256265,
    "BANKNIFTY": 260105,
    "SENSEX": 265,
}


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _exact_sha(value: Any) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise ValueError("CODE_SHA_EXACT_REQUIRED")
    return text


def _key(value: str | None = None) -> bytes:
    raw = str(value if value is not None else os.getenv("TRADEBOT_LIVE_SESSION_ATTESTATION_KEY") or "").encode("utf-8")
    if len(raw) < 32:
        raise ValueError("TRUSTED_LIVE_ATTESTATION_KEY_REQUIRED")
    return raw


def _require_live_subscription_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, Mapping):
        raise ValueError("LIVE_SUBSCRIPTION_EVIDENCE_REQUIRED")
    row = dict(evidence)
    if str(row.get("provider") or "").lower() != PROVIDER:
        raise ValueError("LIVE_SUBSCRIPTION_PROVIDER_INVALID")
    if str(row.get("token_domain") or "") != TOKEN_DOMAIN:
        raise ValueError("LIVE_SUBSCRIPTION_TOKEN_DOMAIN_INVALID")
    feed_session_id = str(row.get("feed_session_id") or "").strip()
    if not feed_session_id:
        raise ValueError("LIVE_SUBSCRIPTION_SESSION_ID_MISSING")
    if not str(row.get("subscription_evidence_id") or "").strip():
        raise ValueError("LIVE_SUBSCRIPTION_EVIDENCE_ID_MISSING")

    token_by_symbol = row.get("token_by_symbol")
    lifecycle = row.get("token_lifecycle")
    if not isinstance(token_by_symbol, Mapping) or not isinstance(lifecycle, Mapping):
        raise ValueError("LIVE_SUBSCRIPTION_LIFECYCLE_MISSING")

    for symbol, token in TRUSTED_INDEX_TOKENS.items():
        try:
            observed_token = int(token_by_symbol.get(symbol))
        except Exception as exc:
            raise ValueError(f"LIVE_INDEX_IDENTITY_INVALID:{symbol}") from exc
        if observed_token != token:
            raise ValueError(f"LIVE_INDEX_IDENTITY_INVALID:{symbol}")
        life = lifecycle.get(str(token))
        if not isinstance(life, Mapping):
            raise ValueError(f"LIVE_INDEX_LIFECYCLE_MISSING:{symbol}")
        if str(life.get("feed_session_id") or feed_session_id) != feed_session_id:
            raise ValueError(f"LIVE_INDEX_SESSION_MISMATCH:{symbol}")
        required = (
            "subscribe_call_succeeded_epoch",
            "first_post_request_tick_epoch",
            "first_full_payload_epoch",
        )
        if any(life.get(field) is None for field in required):
            raise ValueError(f"LIVE_INDEX_FULL_SUBSCRIPTION_UNPROVEN:{symbol}")
        if life.get("final_current_generation_local_mode_is_full") is False:
            raise ValueError(f"LIVE_INDEX_FULL_MODE_UNPROVEN:{symbol}")
    return row


def build_live_session_attestation(
    *,
    session_date: date,
    code_sha: str,
    subscription_evidence: Mapping[str, Any],
    attested_at_ist: datetime | None = None,
    attestation_key: str | None = None,
) -> dict[str, Any]:
    """Build and sign one attestation from independent WebSocket lifecycle truth."""
    if not isinstance(session_date, date):
        raise ValueError("SESSION_DATE_INVALID")
    now = (attested_at_ist or datetime.now(IST)).astimezone(IST)
    if now.date() != session_date or now.time() < time(15, 30):
        raise ValueError("SESSION_NOT_COMPLETE_FOR_ATTESTATION")
    sha = _exact_sha(code_sha)
    evidence = _require_live_subscription_evidence(subscription_evidence)

    unsigned = {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": STATUS,
        "session_date": session_date.isoformat(),
        "attested_at_ist": now.isoformat(timespec="seconds"),
        "provider": PROVIDER,
        "token_domain": TOKEN_DOMAIN,
        "live_feed_session_id": str(evidence["feed_session_id"]),
        "code_sha": sha,
        "subscription_evidence_id": str(evidence["subscription_evidence_id"]),
        "subscription_evidence_sha256": hashlib.sha256(_canonical(evidence)).hexdigest(),
        "indices": {
            symbol: {"symbol": symbol, "instrument_token": token}
            for symbol, token in TRUSTED_INDEX_TOKENS.items()
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
    signed = dict(unsigned)
    signed["attestation_hmac_sha256"] = hmac.new(_key(attestation_key), _canonical(unsigned), hashlib.sha256).hexdigest()
    return signed


def produce_from_kite_depth_ws(
    *,
    session_date: date,
    code_sha: str,
    attested_at_ist: datetime | None = None,
    attestation_key: str | None = None,
) -> dict[str, Any]:
    """Read exact in-process Kite subscription truth and produce an attestation."""
    from core import kite_depth_ws

    evidence = kite_depth_ws.market_event_graph_subscription_evidence_for_tokens(TRUSTED_INDEX_TOKENS)
    return build_live_session_attestation(
        session_date=session_date,
        code_sha=code_sha,
        subscription_evidence=evidence,
        attested_at_ist=attested_at_ist,
        attestation_key=attestation_key,
    )


def write_attestation(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Write once or prove byte-identical idempotency; never overwrite conflict."""
    data = _canonical(payload)
    path = Path(path)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"IMMUTABLE_ATTESTATION_CONFLICT:{path}")
        return {"status": "IDEMPOTENT", "path": str(path), "sha256": hashlib.sha256(data).hexdigest()}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return {"status": "SEALED", "path": str(path), "sha256": hashlib.sha256(data).hexdigest()}
