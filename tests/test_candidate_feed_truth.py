from core.feed.candidate_feed_truth import classify_candidate_feed_truth
from core.kite_depth_ws import _PENDING_SUBSCRIBE_TOKENS, _PENDING_MODE_FULL_TOKENS

def test_fallback_used_blocks_live():
    res = classify_candidate_feed_truth({"fallback_used": True})
    assert res.executable_feed_ready is False
    assert "FALLBACK_USED" in res.reasons

def test_missing_bid_ask_blocks_live():
    res = classify_candidate_feed_truth({"bid": 0.0, "ask": 0.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "MISSING_BID_ASK" in res.reasons

def test_invalid_spread_blocks_live():
    res = classify_candidate_feed_truth({"invalid_spread": True, "bid": 100.0, "ask": 101.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "INVALID_SPREAD" in res.reasons

def test_stale_option_ltp_blocks_live():
    res = classify_candidate_feed_truth({"option_ltp_age_sec": 20.0, "bid": 100.0, "ask": 101.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "STALE_OPTION_LTP" in res.reasons

def test_stale_depth_blocks_live():
    res = classify_candidate_feed_truth({"depth_age_sec": 20.0, "bid": 100.0, "ask": 101.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "STALE_DEPTH" in res.reasons

def test_token_health_blocks_live():
    res = classify_candidate_feed_truth({"token_health": "STALE", "bid": 100.0, "ask": 101.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "TOKEN_HEALTH_DEGRADED" in res.reasons

def test_bucket_health_blocks_live():
    res = classify_candidate_feed_truth({"bucket_health": "STALE", "bid": 100.0, "ask": 101.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "BUCKET_HEALTH_DEGRADED" in res.reasons

def test_mode_full_unverified_blocks_live():
    res = classify_candidate_feed_truth({"mode_full_verified": False, "bid": 100.0, "ask": 101.0, "quote_source": "LIVE"})
    assert res.executable_feed_ready is False
    assert "MODE_FULL_UNVERIFIED" in res.reasons

def test_pending_subscribe_blocks_live():
    _PENDING_SUBSCRIBE_TOKENS.add(12345)
    res = classify_candidate_feed_truth({"option_token": 12345, "bid": 100.0, "ask": 101.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "PENDING_SUBSCRIBE_MUTATION" in res.reasons
    _PENDING_SUBSCRIBE_TOKENS.discard(12345)

def test_pending_mode_full_blocks_live():
    _PENDING_MODE_FULL_TOKENS.add(12345)
    res = classify_candidate_feed_truth({"option_token": 12345, "bid": 100.0, "ask": 101.0, "quote_source": "LIVE", "mode_full_verified": True})
    assert res.executable_feed_ready is False
    assert "PENDING_MODE_FULL_MUTATION" in res.reasons
    _PENDING_MODE_FULL_TOKENS.discard(12345)

def test_perfect_live_is_ready():
    res = classify_candidate_feed_truth({
        "bid": 100.0,
        "ask": 101.0,
        "quote_source": "LIVE",
        "mode_full_verified": True,
        "option_ltp_age_sec": 1.0,
        "depth_age_sec": 1.0,
        "token_health": "HEALTHY",
        "bucket_health": "HEALTHY",
        "fallback_used": False,
        "invalid_spread": False,
    })
    assert res.executable_feed_ready is True
    assert res.reason_code == "OK"
