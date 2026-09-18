"""Tests for Unified NativePulse spine and cryptographic verification."""
import pytest
from core.causal_pulse import NativePulse, create_native_pulse, sha256_canonical


def test_native_pulse_creation_and_integrity():
    payload = {"symbol": "NIFTY 50", "ltp": 24500.0, "status": "LIVE"}
    pulse = create_native_pulse(
        session_id="test-session-001",
        sequence_num=1,
        payload=payload,
        producer_sha="49f813899d062b33ad6d2f3b8231470ff8f31d94",
        parent_pulse_id=None,
        hop_name="MARKET_FEED",
    )

    assert pulse.sequence_num == 1
    assert pulse.session_id == "test-session-001"
    assert pulse.verify_integrity() is True
    assert pulse.parent_pulse_id is None
    assert pulse.payload_sha256 == sha256_canonical(payload)


def test_native_pulse_tamper_detection():
    payload = {"symbol": "NIFTY 50", "ltp": 24500.0}
    pulse = create_native_pulse(
        session_id="test-session-001",
        sequence_num=1,
        payload=payload,
        producer_sha="49f813899d062b33ad6d2f3b8231470ff8f31d94",
    )

    # Tamper with payload_sha256
    tampered_pulse = NativePulse(
        pulse_id=pulse.pulse_id,
        sequence_num=pulse.sequence_num,
        timestamp_epoch=pulse.timestamp_epoch,
        timestamp_ist=pulse.timestamp_ist,
        session_id=pulse.session_id,
        producer_sha=pulse.producer_sha,
        payload_sha256="0" * 64,
    )
    assert tampered_pulse.verify_integrity() is False


def test_native_pulse_chaining():
    p1 = create_native_pulse(
        session_id="test-session-001",
        sequence_num=1,
        payload={"bar": 1},
        producer_sha="49f813899d062b33ad6d2f3b8231470ff8f31d94",
    )
    p2 = create_native_pulse(
        session_id="test-session-001",
        sequence_num=2,
        payload={"bar": 2},
        producer_sha="49f813899d062b33ad6d2f3b8231470ff8f31d94",
        parent_pulse_id=p1.pulse_id,
    )

    assert p2.parent_pulse_id == p1.pulse_id
    assert p2.verify_integrity() is True
    assert p2.pulse_id != p1.pulse_id
