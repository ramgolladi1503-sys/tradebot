"""Offline Scenario C/D composition at the read-only observer boundary."""
from __future__ import annotations

from datetime import datetime

import pytest

from core.paper_shadow.strategy_shadow_adapter import StrategyMarketSnapshotBuilder
from core.runtime_snapshot_stages import build_feed_health_truth_latest_payload
from core.candidate_audits.intraday_opening_drive import IST_TZ


OPTION_SYMBOL = "NIFTY26OCT25000CE"


def _runtime_health(*, spot_state: str, websocket_ok: bool = True):
    return build_feed_health_truth_latest_payload({
        "feed_ok": False,
        "feed_ok_scope": "symbol_aggregate",
        "global_feed_blocked": False,
        "ws_connected": websocket_ok,
        "effective_ws_connected": websocket_ok,
        "runtime_state": "RUNNING",
        "option_feed_block_reason_by_symbol": {
            "NIFTY": "OK",
            OPTION_SYMBOL: "STALE",
        },
        "option_last_tick_age_by_symbol": {
            "NIFTY": 0.25,
            OPTION_SYMBOL: 900.0,
        },
        "symbol_feed_ok_by_symbol": {
            "NIFTY": True,
            OPTION_SYMBOL: False,
        },
        "domain_health_by_domain": {
            "INDEX_SPOT": {"state": spot_state},
            "INDEX_OPTIONS": {"state": "DEGRADED"},
        },
    })[0]


def _market_snapshot():
    return {"symbols": {
        "NIFTY": {
            "instrument_type": "INDEX",
            "instrument_token": 256265,
            "ltp": 25000.0,
            "quote_truth": {
                "symbol": "NIFTY",
                "instrument_token": 256265,
                "is_fresh": True,
                "ltp": 25000.0,
            },
        },
        OPTION_SYMBOL: {
            "instrument_type": "OPT",
            "segment": "NFO-OPT",
            "instrument_token": 123456,
            "underlying": "NIFTY",
            "strike": 25000,
            "option_type": "CE",
            "expiry": "2026-10-29",
            "quote_truth": {
                "symbol": OPTION_SYMBOL,
                "instrument_token": 123456,
                "is_fresh": False,
            },
        },
    }}


def _build(*, spot_state: str, websocket_ok: bool = True):
    return StrategyMarketSnapshotBuilder.build_snapshots(
        pulse_id="SCENARIO_C_D",
        timestamp_ist=datetime(2026, 10, 1, 10, 0, tzinfo=IST_TZ),
        market_snapshot=_market_snapshot(),
        feed_health_truth=_runtime_health(spot_state=spot_state, websocket_ok=websocket_ok),
    )


def test_scenario_c_stale_option_does_not_poison_healthy_spot_observer_but_option_stays_degraded():
    runtime_truth = _runtime_health(spot_state="HEALTHY")
    assert runtime_truth["read_only"] is True
    assert runtime_truth["is_order_action"] is False
    assert runtime_truth["append"] is False
    assert runtime_truth.get("broker_api_called") is not True
    assert runtime_truth.get("paper_authorized") is not True
    assert runtime_truth.get("live_authorized") is not True
    assert runtime_truth.get("allowed_for_live_execution") is not True
    snapshots = StrategyMarketSnapshotBuilder.build_snapshots(
        pulse_id="SCENARIO_C_D",
        timestamp_ist=datetime(2026, 10, 1, 10, 0, tzinfo=IST_TZ),
        market_snapshot=_market_snapshot(),
        feed_health_truth=runtime_truth,
    )
    by_symbol = {snapshot.trading_symbol: snapshot for snapshot in snapshots}

    assert set(by_symbol) == {"NIFTY", OPTION_SYMBOL}
    assert by_symbol["NIFTY"].feed_health == "HEALTHY"
    assert by_symbol["NIFTY"].instrument_key == "256265"
    assert by_symbol[OPTION_SYMBOL].feed_health == "DEGRADED"
    # This read-only snapshot contract exposes no executable-quote grant.
    assert not hasattr(by_symbol[OPTION_SYMBOL], "is_executable_quote")


@pytest.mark.parametrize(
    ("spot_state", "websocket_ok"),
    [("DEGRADED", True), ("HEALTHY", False)],
)
def test_scenario_d_required_spot_or_shared_transport_failure_stays_degraded(spot_state, websocket_ok):
    snapshots = _build(spot_state=spot_state, websocket_ok=websocket_ok)
    by_symbol = {snapshot.trading_symbol: snapshot for snapshot in snapshots}

    assert "NIFTY" in by_symbol
    assert by_symbol["NIFTY"].feed_health == "DEGRADED"
    assert by_symbol[OPTION_SYMBOL].feed_health == "DEGRADED"
