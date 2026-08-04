from __future__ import annotations

from scripts.generate_offline_fixture import build_fixture
from aixion_trade_intelligence.replay import assert_replay_deterministic, replay


def test_replay_is_independent_of_input_order():
    events = build_fixture(); first = replay(events); second = replay(reversed(events))
    assert first.deterministic_hash == second.deterministic_hash; assert [row.event_id for row in first.ordered_events] == [row.event_id for row in second.ordered_events]; assert_replay_deterministic(events)


def test_replay_deduplicates_identical_event_ids():
    events = build_fixture(); result = replay([*events, events[5]])
    assert result.raw_event_count == len(events) + 1; assert result.event_count == len(events); assert result.idempotent_duplicate_count == 1; assert result.deterministic_hash == replay(events).deterministic_hash
