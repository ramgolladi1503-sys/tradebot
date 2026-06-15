from __future__ import annotations

import scripts.check_option_pipeline_health as health_script


def test_strict_fails_when_resolution_fails_even_with_runtime_tokens(monkeypatch):
    monkeypatch.setattr(
        health_script,
        "build_subscription_tokens",
        lambda symbols, max_tokens=None: (
            [101, 102, 103],
            [
                {
                    "symbol": "NIFTY",
                    "count": 1,
                    "option_count": 0,
                    "option_fail_reason": "expiry_unavailable",
                    "expiry": None,
                }
            ],
        ),
    )
    monkeypatch.setattr(
        health_script.kite_client,
        "instruments_cached",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        health_script,
        "get_feed_debug",
        lambda: {
            "ws_connected": True,
            "subscribed_tokens_count": 73,
            "intended_tokens_count": 73,
            "last_db_tick_age_sec": 1.0,
            "feed_runtime_state": "RUNNING",
            "distinct_tokens_recent": 73,
        },
    )
    monkeypatch.setattr(health_script, "get_freshness_status", lambda force=True: {"ltp": {"age_sec": 1.0}})
    monkeypatch.setattr(health_script, "_build_synthetic_lotto_candidates", lambda symbol="NIFTY": 4)
    monkeypatch.setattr(
        health_script,
        "_derivative_cache_stats",
        lambda: {"cache_exists": 1, "nfo_opt_rows": 100, "bfo_opt_rows": 100},
    )
    monkeypatch.setattr(health_script.cfg, "MIN_OPTION_TOKENS", 12, raising=False)
    monkeypatch.setattr("sys.argv", ["check_option_pipeline_health.py", "--strict"])
    assert health_script.main() == 1

