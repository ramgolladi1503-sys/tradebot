from datetime import date, datetime, time
import json
from threading import Event, RLock, Thread
from types import MethodType, SimpleNamespace
from zoneinfo import ZoneInfo

from core.sentinel_live_stream_advisor import (
    SentinelLiveStreamAdvisor,
    mode5_overlays_are_diagnostic,
)
from core import sentinel_live_stream_advisor as advisor_module


IST = ZoneInfo("Asia/Kolkata")
SESSION = date(2026, 11, 23)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _advisor_with_target_or(source_timestamp_ms: int, available_at_ms: int):
    expected_start = _ms(datetime.combine(SESSION, time(9, 15), tzinfo=IST))
    expected_end = _ms(datetime.combine(SESSION, time(9, 44), tzinfo=IST))
    advisor = SimpleNamespace(
        _lock=RLock(),
        _or_generation={"NIFTY": 0, "SENSEX": 0},
        or_evidence={
            "NIFTY": {
                "session_date": SESSION.isoformat(),
                "status": "COMPLETE",
                "source": "UPSTOX_V2_1M_EXACT_30",
                "source_timestamp_ms": source_timestamp_ms,
                "available_at_ms": available_at_ms,
                "coverage_count": 30,
                "coverage_start_ms": expected_start,
                "coverage_end_ms": expected_end,
            }
        },
        or_bounds={"NIFTY": {"high": 26000.0, "low": 25800.0}, "SENSEX": {}},
        _trusted_or_proofs={},
        enable_nifty_live=False,
        market_open_time=time(9, 15),
        opening_shock_end_time=time(9, 45),
    )
    return advisor


def test_mode5_target_or_requires_source_strictly_before_bar_boundary():
    expected_source = _ms(datetime.combine(SESSION, time(9, 44), tzinfo=IST))
    decision_boundary = _ms(datetime.combine(SESSION, time(9, 45), tzinfo=IST))
    decision_available = decision_boundary + 2_000

    before = _advisor_with_target_or(expected_source, decision_boundary)
    assert SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        before, "NIFTY", decision_boundary, decision_boundary, decision_available
    )[:2] == (True, "OR_COMPLETE_VERIFIED")

    equal = _advisor_with_target_or(decision_boundary, decision_boundary)
    valid, reason, _ = SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        equal, "NIFTY", decision_boundary, decision_boundary, decision_available
    )
    assert not valid
    assert reason == "OR_SOURCE_NONCAUSAL"

    after = _advisor_with_target_or(decision_boundary + 1, decision_boundary + 2)
    valid, reason, _ = SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        after, "NIFTY", decision_boundary, decision_boundary, decision_available
    )
    assert not valid
    assert reason == "OR_SOURCE_NONCAUSAL"


def test_mode5_or_availability_must_be_observed_before_decision():
    source = _ms(datetime.combine(SESSION, time(9, 44), tzinfo=IST))
    decision_boundary = _ms(datetime.combine(SESSION, time(9, 45), tzinfo=IST))

    missing = _advisor_with_target_or(source, None)
    valid, reason, _ = SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        missing, "NIFTY", decision_boundary, decision_boundary, decision_boundary + 5
    )
    assert not valid
    assert reason == "OR_AVAILABILITY_UNPROVEN"

    late = _advisor_with_target_or(source, decision_boundary + 1)
    valid, reason, _ = SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        late, "NIFTY", decision_boundary, decision_boundary, decision_boundary
    )
    assert not valid
    assert reason == "OR_NOT_AVAILABLE_AT_DECISION"

    early = _advisor_with_target_or(source, decision_boundary)
    valid, reason, _ = SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        early, "NIFTY", decision_boundary, decision_boundary, decision_boundary
    )
    assert not valid
    assert reason == "OR_AVAILABILITY_AMBIGUOUS"

    strictly_before = _advisor_with_target_or(source, decision_boundary - 1)
    valid, reason, _ = SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        strictly_before, "NIFTY", decision_boundary, decision_boundary, decision_boundary + 1
    )
    assert valid
    assert reason == "OR_COMPLETE_VERIFIED"


