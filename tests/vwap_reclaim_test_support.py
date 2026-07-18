from __future__ import annotations
"""Evidence support helpers for VWAP reclaim tests."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyContext


IST = ZoneInfo("Asia/Kolkata")
SESSION_DATE = "2026-07-14"
SESSION_OPEN = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
EVALUATION_CUTOFF = (SESSION_OPEN + timedelta(minutes=3)).timestamp()

assert EVALUATION_CUTOFF > 0


def bullish_history(*, include_future: bool = False) -> list[dict[str, object]]:
    bars = [
        _bar(0, 22500.0, 22520.0, 22490.0, 22490.0),
        _bar(1, 22535.0, 22550.0, 22530.0, 22540.0),
        _bar(2, 22590.0, 22610.0, 22550.0, 22580.0),
    ]
    if include_future:
        bars.append(_bar(3, 22610.0, 22690.0, 22605.0, 22680.0, volume=5000.0))
    return bars


def bearish_history(*, include_future: bool = False) -> list[dict[str, object]]:
    bars = [
        _bar(0, 22580.0, 22590.0, 22565.0, 22585.0),
        _bar(1, 22550.0, 22552.0, 22528.0, 22540.0),
        _bar(2, 22500.0, 22510.0, 22490.0, 22500.0),
    ]
    if include_future:
        bars.append(_bar(3, 22484.0, 22490.0, 22450.0, 22455.0, volume=5000.0))
    return bars


def vwap_reclaim_context(
    *,
    bullish: bool = True,
    history: list[dict[str, object]] | None = None,
    ts_epoch: float | None = None,
    spot_ltp: float | None = None,
    vwap: float = 22540.0,
    vwap_slope: float | None = 0.04,
    volume_z: float | None = 1.2,
    previous_spot_ltp: float | None = None,
    metadata: dict[str, object] | None = None,
) -> StrategyContext:
    if history is None:
        history = bullish_history() if bullish else bearish_history()
    if ts_epoch is None:
        ts_epoch = (SESSION_OPEN + timedelta(minutes=3)).timestamp()
    if spot_ltp is None:
        spot_ltp = 22610.0 if bullish else 22485.0
    if previous_spot_ltp is None:
        previous_spot_ltp = 22495.0 if bullish else 22585.0

    payload = {
        "symbol": "NIFTY",
        "ts_epoch": ts_epoch,
        "spot_ltp": spot_ltp,
        "vwap": vwap,
        "vwap_slope": vwap_slope,
        "volume_z": volume_z,
        "option_ce_ltp": 125.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 10.0 if bullish else 0.0,
        "pe_premium_change": 0.0 if bullish else 11.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 35,
        "minutes_to_close": 280,
        "completed_bar_history": history,
        "metadata": {
            "previous_spot_ltp": previous_spot_ltp,
            "vwap_reclaim_up_confirmed": bullish,
            "vwap_reclaim_down_confirmed": not bullish,
        },
    }
    if metadata:
        payload["metadata"].update(metadata)
    return StrategyContext(**payload)


def runtime_truth_payload(
    *,
    bullish: bool = True,
    history: list[dict[str, object]] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    if history is None:
        history = bullish_history() if bullish else bearish_history()
    payload = {
        "symbol": "NIFTY",
        "spot": 22610.0 if bullish else 22485.0,
        "ltp": 22610.0 if bullish else 22485.0,
        "prev_ltp": 22495.0 if bullish else 22585.0,
        "vwap": 22540.0,
        "vwap_slope": 0.04 if bullish else -0.04,
        "volume_z": 1.2,
        "vol_z": 1.2,
        "minutes_since_open": 35,
        "market_open": True,
        "segment": "NSE_FNO",
        "timestamp_ist": "2026-07-14T09:18:00+05:30",
        "ltp_ts_epoch": EVALUATION_CUTOFF,
        "completed_bar_history": history,
        "completed_bar_history_provenance": {
            "source_component": "tests.vwap_reclaim_test_support",
            "source_field": "completed_bar_history",
            "status": "TRUTHFUL",
            "source_event_timestamp": history[-1]["bar_end_timestamp"],
            "receipt_timestamp": history[-1]["receipt_timestamp"],
            "symbol": "NIFTY",
            "session_date": SESSION_DATE,
            "timeframe": "1m",
        },
        "option_chain_health": {"quote_age_sec": 0.4},
        "quote_source": "live_option_tick",
        "option_chain": [
            {
                "strike": 22600.0,
                "type": "CE",
                "ltp": 120.0,
                "spread_pct": 0.8,
                "bid_qty": 600.0,
                "ask_qty": 600.0,
                "ltp_change": 10.0 if bullish else 0.0,
            },
            {
                "strike": 22600.0,
                "type": "PE",
                "ltp": 90.0,
                "spread_pct": 0.8,
                "bid_qty": 600.0,
                "ask_qty": 600.0,
                "ltp_change": 0.0 if bullish else 11.0,
            },
        ],
        "metadata": {
            "previous_spot_ltp": 22495.0 if bullish else 22585.0,
            "vwap_reclaim_up_confirmed": bullish,
            "vwap_reclaim_down_confirmed": not bullish,
            "strategy_context_truth": {
                "vwap": 22540.0,
                "vwap_slope": 0.04 if bullish else -0.04,
                "completed_bar_history": history,
            },
            "strategy_context_provenance": {
                "completed_bar_history": {
                    "source_component": "tests.vwap_reclaim_test_support",
                    "source_field": "completed_bar_history",
                    "status": "TRUTHFUL",
                }
            },
            "strategy_context_missing": {},
        },
    }
    if metadata:
        payload["metadata"].update(metadata)
    return payload


def _bar(
    offset_minutes: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    volume: float = 1000.0,
) -> dict[str, object]:
    start = SESSION_OPEN + timedelta(minutes=offset_minutes)
    end = start + timedelta(minutes=1)
    return {
        "symbol": "NIFTY",
        "session_date": SESSION_DATE,
        "timeframe": "1m",
        "bar_start_timestamp": start.isoformat(),
        "bar_end_timestamp": end.isoformat(),
        "ts": start.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source": "unit_test",
        "source_timestamp": end.isoformat(),
        "receipt_timestamp": (end + timedelta(seconds=1)).isoformat(),
        "is_complete": True,
    }
