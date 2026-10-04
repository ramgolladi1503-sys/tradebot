from __future__ import annotations

from core.runtime_feed_truth_snapshot import build_feed_truth_snapshot


def _fresh_runtime(**overrides):
    payload = {
        "effective_ws_connected": True,
        "market_open": True,
        "last_ws_tick_age_sec": 0.5,
        "subscribed_tokens_count": 11,
        "subscribed_option_tokens_count": 10,
        "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
        "last_depth_age_sec": 0.5,
    }
    payload.update(overrides)
    return payload


def test_feed_fresh_requires_fresh_depth():
    truth = build_feed_truth_snapshot(feed_runtime=_fresh_runtime(), phase2_rejection={})

    assert truth["feed_fresh"] is True
    assert truth["depth_fresh"] is True
    assert truth["stale_reason"] == []


def test_stale_depth_blocks_aggregate_feed_freshness():
    truth = build_feed_truth_snapshot(
        feed_runtime=_fresh_runtime(last_depth_age_sec=9.0),
        phase2_rejection={},
    )

    assert truth["ws_connected"] is True
    assert truth["underlying_tick_fresh"] is True
    assert truth["option_tick_fresh"] is True
    assert truth["depth_fresh"] is False
    assert truth["feed_fresh"] is False
    assert "depth_stale_or_missing" in truth["stale_reason"]


def test_missing_depth_blocks_aggregate_feed_freshness():
    truth = build_feed_truth_snapshot(
        feed_runtime=_fresh_runtime(last_depth_age_sec=None),
        phase2_rejection={},
    )

    assert truth["depth_fresh"] is False
    assert truth["feed_fresh"] is False
    assert "depth_stale_or_missing" in truth["stale_reason"]
