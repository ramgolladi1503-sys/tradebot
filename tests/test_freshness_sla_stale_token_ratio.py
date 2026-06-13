from __future__ import annotations


def test_freshness_sla_does_not_fail_on_small_fraction_stale_tokens(monkeypatch):
    """
    Regression guard:
    Freshness SLA tracks a token set (often includes option tokens). Some option tokens are sparse
    even when the feed is healthy. We should fail only when staleness is widespread (ratio-based).
    """

    import core.freshness_sla as fs
    from config import config as cfg

    fs._reset_cache_for_tests()

    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(fs, "is_market_open_ist", lambda: True, raising=False)
    monkeypatch.setattr(cfg, "SLA_REQUIRE_OPTIONS_DEPTH_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_RUNTIME_SNAPSHOT_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_TTL_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_MAX_STALE_TOKEN_RATIO", 0.5, raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_STALE_TOKEN_MIN_COUNT", 5, raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_PREFER_TICKSTORE_MEMORY", True, raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_UNSCOPED_INDEX_ONLY", False, raising=False)

    # Stable time.
    monkeypatch.setattr(fs, "now_utc_epoch", lambda: 1000.0, raising=False)

    # 100 tracked tokens: 20 stale (> threshold age), 80 fresh.
    tokens = list(range(1, 101))

    def _fake_get_last_tick(token: int, allow_db: bool = False):
        # age 10 sec for the first 20 tokens, age 0.5 sec for the rest
        if token <= 20:
            return {"ts_epoch": 990.0}
        return {"ts_epoch": 999.5}

    monkeypatch.setattr(fs, "_get_last_tick", _fake_get_last_tick, raising=False)

    # Ensure we don't touch sqlite fallback.
    monkeypatch.setattr(fs, "_get_latest_tick_rows_db", lambda toks: {}, raising=False)

    status = fs.get_freshness_status(symbol="NIFTY", tokens=tokens, force=True)
    assert bool(status.get("data_available")) is True
    assert int(status.get("ltp", {}).get("stale_tokens_count") or 0) == 20
    # 20% stale < 50% threshold, should be ok.
    assert bool(status.get("ok")) is True
