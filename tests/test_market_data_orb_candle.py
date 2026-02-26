from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import config as cfg
from core import market_data


IST = ZoneInfo("Asia/Kolkata")


def _bar(ts: datetime, o: float, h: float, l: float, c: float) -> dict:
    return {"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": 100}


def test_orb_candle_bias_pending_neutral_up_down(monkeypatch):
    monkeypatch.setattr(cfg, "ORB_WINDOW_MIN", 5, raising=False)
    monkeypatch.setattr(cfg, "ORB_BREAK_BUFFER_PCT", 0.0005, raising=False)

    base = datetime(2026, 2, 24, 9, 15, tzinfo=IST)
    seed = [
        _bar(base + timedelta(minutes=0), 100, 101, 99, 100),
        _bar(base + timedelta(minutes=1), 100, 102, 98, 101),
        _bar(base + timedelta(minutes=2), 101, 103, 97, 100),
    ]

    pending = market_data._orb_state_from_candles(  # type: ignore[attr-defined]
        "NIFTY_TEST_ORB",
        seed,
        now_dt=base + timedelta(minutes=3),
        segment="NSE_FNO",
        market_open=True,
    )
    assert pending["bias"] == "PENDING"

    window_full = seed + [
        _bar(base + timedelta(minutes=3), 100, 104, 96, 100),
        _bar(base + timedelta(minutes=4), 100, 105, 95, 100),
        _bar(base + timedelta(minutes=5), 100, 104, 96, 100),
    ]
    neutral = market_data._orb_state_from_candles(  # type: ignore[attr-defined]
        "BANKNIFTY_TEST_ORB",
        window_full,
        now_dt=base + timedelta(minutes=6),
        segment="NSE_FNO",
        market_open=True,
    )
    assert neutral["bias"] == "NEUTRAL"

    up_bars = list(window_full) + [_bar(base + timedelta(minutes=6), 100, 107, 100, 106)]
    up = market_data._orb_state_from_candles(  # type: ignore[attr-defined]
        "SENSEX_TEST_ORB_UP",
        up_bars,
        now_dt=base + timedelta(minutes=7),
        segment="NSE_FNO",
        market_open=True,
    )
    assert up["bias"] == "UP"

    down_bars = list(window_full) + [_bar(base + timedelta(minutes=6), 100, 100, 93, 94)]
    down = market_data._orb_state_from_candles(  # type: ignore[attr-defined]
        "SENSEX_TEST_ORB_DOWN",
        down_bars,
        now_dt=base + timedelta(minutes=7),
        segment="NSE_FNO",
        market_open=True,
    )
    assert down["bias"] == "DOWN"
