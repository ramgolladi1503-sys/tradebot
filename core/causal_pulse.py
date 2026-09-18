"""Unified Native Pulse & Causal Envelope Spine for TradeBot.

Establishes an immutable, cryptographically chained trace context that flows
unbroken through all 12 hops of the causal pipeline.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

IST_TZ = ZoneInfo("Asia/Kolkata")
PULSE_SCHEMA_VERSION = 1


def sha256_canonical(payload: Mapping[str, Any] | list[Any] | str | bytes) -> str:
    """Produce deterministic SHA256 hex digest of arbitrary canonical payload."""
    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class NativePulse:
    """Immutable single-event causal pulse propagating across the 12-hop pipeline."""
    pulse_id: str
    sequence_num: int
    timestamp_epoch: float
    timestamp_ist: str
    session_id: str
    producer_sha: str
    payload_sha256: str
    parent_pulse_id: str | None = None
    hop_name: str = "MARKET_FEED"
    schema_version: int = PULSE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "sequence_num": self.sequence_num,
            "timestamp_epoch": self.timestamp_epoch,
            "timestamp_ist": self.timestamp_ist,
            "session_id": self.session_id,
            "producer_sha": self.producer_sha,
            "payload_sha256": self.payload_sha256,
            "parent_pulse_id": self.parent_pulse_id,
            "hop_name": self.hop_name,
            "schema_version": self.schema_version,
        }

    def verify_integrity(self) -> bool:
        """Verify internal consistency and deterministic pulse_id hash derivation."""
        expected_id = derive_pulse_id(
            session_id=self.session_id,
            sequence_num=self.sequence_num,
            timestamp_epoch=self.timestamp_epoch,
            payload_sha256=self.payload_sha256,
            parent_pulse_id=self.parent_pulse_id,
            producer_sha=self.producer_sha,
        )
        return self.pulse_id == expected_id


def derive_pulse_id(
    *,
    session_id: str,
    sequence_num: int,
    timestamp_epoch: float,
    payload_sha256: str,
    parent_pulse_id: str | None,
    producer_sha: str,
) -> str:
    """Derive deterministic cryptographic pulse ID."""
    seed = f"{session_id}:{sequence_num}:{timestamp_epoch:.6f}:{payload_sha256}:{parent_pulse_id or 'ROOT'}:{producer_sha}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def create_native_pulse(
    *,
    session_id: str,
    sequence_num: int,
    timestamp_epoch: float | None = None,
    payload: Any,
    producer_sha: str,
    parent_pulse_id: str | None = None,
    hop_name: str = "MARKET_FEED",
) -> NativePulse:
    """Construct verified, immutable NativePulse instance."""
    ts_epoch = float(timestamp_epoch if timestamp_epoch is not None else datetime.now(timezone.utc).timestamp())
    ts_ist = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).astimezone(IST_TZ).isoformat()
    payload_hash = sha256_canonical(payload)
    pulse_id = derive_pulse_id(
        session_id=session_id,
        sequence_num=sequence_num,
        timestamp_epoch=ts_epoch,
        payload_sha256=payload_hash,
        parent_pulse_id=parent_pulse_id,
        producer_sha=producer_sha,
    )
    return NativePulse(
        pulse_id=pulse_id,
        sequence_num=sequence_num,
        timestamp_epoch=ts_epoch,
        timestamp_ist=ts_ist,
        session_id=session_id,
        producer_sha=producer_sha,
        payload_sha256=payload_hash,
        parent_pulse_id=parent_pulse_id,
        hop_name=hop_name,
    )


class NativePulseTracker:
    """Manages sequential monotonic NativePulse generation across an observation session."""

    def __init__(self, session_id: str, producer_sha: str) -> None:
        self.session_id = session_id
        self.producer_sha = producer_sha
        self.sequence_num = 0
        self.last_pulse_id: str | None = None

    def next_pulse(
        self,
        payload: Any,
        timestamp_epoch: float | None = None,
        timestamp_ist: str | None = None,
        hop_name: str = "CYCLE_OBSERVATION",
    ) -> NativePulse:
        self.sequence_num += 1
        pulse = create_native_pulse(
            session_id=self.session_id,
            sequence_num=self.sequence_num,
            timestamp_epoch=timestamp_epoch,
            payload=payload,
            producer_sha=self.producer_sha,
            parent_pulse_id=self.last_pulse_id,
            hop_name=hop_name,
        )
        self.last_pulse_id = pulse.pulse_id
        return pulse

