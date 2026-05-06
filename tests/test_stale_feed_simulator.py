from core.stale_feed_simulator import FeedTick, classify_feed_freshness, simulate_stale_feed


def test_classify_feed_freshness_marks_fresh_tick():
    result = classify_feed_freshness(
        now_epoch=100.0,
        tick_timestamp_epoch=98.5,
        sla_threshold_sec=3.0,
    )

    assert result["status"] == "fresh"
    assert result["blocker"] is None
    assert result["age_sec"] == 1.5


def test_classify_feed_freshness_marks_stale_tick():
    result = classify_feed_freshness(
        now_epoch=100.0,
        tick_timestamp_epoch=90.0,
        sla_threshold_sec=3.0,
    )

    assert result["status"] == "stale"
    assert result["blocker"] == "STALE_TICK"
    assert result["age_sec"] == 10.0


def test_classify_feed_freshness_marks_future_tick_invalid():
    result = classify_feed_freshness(
        now_epoch=100.0,
        tick_timestamp_epoch=101.0,
        sla_threshold_sec=3.0,
    )

    assert result["status"] == "invalid"
    assert result["blocker"] == "TICK_FROM_FUTURE"


def test_simulate_stale_feed_blocks_stale_and_missing_ltp_symbols():
    result = simulate_stale_feed(
        [
            FeedTick(symbol="NIFTY", ltp=100.0, timestamp_epoch=99.0),
            FeedTick(symbol="BANKNIFTY", ltp=200.0, timestamp_epoch=90.0),
            FeedTick(symbol="SENSEX", ltp=None, timestamp_epoch=99.0),
        ],
        now_epoch=100.0,
        sla_threshold_sec=3.0,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "STALE_TICK" in result["blockers"]
    assert "MISSING_LTP" in result["blockers"]
    assert result["stale_symbols"] == ["BANKNIFTY"]
    assert result["missing_ltp_symbols"] == ["SENSEX"]


def test_simulate_stale_feed_passes_all_fresh_ticks():
    result = simulate_stale_feed(
        [
            FeedTick(symbol="NIFTY", ltp=100.0, timestamp_epoch=99.0),
            FeedTick(symbol="BANKNIFTY", ltp=200.0, timestamp_epoch=98.0),
        ],
        now_epoch=100.0,
        sla_threshold_sec=3.0,
    )

    assert result["ok"] is True
    assert result["blocked"] is False
    assert result["blockers"] == []
