from __future__ import annotations

from types import SimpleNamespace

from config import config as cfg
from core.quote_truth import resolve_quote_validation_status
from core import review_queue
from strategies.trade_builder import TradeBuilder


def test_resolve_quote_validation_status_overrides_stale_when_quote_recovers():
    assert (
        resolve_quote_validation_status(
            existing_status="STALE_OPTION_LTP",
            current_ltp=24.1,
            quote_age_sec=0.6,
            best_bid=24.0,
            best_ask=24.1,
            max_quote_age_sec=8.0,
        )
        == "OK"
    )


def test_resolve_quote_validation_status_keeps_price_mismatch_passthrough():
    assert (
        resolve_quote_validation_status(
            existing_status="PRICE_MISMATCH",
            current_ltp=24.1,
            quote_age_sec=0.6,
            best_bid=24.0,
            best_ask=24.1,
            max_quote_age_sec=8.0,
        )
        == "PRICE_MISMATCH"
    )


def test_review_queue_quote_truth_snapshot_recomputes_fresh_status():
    entry = {
        "trade_id": "T-QUOTE-FRESH-Q",
        "symbol": "NIFTY",
        "current_ltp": 24.1,
        "best_bid": 24.0,
        "best_ask": 24.1,
        "quote_source": "live",
        "option_ltp_source": "live",
        "quote_validation_status": "STALE_OPTION_LTP",
        "quote_ts_epoch": 200.0,
        "quote_age_sec": 0.6,
    }

    snapshot = review_queue._quote_truth_snapshot_from_entry(entry, source="builder", now_epoch=200.6)

    assert snapshot["quote_validation_status"] == "OK"


def test_merge_quote_truth_preserves_fresher_builder_quote_when_queue_is_older():
    entry = {
        "trade_id": "T-QUOTE-OLDER",
        "symbol": "NIFTY",
        "current_ltp": 150.0,
        "best_bid": 149.5,
        "best_ask": 150.0,
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "quote_validation_status": "OK",
        "quote_ts_epoch": 100.0,
        "quote_age_sec": 0.8,
        "source_flags": {
            "quote_truth": {
                "quote_snapshot_id": "builder|100.0",
                "quote_ts_epoch": 100.0,
                "quote_age_sec": 0.8,
                "current_ltp": 150.0,
                "best_bid": 149.5,
                "best_ask": 150.0,
                "quote_source": "tick_store",
                "option_ltp_source": "tick_store",
                "quote_validation_status": "OK",
            }
        },
    }
    builder_truth = review_queue._quote_truth_snapshot_from_entry(entry, source="builder", now_epoch=200.0)
    queue_truth = {
        "quote_snapshot_id": "queue|90.0",
        "quote_ts_epoch": 90.0,
        "quote_age_sec": 1.6,
        "current_ltp": 149.0,
        "best_bid": 149.0,
        "best_ask": 149.5,
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "quote_validation_status": "STALE_OPTION_LTP",
    }

    merged, action, drift = review_queue._merge_quote_truth(
        entry,
        builder_truth=builder_truth,
        queue_truth=queue_truth,
        now_epoch=200.0,
    )

    assert action == "preserved_builder"
    assert drift["action"] == "preserved_builder"
    assert merged["current_ltp"] == 150.0
    assert merged["best_bid"] == 149.5
    assert merged["best_ask"] == 150.0
    assert merged["quote_validation_status"] == "OK"
    assert merged["source_flags"]["quote_truth"]["quote_snapshot_id"] == "builder|100.0"


def test_merge_quote_truth_accepts_newer_queue_quote():
    entry = {
        "trade_id": "T-QUOTE-NEWER",
        "symbol": "NIFTY",
        "current_ltp": 150.0,
        "best_bid": 149.5,
        "best_ask": 150.0,
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "quote_validation_status": "OK",
        "quote_ts_epoch": 100.0,
        "quote_age_sec": 0.8,
        "source_flags": {
            "quote_truth": {
                "quote_snapshot_id": "builder|100.0",
                "quote_ts_epoch": 100.0,
                "quote_age_sec": 0.8,
                "current_ltp": 150.0,
                "best_bid": 149.5,
                "best_ask": 150.0,
                "quote_source": "tick_store",
                "option_ltp_source": "tick_store",
                "quote_validation_status": "OK",
            }
        },
    }
    builder_truth = review_queue._quote_truth_snapshot_from_entry(entry, source="builder", now_epoch=200.0)
    queue_truth = {
        "quote_snapshot_id": "queue|105.0",
        "quote_ts_epoch": 105.0,
        "quote_age_sec": 0.4,
        "current_ltp": 151.0,
        "best_bid": 150.5,
        "best_ask": 151.0,
        "quote_source": "live",
        "option_ltp_source": "live",
        "quote_validation_status": "OK",
    }

    merged, action, drift = review_queue._merge_quote_truth(
        entry,
        builder_truth=builder_truth,
        queue_truth=queue_truth,
        now_epoch=200.0,
    )

    assert action == "updated_from_queue"
    assert drift["action"] == "updated_from_queue"
    assert merged["current_ltp"] == 151.0
    assert merged["best_bid"] == 150.5
    assert merged["best_ask"] == 151.0
    assert merged["quote_validation_status"] == "OK"
    assert merged["source_flags"]["quote_truth"]["quote_snapshot_id"] == "queue|105.0"


