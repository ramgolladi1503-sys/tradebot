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



def test_live_option_evidence_does_not_treat_123_token_union_as_options():
    count, source = health_script._live_option_token_evidence(
        {
            "subscribed_tokens_count": 123,
            "intended_tokens_count": 123,
            "distinct_tokens_recent": 123,
            "subscribed_option_tokens_count": 0,
            "option_tokens_subscribed_count_by_symbol": {},
        },
        resolved_option_tokens_count=0,
    )
    assert count == 0
    assert source == "unverified"


def test_live_option_evidence_prefers_runtime_option_counts_by_symbol():
    count, source = health_script._live_option_token_evidence(
        {
            "subscribed_tokens_count": 123,
            "subscribed_option_tokens_count": 70,
            "option_tokens_subscribed_count_by_symbol": {
                "NIFTY": 26,
                "BANKNIFTY": 26,
                "SENSEX": 18,
            },
        },
        resolved_option_tokens_count=72,
    )
    assert count == 70
    assert source == "runtime_option_counts_by_symbol"


def test_live_option_evidence_uses_exact_runtime_option_count_before_resolution():
    count, source = health_script._live_option_token_evidence(
        {
            "subscribed_option_tokens_count": 68,
            "option_tokens_subscribed_count_by_symbol": {},
        },
        resolved_option_tokens_count=72,
    )
    assert count == 68
    assert source == "runtime_option_subscription_count"
