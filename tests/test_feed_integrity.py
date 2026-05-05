from core.feed_integrity import evaluate_feed_integrity


def test_blocks_on_stale_tick():
    res = evaluate_feed_integrity(
        ws_connected=True,
        tick_age_sec=5.0,
        depth_age_sec=1.0,
        queue_pressure_pct=10.0,
        ingest_lag_sec=0.1,
        fallback_used=False,
        market_open=True,
    )
    assert not res.execution_allowed
    assert "tick_stale" in res.reasons


def test_blocks_on_fallback():
    res = evaluate_feed_integrity(
        ws_connected=True,
        tick_age_sec=0.5,
        depth_age_sec=0.5,
        queue_pressure_pct=10.0,
        ingest_lag_sec=0.1,
        fallback_used=True,
        market_open=True,
    )
    assert not res.execution_allowed
    assert "fallback_used" in res.reasons


def test_allows_when_clean():
    res = evaluate_feed_integrity(
        ws_connected=True,
        tick_age_sec=0.5,
        depth_age_sec=0.5,
        queue_pressure_pct=10.0,
        ingest_lag_sec=0.1,
        fallback_used=False,
        market_open=True,
    )
    assert res.execution_allowed
