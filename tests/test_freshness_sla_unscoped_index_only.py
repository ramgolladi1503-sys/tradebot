from __future__ import annotations


def test_freshness_sla_unscoped_uses_index_tokens_only(monkeypatch):
    import core.freshness_sla as fs
    from config import config as cfg

    fs._reset_cache_for_tests()

    monkeypatch.setattr(cfg, "FEED_FRESHNESS_TTL_SEC", 0.0, raising=False)
    monkeypatch.setattr(cfg, "FEED_FRESHNESS_UNSCOPED_INDEX_ONLY", True, raising=False)

    # Provide index token mapping.
    monkeypatch.setattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {"NIFTY": 256265, "BANKNIFTY": 260105}, raising=False)

    # If _depth_store_tokens were used, we'd get options and the test would fail.
    monkeypatch.setattr(fs, "_depth_store_tokens", lambda: [111, 222, 333], raising=False)

    seen = {"tokens": None}

    def _fake_metrics(*, tokens_for_ltp, now_epoch, sla_threshold_sec):
        seen["tokens"] = list(tokens_for_ltp)
        return {"last_epoch": now_epoch, "source": "ticks_memory", "stale_tokens": [], "max_tick_age_sec": 0.0, "tracked_tokens": list(tokens_for_ltp)}

    monkeypatch.setattr(fs, "_ltp_metrics_from_db", _fake_metrics, raising=False)
    monkeypatch.setattr(fs, "now_utc_epoch", lambda: 1000.0, raising=False)

    status = fs.get_freshness_status(symbol=None, tokens=None, force=True)
    assert bool(status.get("data_available")) is True
    assert sorted(seen["tokens"] or []) == [256265, 260105]

