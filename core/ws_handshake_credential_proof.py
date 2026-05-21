from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CredentialProof:
    api_key_tail4: str | None
    access_token_tail4: str | None
    access_token_len: int | None
    access_token_has_internal_whitespace: bool | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_key_tail4": self.api_key_tail4,
            "access_token_tail4": self.access_token_tail4,
            "access_token_len": self.access_token_len,
            "access_token_has_internal_whitespace": self.access_token_has_internal_whitespace,
            "source": self.source,
        }


def build_handshake_credential_proof(
    *,
    api_key: str | None,
    access_token: str | None,
    source: str,
) -> CredentialProof:
    stripped_api = str(api_key or "").strip()
    stripped_token = str(access_token or "").strip()
    return CredentialProof(
        api_key_tail4=_tail4(stripped_api),
        access_token_tail4=_tail4(stripped_token),
        access_token_len=len(stripped_token),
        access_token_has_internal_whitespace=any(ch.isspace() for ch in stripped_token),
        source=str(source or "unknown"),
    )


def build_ws_handshake_attempt_event(
    *,
    api_key: str | None,
    access_token: str | None,
    token_count: int,
    profile_verified: bool,
    source: str = "kite_depth_ws_start",
) -> dict[str, Any]:
    proof = build_handshake_credential_proof(
        api_key=api_key,
        access_token=access_token,
        source=source,
    ).to_dict()
    return {
        "event": "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF",
        **proof,
        "token_count": max(0, int(token_count or 0)),
        "profile_verified": bool(profile_verified),
    }


def build_ws_auth_failure_proof_event(
    *,
    api_key: str | None,
    access_token: str | None,
    code: int | str | None,
    reason: str | None,
    auth_required_latch: bool,
    source: str = "kite_depth_ws_auth_failure",
) -> dict[str, Any]:
    proof = build_handshake_credential_proof(
        api_key=api_key,
        access_token=access_token,
        source=source,
    ).to_dict()
    return {
        "event": "FEED_WS_AUTH_FAILURE_PROOF",
        **proof,
        "code": code,
        "reason": str(reason or ""),
        "auth_required_latch": bool(auth_required_latch),
    }


def extract_latest_handshake_proof_from_lines(lines: list[str]) -> dict[str, Any]:
    for line in reversed(list(lines or [])):
        payload = _json_payload_from_line(line)
        if payload.get("event") == "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF":
            return payload
    return {}


def extract_latest_auth_failure_proof_from_lines(lines: list[str]) -> dict[str, Any]:
    for line in reversed(list(lines or [])):
        payload = _json_payload_from_line(line)
        if payload.get("event") == "FEED_WS_AUTH_FAILURE_PROOF":
            return payload
    return {}


def read_recent_log_lines(path: str | Path, *, max_lines: int = 1000) -> list[str]:
    target = Path(path).expanduser()
    if not target.exists():
        return []
    try:
        return target.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception:
        return []


def _tail4(value: str | None) -> str | None:
    text = str(value or "")
    return text[-4:] if text else None


def _json_payload_from_line(line: str) -> dict[str, Any]:
    text = str(line or "").strip()
    if not text:
        return {}
    json_start = text.find("{")
    if json_start >= 0:
        text = text[json_start:]
    try:
        payload = json.loads(text)
    except Exception:
        return _parse_key_value_line(str(line or ""))
    return payload if isinstance(payload, dict) else {}


def _parse_key_value_line(line: str) -> dict[str, Any]:
    if "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF" not in line and "FEED_WS_AUTH_FAILURE_PROOF" not in line:
        return {}
    payload: dict[str, Any] = {
        "event": "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF"
        if "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF" in line
        else "FEED_WS_AUTH_FAILURE_PROOF"
    }
    for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)", line):
        payload[key] = value
    return payload
