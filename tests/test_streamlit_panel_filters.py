import pandas as pd

from dashboard.streamlit_app_runtime import (
    _partition_trade_universe,
    filter_trades_for_panel,
)


def test_filter_trades_for_panel_strict_statuses():
    df = pd.DataFrame(
        [
            {"symbol": "NIFTY", "status": "ACTIVE"},
            {"symbol": "BANKNIFTY", "status": "PLANNING"},
            {"symbol": "SENSEX", "status": "PROPOSED"},
            {"symbol": "MIDCPNIFTY", "status": "QUEUED_REVIEW"},
            {"symbol": "FINNIFTY", "status": "REVIEW"},
        ]
    )

    active = filter_trades_for_panel(df, "active")
    suggested = filter_trades_for_panel(df, "suggested")
    review = filter_trades_for_panel(df, "review")

    assert set(active["symbol"]) == {"NIFTY"}
    assert set(suggested["symbol"]) == {"BANKNIFTY", "SENSEX"}
    assert set(review["symbol"]) == {"MIDCPNIFTY"}


def test_partition_trade_universe_enforces_state_and_source_separation():
    df = pd.DataFrame(
        [
            {"symbol": "A", "status": "ACTIVE", "source_bucket": "suggested_quick"},
            {"symbol": "B", "status": "PLANNING", "source_bucket": "suggested_quick"},
            {"symbol": "C", "status": "PROPOSED", "source_bucket": "suggested_scalp"},
            {"symbol": "D", "status": "PLANNING", "source_bucket": "advisory_20"},
            {"symbol": "E", "status": "QUEUED_REVIEW", "source_bucket": "review_queue"},
            {"symbol": "F", "status": "REVIEW", "source_bucket": "review_queue"},
            {"symbol": "G", "status": "QUEUED_REVIEW", "source_bucket": "suggested_quick"},
        ]
    )

    active, review, suggested, advisory = _partition_trade_universe(df)

    assert set(active["symbol"]) == {"A"}
    assert set(review["symbol"]) == {"E"}
    assert set(suggested["symbol"]) == {"B", "C"}
    assert set(advisory["symbol"]) == {"D"}
    assert "A" not in set(suggested["symbol"])