def test_merge_quote_truth_preserves_builder_when_queue_is_missing():
    entry = {
        "trade_id": "T-QUOTE-MISSING",
        "symbol": "NIFTY",
        "current_ltp": 150.0,
        "best_bid": 149.5,
        "best_ask": 150.0,
        "quote_source": "tick_store",
        "option_ltp_source": "tick_store",
        "quote_validation_status": "OK",
        "quote_ts_epoch": 100.0,
        "quote_age_sec": 0.8,
        "source_flags": {
            "quote_truth": {
                "quote_snapshot_id": "builder|100.0",
                "quote_ts_epoch": 100.0,
                "quote_age_sec": 0.8,
                "current_ltp": 150.0,
                "best_bid": 149.5,
                "best_ask": 150.0,
                "quote_source": "tick_store",
                "option_ltp_source": "tick_store",
                "quote_validation_status": "OK",
            }
        },
    }
    builder_truth = review_queue._quote_truth_snapshot_from_entry(entry, source="builder", now_epoch=200.0)

    merged, action, drift = review_queue._merge_quote_truth(
        entry,
        builder_truth=builder_truth,
        queue_truth={},
        now_epoch=200.0,
    )

    assert action == "preserved_builder"
    assert drift["action"] == "preserved_builder"
    assert merged["current_ltp"] == 150.0
    assert merged["best_bid"] == 149.5
    assert merged["best_ask"] == 150.0
    assert merged["quote_validation_status"] == "OK"


def test_builder_stamp_quote_truth_recomputes_fresh_status_from_live_quote(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0, raising=False)
    monkeypatch.setattr("strategies.trade_builder.now_utc_epoch", lambda: 200.6, raising=False)
    builder = TradeBuilder(predictor=None)
    trade = SimpleNamespace(
        trade_id="T-QUOTE-FRESH",
        symbol="NIFTY",
        instrument_token=99123,
        tradingsymbol="NIFTY26APR23650PE",
        strike=23650.0,
        expiry="2026-04-28",
        expiry_date="2026-04-28",
        option_type="PE",
        right="PE",
        current_ltp=24.1,
        best_bid=24.0,
        best_ask=24.1,
        quote_validation_status="STALE_OPTION_LTP",
        option_ltp_source="live",
        quote_source="live",
        source_flags={
            "quote_truth": {
                "quote_snapshot_id": "stale|old",
                "quote_ts_epoch": 100.0,
                "quote_age_sec": 12.0,
                "current_ltp": 23.8,
                "best_bid": 23.7,
                "best_ask": 23.8,
                "quote_source": "live",
                "option_ltp_source": "live",
                "quote_validation_status": "STALE_OPTION_LTP",
            }
        },
    )

    snapshot = builder._stamp_quote_truth_snapshot(
        trade,
        market_data={
            "symbol": "NIFTY",
            "option_chain": [
                {
                    "instrument_token": 99123,
                    "tradingsymbol": "NIFTY26APR23650PE",
                    "strike": 23650.0,
                    "expiry": "2026-04-28",
                    "type": "PE",
                    "quote_live": True,
                    "quote_ok": True,
                    "quote_ts_epoch": 200.0,
                    "quote_age_sec": 0.6,
                    "ltp": 24.1,
                    "best_bid": 24.0,
                    "best_ask": 24.1,
                    "quote_source": "live",
                    "option_ltp_source": "live",
                }
            ],
        },
        source_flags=dict(trade.source_flags),
        lifecycle=None,
    )

    assert snapshot["quote_validation_status"] == "OK"
    assert trade.source_flags["quote_truth"]["quote_validation_status"] == "OK"
