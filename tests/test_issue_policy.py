from __future__ import annotations

from core.issue_policy import (
    ISSUE_CATEGORY_HARD,
    ISSUE_CATEGORY_SOFT,
    ISSUE_CATEGORY_WARNING,
    classify_issue,
)


def test_classify_issue_market_closed_feed_problem_is_warning():
    out = classify_issue(
        "NO_LIVE_OPTION_FEED",
        {
            "mode": "OFFHOURS",
            "market_open": False,
            "allow_stale_quotes": True,
            "permission": "ADVISORY_ONLY",
        },
    )

    assert out.category == ISSUE_CATEGORY_WARNING
    assert out.penalty == 0.0


def test_classify_issue_live_price_mismatch_is_hard_for_execute():
    out = classify_issue(
        "PRICE_MISMATCH",
        {
            "mode": "LIVE",
            "market_open": True,
            "allow_stale_quotes": False,
            "permission": "EXECUTE",
            "quote_age_sec": 0.5,
            "quote_source": "tick_store",
        },
    )

    assert out.category == ISSUE_CATEGORY_HARD


def test_classify_issue_relaxed_price_mismatch_is_soft():
    out = classify_issue(
        "PRICE_MISMATCH",
        {
            "mode": "PAPER",
            "market_open": True,
            "allow_stale_quotes": True,
            "permission": "ADVISORY_ONLY",
            "quote_age_sec": 0.5,
            "quote_source": "tick_store",
        },
    )

    assert out.category == ISSUE_CATEGORY_SOFT
    assert out.penalty > 0.0


def test_classify_issue_no_token_is_always_hard():
    out = classify_issue(
        "NO_TOKEN",
        {
            "mode": "SIM",
            "market_open": False,
            "allow_stale_quotes": True,
            "permission": "ADVISORY_ONLY",
        },
    )

    assert out.category == ISSUE_CATEGORY_HARD


def test_classify_issue_missing_cross_asset_feature_is_soft_penalty():
    out = classify_issue(
        "MISSING_CROSS_ASSET_FEATURE",
        {
            "mode": "LIVE",
            "market_open": True,
            "permission": "QUEUE_ONLY",
        },
    )

    assert out.category == ISSUE_CATEGORY_SOFT
    assert out.penalty > 0.0


def test_classify_issue_display_entry_fallback_is_warning():
    out = classify_issue(
        "DISPLAY_ENTRY_FALLBACK",
        {
            "mode": "LIVE",
            "market_open": True,
            "permission": "ADVISORY_ONLY",
        },
    )

    assert out.category == ISSUE_CATEGORY_WARNING
    assert out.penalty == 0.0


def test_classify_issue_stale_option_ltp_with_executable_quote_is_soft():
    out = classify_issue(
        "STALE_OPTION_LTP",
        {
            "mode": "LIVE",
            "market_open": True,
            "allow_stale_quotes": False,
            "permission": "EXECUTE",
            "quote_source": "tick_store",
            "quote_age_sec": 6.0,
            "best_bid": 229.9,
            "best_ask": 230.15,
        },
    )

    assert out.category == ISSUE_CATEGORY_SOFT
    assert out.penalty > 0.0


def test_classify_issue_stale_option_ltp_without_executable_quote_is_hard():
    out = classify_issue(
        "STALE_OPTION_LTP",
        {
            "mode": "LIVE",
            "market_open": True,
            "allow_stale_quotes": False,
            "permission": "EXECUTE",
            "quote_source": "tick_store",
            "quote_age_sec": 6.0,
            "best_bid": None,
            "best_ask": None,
        },
    )

    assert out.category == ISSUE_CATEGORY_HARD
    assert out.penalty == 0.0


def test_classify_issue_minor_price_mismatch_is_soft():
    out = classify_issue(
        "PRICE_MISMATCH",
        {
            "mode": "LIVE",
            "market_open": True,
            "allow_stale_quotes": False,
            "permission": "EXECUTE",
            "quote_source": "tick_store",
            "quote_age_sec": 0.8,
            "price_mismatch_abs": 1.25,
            "price_mismatch_pct": 0.012,
            "price_mismatch_persistent": False,
        },
    )

    assert out.category == ISSUE_CATEGORY_SOFT
    assert out.penalty > 0.0


def test_classify_issue_severe_price_mismatch_is_hard():
    out = classify_issue(
        "PRICE_MISMATCH",
        {
            "mode": "LIVE",
            "market_open": True,
            "allow_stale_quotes": False,
            "permission": "EXECUTE",
            "quote_source": "tick_store",
            "quote_age_sec": 0.8,
            "price_mismatch_abs": 18.0,
            "price_mismatch_pct": 0.18,
            "price_mismatch_persistent": True,
        },
    )

    assert out.category == ISSUE_CATEGORY_HARD
    assert out.penalty == 0.0


def test_classify_issue_missing_rr_context_is_soft():
    out = classify_issue(
        "missing_rr_context",
        {
            "mode": "LIVE",
            "market_open": True,
            "allow_stale_quotes": False,
            "permission": "EXECUTE",
            "quote_source": "tick_store",
            "quote_age_sec": 0.4,
        },
    )

    assert out.category == ISSUE_CATEGORY_SOFT
    assert out.penalty > 0.0


def test_classify_issue_unregistered_code_remains_hard():
    out = classify_issue(
        "UNREGISTERED_FATAL_CHECK",
        {
            "mode": "LIVE",
            "market_open": True,
            "permission": "EXECUTE",
        },
    )

    assert out.category == ISSUE_CATEGORY_HARD
    assert out.penalty == 0.0
