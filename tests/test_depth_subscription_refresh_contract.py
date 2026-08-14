from types import SimpleNamespace

import core.depth_subscription_engine as engine


def test_freshness_refresh_never_unsubscribes_fixed_intended_registry(monkeypatch):
    ws = SimpleNamespace(
        _LAST_TOKENS=[101, 202, 303],
        _TOKEN_TO_SYMBOL={101: "NIFTY", 202: "NIFTY", 303: "NIFTY"},
        cfg=SimpleNamespace(
            SYMBOLS=["NIFTY"],
            FEED_STALE_OPTION_SUBSCRIPTION_MIN_FRESH_RATIO=0.8,
            FEED_STALE_OPTION_SUBSCRIPTION_DRIFT_REFRESH_SEC=5.0,
            FEED_STALE_OPTION_SUBSCRIPTION_REFRESH_SEC=20.0,
            FEED_STALE_OPTION_SUBSCRIPTION_URGENT_MAX_AGE_SEC=8.0,
        ),
    )

    monkeypatch.setattr(engine, "_ws_module", lambda: ws)
    monkeypatch.setattr(ws, "is_market_open_ist", lambda: True, raising=False)
    monkeypatch.setattr(ws, "build_subscription_tokens", lambda symbols: ([101, 202, 303, 404], []), raising=False)
    monkeypatch.setattr(
        engine,
        "_option_freshness_stats",
        lambda _ws, _tokens, _now: ({}, {"option_count": 3, "fresh_count": 3, "stale_count": 0, "fresh_ratio": 1.0, "max_age_sec": 0.0, "urgent_max_age_sec": 8.0}),
    )

    should_refresh, payload = engine._maybe_refresh_stale_option_subscription_universe(
        now_epoch=100.0,
        refresh_state={},
    )

    assert should_refresh is True
    assert payload["subscribe_tokens"] == [404]
    assert payload["unsubscribe_tokens"] == []
    assert payload["unsubscribe_count"] == 0