def test_mode5_companion_or_is_diagnostic_when_target_is_valid():
    source = _ms(datetime.combine(SESSION, time(9, 44), tzinfo=IST))
    decision_boundary = _ms(datetime.combine(SESSION, time(9, 45), tzinfo=IST))
    advisor = _advisor_with_target_or(source, decision_boundary)
    advisor._validate_mode5_or_evidence = MethodType(
        SentinelLiveStreamAdvisor._validate_mode5_or_evidence, advisor
    )
    valid, reason, details = SentinelLiveStreamAdvisor._validate_mode5_or_pair(
        advisor, "NIFTY", decision_boundary, decision_boundary, decision_boundary + 1
    )
    assert valid
    assert reason.startswith("MODE5_TARGET_OR_VALID")
    assert details["companion_authority"] == "DIAGNOSTIC_ONLY"
    assert details["companion_validation"] == "OR_SESSION_MISMATCH"


def test_mode5_target_failure_still_reports_companion_diagnostics():
    source = _ms(datetime.combine(SESSION, time(9, 44), tzinfo=IST))
    decision_boundary = _ms(datetime.combine(SESSION, time(9, 45), tzinfo=IST))
    advisor = _advisor_with_target_or(source, decision_boundary)
    advisor._validate_mode5_or_evidence = MethodType(
        SentinelLiveStreamAdvisor._validate_mode5_or_evidence, advisor
    )
    valid, reason, details = SentinelLiveStreamAdvisor._validate_mode5_or_pair(
        advisor, "NIFTY", decision_boundary, decision_boundary, decision_boundary
    )
    assert not valid
    assert reason == "MODE5_TARGET_OR_AVAILABILITY_AMBIGUOUS"
    assert details["companion_authority"] == "DIAGNOSTIC_ONLY"
    assert details["companion_validation"] == "OR_SESSION_MISMATCH"


def test_mode5_or_pair_rejects_snapshot_if_rollover_wins_between_indices():
    source = _ms(datetime.combine(SESSION, time(9, 44), tzinfo=IST))
    decision_boundary = _ms(datetime.combine(SESSION, time(9, 45), tzinfo=IST))
    advisor = _advisor_with_target_or(source, decision_boundary - 1)
    advisor._validate_mode5_or_evidence = MethodType(
        SentinelLiveStreamAdvisor._validate_mode5_or_evidence, advisor
    )
    original = advisor._validate_mode5_or_evidence
    calls = 0
    rollover_attempted = Event()
    rollover_completed = Event()
    rollover_thread = None

    def rollover_between_indices(index_name, *args, **kwargs):
        nonlocal calls, rollover_thread
        calls += 1
        result = original(index_name, *args, **kwargs)
        if calls == 1:
            def rollover():
                rollover_attempted.set()
                with advisor._lock:
                    advisor._or_generation["NIFTY"] += 1
                    advisor.or_evidence["NIFTY"] = {"session_date": "2026-11-24"}
                rollover_completed.set()

            rollover_thread = Thread(target=rollover)
            rollover_thread.start()
            assert rollover_attempted.wait(timeout=1)
        return result

    advisor._validate_mode5_or_evidence = rollover_between_indices
    try:
        valid, reason, details = SentinelLiveStreamAdvisor._validate_mode5_or_pair(
            advisor, "NIFTY", decision_boundary, decision_boundary, decision_boundary + 1
        )
        assert valid
        assert reason == "MODE5_TARGET_OR_VALID:OR_COMPLETE_VERIFIED"
        assert details["target"]["evidence"]["session_date"] == SESSION.isoformat()
        assert details["companion"]["evidence"] == {}
        assert details["companion_validation"] == "OR_SESSION_MISMATCH"
        assert not rollover_completed.is_set()
    finally:
        if rollover_thread is not None:
            rollover_thread.join(timeout=1)
    assert rollover_completed.is_set()
    assert advisor.or_evidence["NIFTY"]["session_date"] == "2026-11-24"


