"""CAS candidate/observation contract: deterministic OFFLINE fixtures only.

These tests establish code semantics, not historical or prospective market proof.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.cas_primitive_producer import CASPrimitiveStore
from core.causal_pulse import create_native_pulse
from core.causal_strategy_harness import evaluate_causal_strategies

IST = ZoneInfo("Asia/Kolkata")
SOURCE = "a" * 40
SESSION = "cas-unit-fixture"


def _at(hour, minute, seconds=0.0):
    return datetime(2026, 9, 23, hour, minute, tzinfo=IST).timestamp() + seconds


def _store(tmp_path, *, morning_end=110.0, omit=(), fallback=False):
    store = CASPrimitiveStore(
        tmp_path / "cas.json", session_id=SESSION,
        source_sha=SOURCE, underlying_token=256265,
    )
    for name, hour, minute, price in (
        ("0915", 9, 15, 100.0),
        ("1000", 10, 0, morning_end),
        ("1514", 15, 14, 25000.0),
    ):
        if name in omit:
            continue
        target = _at(hour, minute)
        tick = {
            "underlying_symbol": "NIFTY",
            "last_price": price,
            "timestamp_epoch": target + 0.1,
            "timestamp_authority": "EXCHANGE_TIMESTAMP",
            "source_timestamp_epoch": target + 0.1,
            "receive_timestamp_epoch": target + 0.4,
            "timestamp_fallback_used": fallback,
        }
        store.capture(
            name, target, tick,
            capture_timestamp_ist=datetime.fromtimestamp(target + 0.4, timezone.utc).astimezone(IST).isoformat(),
        )
    return store


def _run(store=None, *, symbols=None, at=None):
    epoch = _at(15, 14, 0.9) if at is None else at
    pulse = create_native_pulse(
        session_id=SESSION, sequence_num=1, payload={"fixture": True},
        timestamp_epoch=epoch, producer_sha=SOURCE,
    )
    if symbols is None:
        symbols = [{
            "symbol": "NIFTY", "instrument_token": 256265, "feed_ok": True,
            "confidence": 0.99, "direction": "BUY",  # MUST be ignored.
            "is_completed_bar_signal": True,  # MUST be ignored.
        }]
    result = evaluate_causal_strategies(
        pulse=pulse, market_snapshot={"market_open": True},
        feed_health_truth={"symbols": symbols}, cas_primitive_store=store,
    )
    return pulse, result


def test_1_verified_primitives_create_shadow_only_candidate(tmp_path):
    _, res = _run(_store(tmp_path))
    assert len(res.candidates) == 1
    candidate = res.candidates[0]
    assert candidate.strategy_qualified is True
    assert candidate.execution_eligible is False
    assert candidate.advisory_ready is True
    assert candidate.direction == "DOWN"
    assert candidate.metadata["buy_only_option_side"] == "PE"
    assert candidate.confidence is None  # CAS has no calibrated confidence.
    assert len(res.executable_candidates) == 0
    assert len(res.advisory_candidates) == 1


def test_2_generic_confidence_cannot_qualify_cas():
    _, result = _run()
    assert not result.candidates
    assert result.observations[0].qualification_state == "UNKNOWN"
    assert result.observations[0].reason_code == "CAS_PRIMITIVE_STORE_MISSING"


def test_3_registry_rejects_non_nifty_symbols(tmp_path):
    symbols = [
        {"symbol": name, "instrument_token": 1, "feed_ok": True}
        for name in ("BANKNIFTY", "FINNIFTY", "RELIANCE", "TCS", "INFY")
    ]
    _, result = _run(_store(tmp_path), symbols=symbols)
    assert len(result.candidates) == 0
    assert {o.symbol for o in result.observations if o.applicability_state == "INAPPLICABLE"} == {
        "BANKNIFTY", "FINNIFTY", "RELIANCE", "TCS", "INFY",
    }


def test_4_missing_1514_exchange_observation_blocks_qualification(tmp_path):
    _, res = _run(_store(tmp_path, omit=("1514",)))
    assert not res.candidates
    assert res.observations[0].reason_code == "CAS_1514_PRIMITIVE_MISSING"


def test_5_completed_bar_flag_does_not_bypass_missing_authority(tmp_path):
    _, res = _run(_store(tmp_path, omit=("1000",)))
    assert not res.candidates
    assert res.observations[0].qualification_state == "UNKNOWN"


def test_6_expired_decision_window_never_emits_late_candidate(tmp_path):
    _, res = _run(_store(tmp_path), at=_at(15, 15))
    assert not res.candidates
    assert res.observations[0].qualification_state == "QUALIFIED"
    assert res.rejections[0]["reason_code"] == "CAS_ADVISORY_WINDOW_EXPIRED"


def test_7_candidate_has_no_invented_option_prices(tmp_path):
    _, res = _run(_store(tmp_path))
    c = res.candidates[0]
    assert c.entry_price is c.stop_loss is c.target_price is None
    assert c.option_quote_age_sec is None
    assert c.execution_block_reason == "SHADOW_ONLY_NO_EXECUTION_AUTHORITY"


def test_8_pulse_clock_mismatch_fails_closed(tmp_path):
    from core.causal_cas_qualification import qualify_cas
    pulse, _ = _run(_store(tmp_path))
    bad = replace(pulse, timestamp_ist="2026-09-18T11:10:00+05:30")
    q = qualify_cas(pulse=bad, store=_store(tmp_path), token=256265)
    assert q.state == "UNKNOWN"
    assert q.reason == "PULSE_TIMESTAMP_MISMATCH"


def test_9_telemetry_reports_unassessed_execution_not_false_zero(tmp_path):
    _, res = _run(_store(tmp_path))
    assert res.telemetry_counters["strategy_observations"] == len(res.observations)
    assert res.telemetry_counters["qualified_candidates"] == len(res.candidates)
    assert res.telemetry_counters["execution_gates"] == "NOT_EVALUATED_SHADOW_ONLY"
    assert "blocked_spread" not in res.telemetry_counters


def test_10_corrupted_primitive_cannot_qualify(tmp_path):
    store = _store(tmp_path)
    store.rows["0915"]["price"] = 1_000_000.0  # invalidates row SHA
    _, res = _run(store)
    assert not res.candidates
    assert "PRIMITIVE_INVALID" in res.observations[0].reason_code
