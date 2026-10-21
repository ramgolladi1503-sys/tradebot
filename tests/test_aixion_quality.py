from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from scripts.generate_offline_fixture import build_fixture
from aixion_trade_intelligence.quality import INVALID, PARTIAL, VALID, validate_session


def test_valid_fixture_passes_reconciliation():
    manifest = validate_session(build_fixture()); assert manifest.verdict == VALID; assert manifest.reason_codes == (); assert manifest.coverage_ratio == 1.0; assert manifest.lookahead_violations == 0; assert all(manifest.reconciled_counts.values())


def test_missing_expected_instrument_is_partial():
    events = build_fixture(); start = events[0]; payload = dict(start.payload); payload["expected_instruments"] = [*payload["expected_instruments"], "NSE_FO|NOT_OBSERVED"]
    events[0] = replace(start, payload=payload, payload_hash=""); manifest = validate_session(events)
    assert manifest.verdict == PARTIAL; assert "EXPECTED_INSTRUMENTS_MISSING" in manifest.reason_codes


def test_feature_lookahead_is_invalid():
    events = build_fixture()
    for idx, event in enumerate(events):
        if event.event_type == "STRATEGY_EVALUATED":
            payload = dict(event.payload); payload["feature_available_times"] = {"leaky_feature": (event.event_time + timedelta(seconds=1)).isoformat()}; events[idx] = replace(event, payload=payload, payload_hash=""); break
    manifest = validate_session(events); assert manifest.verdict == INVALID; assert manifest.lookahead_violations == 1; assert "LOOKAHEAD_VIOLATION" in manifest.reason_codes


def test_producer_sequence_gap_is_invalid():
    events = build_fixture(); removed = events.pop(5); end = events[-1]; events[-1] = replace(end, payload={"expected_producer_counts": {"offline-fixture": len(events)}}, payload_hash="")
    manifest = validate_session(events); assert removed.producer_sequence in manifest.producer_sequence_gaps["offline-fixture"]; assert manifest.verdict == INVALID


def test_idempotent_duplicate_is_deduplicated_not_double_counted():
    events = build_fixture(); manifest = validate_session([*events, events[5]])
    assert manifest.verdict == VALID; assert manifest.event_count == len(events) + 1; assert manifest.unique_event_count == len(events); assert manifest.duplicate_event_ids == 1; assert "IDEMPOTENT_DUPLICATES_DEDUPLICATED" in manifest.warnings


def test_control_only_session_is_invalid():
    events = [event for event in build_fixture() if event.event_type in {"SESSION_STARTED", "SESSION_ENDED"}]; end = events[-1]
    events[-1] = replace(end, payload={"expected_producer_counts": {"offline-fixture": 2}}, payload_hash="", producer_sequence=2)
    manifest = validate_session(events); assert manifest.verdict == INVALID; assert "NO_OBSERVATIONAL_EVENTS" in manifest.reason_codes