def test_mode5_sizing_block_terminalizes_and_emits_observation_once_per_generation():
    records = []
    vetoes = []
    consume_calls = []
    metadata = SimpleNamespace(
        generation=7, session_day=SESSION, status="AVAILABLE",
        boundary_timestamp_ms=1000,
    )
    signal = SimpleNamespace(
        action="BUY_PUT", direction="PE", setup_reason="RP1_LOWER_BREAKDOWN",
        bar_time=time(10, 0)
    )
    depth = SimpleNamespace(
        symbol="NIFTY_25000_PE", exchange_timestamp_ms=1234,
        ingress_wall_utc="2026-11-23T04:30:00.001Z",
    )

    def consume(_self, index_name, generation, reason):
        consume_calls.append((index_name, generation, reason))
        records.append({"event_type": "MODE5_CANDIDATE_TERMINAL", "terminal_reason": reason})
        return True

    advisor = SimpleNamespace(
        _lock=RLock(),
        _cached_rbfn_candidate_meta={"NIFTY": metadata},
        cached_rbfn_signals={"NIFTY": signal},
        _mode5_policy_observed_generation={"NIFTY": None},
        _mode5_candidate_id=lambda *args: "run:2026-11-23:NIFTY:7",
        _candidate_snapshot_locked=lambda *args, **kwargs: (signal, metadata),
        _sanitize_mode5_or_telemetry=SentinelLiveStreamAdvisor._sanitize_mode5_or_telemetry,
        strike_resolver=SimpleNamespace(is_contract_matching=lambda **kwargs: True),
        _final_candidate_authorization_locked=lambda **kwargs: (True, "AUTHORIZED"),
        _validate_mode5_or_pair=lambda *args: (
            False, "MODE5_TARGET_OR_AVAILABILITY_UNPROVEN", {
                "target_authority": "PROVENANCE", "nonfinite_bound": float("nan")
            }
        ),
        _observed_ingress_timestamp_ms=lambda _value: 1235,
        log_decision_trace=lambda **kwargs: records.append(kwargs),
        _consume_cached_rbfn_candidate_locked=lambda index_name, generation, reason: consume(
            None, index_name, generation, reason
        ),
        _publish_mode5_lifecycle_record=records.append,
        record_veto=lambda *args: vetoes.append(args),
        replay_mode=False,
        session_clock=None,
        _decision_wall_clock_ms=lambda: 1795428000000,
    )
    observe = MethodType(
        SentinelLiveStreamAdvisor._record_mode5_policy_observation_and_block_locked,
        advisor,
    )
    with advisor._lock:
        first = observe(
            "NIFTY", 7, 1234, {"gate2": {"effect": "DIAGNOSTIC_ONLY"}},
            depth=depth, quote_day=SESSION, instrument_key="NSE_FO|NIFTY",
            source_order=(1, 1), target_strike=25_000.0,
            tolerance_strikes=1, strike_interval=50.0, now_ns=10,
            wall_now_ms=1234,
        )
        duplicate = observe(
            "NIFTY", 7, 1235, {"gate2": {"effect": "DIAGNOSTIC_ONLY"}},
            depth=depth, quote_day=SESSION, instrument_key="NSE_FO|NIFTY",
            source_order=(1, 1), target_strike=25_000.0,
            tolerance_strikes=1, strike_interval=50.0, now_ns=10,
            wall_now_ms=1235,
        )

    assert first is True
    assert duplicate is False
    assert consume_calls == [
        ("NIFTY", 7, "MODE5_SIZING_POLICY_UNVERIFIED")
    ]
    assert sum(row.get("event_type") == "MODE5_CANDIDATE_TERMINAL" for row in records) == 1
    policy_rows = [row for row in records if row.get("event_type") == "MODE5_POLICY_OBSERVATION"]
    assert len(policy_rows) == 1
    assert policy_rows[0]["authorization_block"] == "MODE5_SIZING_POLICY_UNVERIFIED"
    assert policy_rows[0]["observations"]["gate2"]["effect"] == "DIAGNOSTIC_ONLY"
    assert policy_rows[0]["observations"]["opening_range"]["decision_authority"] == "DIAGNOSTIC_ONLY"
    assert policy_rows[0]["observations"]["opening_range"]["valid"] is False
    assert policy_rows[0]["observations"]["opening_range"]["nonfinite_bound"] is None
    assert policy_rows[0]["observations"]["opening_range"]["telemetry_sanitization"]["status"] == "REPLACED_WITH_NULL"
    json.dumps(policy_rows[0], allow_nan=False)
    assert len(vetoes) == 1


