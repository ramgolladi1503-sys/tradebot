"""
Unit Tests for OptionMate Restart PIT Anchor & Session Freeze Suite.

Work Item: FEAT-OPTIONMATE-RESTART-PIT-ANCHOR-003
Pipeline: Hermes Architecture -> GSD Scoped Execution
Governance: TradeBot Agent OS (read_only=True, is_order_action=False)

Verifies:
1. Upstox live quote resolution:
   Computes prior day close strictly from round(last_price - net_change, 2) = 25144.30
   Rejects mutated ohlc['close'] = 25220.35.
   Tests daily candle endpoint fallback when net_change is missing.
2. Midday restart drift immunity:
   First boot at 09:20 produces frozen session grid stored in /tmp/tradebot_rbfn_cache_{today}.json.
   Subsequent midday restart at 14:32 (with drifting live spots) reuses identical frozen boundaries.
3. Gap regime preservation against 5m bar wick distortion:
   Validates abs(gap) >= gap_threshold holds during opening gap acceptance.
   Prevents wide wick extremes from pulling Trend Decider into the sky.
   Anchors to opening body equilibrium (spot_open / bar_5m.open).
   Calibrated NIFTY base_step: 102.0 yields RP1 Upper: 25317.0, RP1 Lower: 25113.0 from TD 25215.0.
"""

import os
import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from strategies.optionmate_rbfn_strategy import (
    OptionMateRBFNStrategy,
    OptionMateGrid,
    GoldenCandle,
)
from core.sentinel_dashboard_rbfn_helper import (
    compute_official_rbfn_boundaries,
    resolve_upstox_prev_close,
    get_cache_path,
)