def test_mode5_overlay_policy_does_not_apply_to_other_strategy_modes():
    assert mode5_overlays_are_diagnostic("OPTIONMATE_RBFN_AUCTION") is True
    assert mode5_overlays_are_diagnostic("SENTINEL") is False
    assert mode5_overlays_are_diagnostic("INTRADAY_REVERSAL") is False
    assert mode5_overlays_are_diagnostic("MIDDAY_MOMENTUM_EXTENSION") is False


def test_mode5_or_availability_cannot_precede_source_timestamp():
    source = _ms(datetime.combine(SESSION, time(9, 44), tzinfo=IST))
    decision_boundary = _ms(datetime.combine(SESSION, time(9, 45), tzinfo=IST))
    advisor = _advisor_with_target_or(source, source - 1)
    valid, reason, _ = SentinelLiveStreamAdvisor._validate_mode5_or_evidence(
        advisor, "NIFTY", decision_boundary, decision_boundary, decision_boundary + 1
    )
    assert not valid
    assert reason == "OR_AVAILABILITY_PRECEDES_SOURCE"


def test_or_telemetry_sanitizer_emits_strict_json_and_replacement_paths():
    detail = {"high": float("nan"), "nested": [float("inf"), -float("inf")], "clean": 1.25}
    safe = SentinelLiveStreamAdvisor._sanitize_mode5_or_telemetry(detail)
    assert safe["high"] is None
    assert safe["nested"] == [None, None]
    assert safe["clean"] == 1.25
    assert safe["telemetry_sanitization"]["status"] == "REPLACED_WITH_NULL"
    assert safe["telemetry_sanitization"]["replaced_paths"] == [
        "or_details.high", "or_details.nested[0]", "or_details.nested[1]"
    ]
    json.dumps(safe, allow_nan=False)


def test_replay_quote_identity_uses_explicit_event_clock_and_fails_closed(monkeypatch):
    event_clock = datetime.combine(SESSION, time(10, 0), tzinfo=IST)
    depth = SimpleNamespace(
        exchange_timestamp_ms=_ms(event_clock) - 1_000,
        ingress_monotonic_ns=123_456,
        sequence_id=1,
        token="NSE_FO|NIFTY_TEST_TOKEN",
    )
    advisor = SimpleNamespace(
        replay_mode=True,
        session_clock=lambda: event_clock,
        _canonical_option_instrument_key=SentinelLiveStreamAdvisor._canonical_option_instrument_key,
    )
    advisor._decision_wall_clock_ms = MethodType(
        SentinelLiveStreamAdvisor._decision_wall_clock_ms, advisor
    )
    monkeypatch.setattr(
        advisor_module, "_wall_clock_seconds",
        lambda: (_ for _ in ()).throw(AssertionError("host wall clock consulted")),
    )
    valid, reason, quote_day, key, order = SentinelLiveStreamAdvisor._option_quote_identity(
        advisor, "NIFTY", depth,
    )
    assert valid
    assert reason == "OPTION_DEPTH_VALID"
    assert quote_day == SESSION
    assert key == "NSE_FO|NIFTY_TEST_TOKEN"
    assert order == (depth.exchange_timestamp_ms, 1)

    advisor.session_clock = lambda: (_ for _ in ()).throw(RuntimeError("clock unavailable"))
    valid, reason, *_ = SentinelLiveStreamAdvisor._option_quote_identity(
        advisor, "NIFTY", depth,
    )
    assert not valid
    assert reason == "OPTION_DEPTH_INVALID_CLOCK_OR_FRESHNESS"