class TestOptionMateRestartPITAnchor:

    def test_upstox_live_quote_resolution_and_rejection_of_mutated_close(self):
        """Prove that resolve_upstox_prev_close derives prior close strictly from last_price - net_change.
        Rejects mutated ohlc['close'] which Upstox mutates to the live candle close.
        """
        # Simulated Upstox quote payload during live market hours
        # last_price = 25215.00, net_change = 70.70 => true prior close = 25144.30
        # mutated ohlc.close = 25220.35 (floating live intraday value)
        item = {
            "last_price": 25215.00,
            "net_change": 70.70,
            "ohlc": {
                "open": 25215.00,
                "high": 25290.00,
                "low": 25200.00,
                "close": 25220.35,  # Mutated by Upstox during market hours!
            },
        }

        resolved = resolve_upstox_prev_close(item)
        assert resolved is not None
        assert resolved == 25144.30
        assert resolved != item["ohlc"]["close"]

    def test_upstox_daily_candle_fallback_when_net_change_unavailable(self):
        """Prove that when net_change is missing, resolve_upstox_prev_close falls back to daily historical candles."""
        item = {
            "last_price": 25215.00,
            "ohlc": {"open": 25215.00, "high": 25290.00, "low": 25200.00, "close": None},
        }
        today_s = datetime.now().strftime("%Y-%m-%d")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Historical candle: [timestamp, open, high, low, close, volume, oi]
        mock_resp.json.return_value = {
            "data": {
                "candles": [
                    [f"{today_s}T00:00:00+05:30", 25215.0, 25290.0, 25200.0, 25220.0, 1000, 0],
                    ["2026-11-13T00:00:00+05:30", 25100.0, 25180.0, 25050.0, 25144.30, 50000, 0],
                ]
            }
        }

        with patch("requests.get", return_value=mock_resp):
            fallback_close = resolve_upstox_prev_close(item, instrument_key="NSE_INDEX%7CNifty%2050", token="test_token")
            assert fallback_close == 25144.30

    def test_midday_restart_drift_immunity_via_session_cache(self):
        """Prove that first boot at 09:20 freezes the grid, and a midday restart at 14:32 reuses the exact frozen grid."""
        today_s = datetime.now().strftime("%Y-%m-%d")
        cache_file = get_cache_path(today_s)

        # Ensure clean state for test
        if os.path.exists(cache_file):
            os.remove(cache_file)

        try:
            # 1. First boot at 09:20: Opening 5m candle completes
            # Spot open = 25215.0, prior close = 25144.30, gap = +70.70
            bar_5m_morning = [
                ["2026-11-16T09:19:00+05:30", 25250.0, 25275.0, 25240.0, 25270.0, 2000],
                ["2026-11-16T09:18:00+05:30", 25240.0, 25260.0, 25230.0, 25255.0, 2000],
                ["2026-11-16T09:17:00+05:30", 25230.0, 25250.0, 25220.0, 25245.0, 2000],
                ["2026-11-16T09:16:00+05:30", 25220.0, 25240.0, 25210.0, 25235.0, 2000],
                ["2026-11-16T09:15:00+05:30", 25215.0, 25230.0, 25200.0, 25225.0, 2000],
            ]
            quote_payload_morning = {
                "data": {
                    "NSE_INDEX:Nifty 50": {
                        "last_price": 25270.00,
                        "net_change": 125.70,
                        "ohlc": {"open": 25215.0, "high": 25280.0, "low": 25200.0, "close": 25270.0},
                    }
                }
            }

            def mock_get_morning(url, *args, **kwargs):
                mock = MagicMock()
                mock.status_code = 200
                if "market-quote/quotes" in url:
                    mock.json.return_value = quote_payload_morning
                elif "historical-candle/intraday" in url:
                    mock.json.return_value = {"data": {"candles": bar_5m_morning}}
                return mock

            with patch("requests.get", side_effect=mock_get_morning):
                grid_morning = compute_official_rbfn_boundaries(spots={"NIFTY": 25270.0}, token="mock_token")

            assert os.path.exists(cache_file), "Session PIT cache file must be created on first frozen run"
            assert grid_morning["NIFTY"]["trend_decider"] == 25215.0
            assert grid_morning["NIFTY"]["rp1_upper"] == 25317.0
            assert grid_morning["NIFTY"]["rp1_lower"] == 25113.0
            assert grid_morning["NIFTY"]["equilibrium_bar_frozen"] is True

            # 2. Midday restart at 14:32: Market has drifted dramatically to 25800.0
            # Even if quote API returns 25800 and 1m candles return new midday bars,
            # compute_official_rbfn_boundaries MUST load from cache and return IDENTICAL grid!
            with patch("requests.get", side_effect=RuntimeError("Network must not even be hit for cached symbols!")):
                grid_afternoon = compute_official_rbfn_boundaries(spots={"NIFTY": 25800.0}, token="mock_token")

            assert grid_afternoon["NIFTY"]["trend_decider"] == grid_morning["NIFTY"]["trend_decider"] == 25215.0
            assert grid_afternoon["NIFTY"]["rp1_upper"] == grid_morning["NIFTY"]["rp1_upper"] == 25317.0
            assert grid_afternoon["NIFTY"]["rp1_lower"] == grid_morning["NIFTY"]["rp1_lower"] == 25113.0
            assert grid_afternoon["NIFTY"]["target_strike"] == grid_morning["NIFTY"]["target_strike"]
            assert grid_afternoon["NIFTY"]["bias"] == grid_morning["NIFTY"]["bias"]

        finally:
            if os.path.exists(cache_file):
                os.remove(cache_file)

    def test_gap_regime_preservation_against_5m_wick_distortion(self):
        """Prove that on gap days (gap >= 0.25 * atr), Trend Decider anchors to opening body equilibrium
        and is protected from extreme upper wicks pulling TD artificially higher.
        """
        strat = OptionMateRBFNStrategy(symbol="NIFTY", step_size=50)
        # NIFTY gap up:
        # spot_open = 25215.0, prev_close = 25144.30 => gap = +70.70
        # atr_14 = 150.0 => gap_threshold = 37.5. Since 70.70 >= 37.5, Gap regime holds!
        # Opening 5m candle has a massive 75-pt wick spiked up to 25290.0, close = 25275.0
        bar_5m_wick = GoldenCandle.create(
            open=25215.0,
            high=25290.0,
            low=25200.0,
            close=25275.0,
            volume=50000.0,
        )

        grid = strat.compute_daily_grid(
            date="2026-11-16",
            spot_open=25215.0,
            prev_close=25144.30,
            atr_14=150.0,
            vix=14.0,
            bar_5m_equilibrium=bar_5m_wick,
            symbol="NIFTY",
        )

        # In Gap regime, Trend Decider must anchor to opening body equilibrium (25215.0)
        # NOT wick-distorted (25215 + 25290 + 25200 + 25275)/4 = 25245.0
        assert grid.trend_decider == 25215.0
        # Calibrated NIFTY base_step = 102.0
        assert grid.rp1_upper == 25317.0
        assert grid.rp1_lower == 25113.0
        assert grid.call_strike == 25300.0
        assert grid.put_strike == 25100.0
        assert grid.read_only is True
        assert grid.is_order_action is False
        assert grid.broker_api_called is False
        assert grid.allowed_for_live_execution is False
