from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODULE = Path(__file__).parents[2] / "scripts" / "run_gravity_well_location_participation_v1.py"
spec = importlib.util.spec_from_file_location("gw", MODULE)
gw = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gw
assert spec.loader is not None
spec.loader.exec_module(gw)


def _ticks(symbol: str, start: str, periods: int, price: float = 24000.0, volume: float = 0.0):
    ts = pd.date_range(start, periods=periods, freq="1min", tz="Asia/Kolkata")
    return pd.DataFrame({"ts": ts.astype(str), "symbol": symbol, "ltp": price + np.arange(periods) * 0.1, "bid": price - 0.5, "ask": price + 0.5, "vol": volume})


def test_missing_index_volume_and_constituents_fail_closed(tmp_path):
    raw = _ticks("NIFTY 50", "2026-07-09 09:15", 376, volume=0)
    ticks = gw.canonicalise_ticks(raw)
    p = tmp_path / "ticks.csv"
    raw.to_csv(p, index=False)
    inv = gw.inventory_source(p, ticks)
    verdict, blockers = gw.choose_verdict([inv], gw.FrozenSpec())
    assert verdict.startswith("DATA_BLOCKED_")
    assert "MISSING_CAUSAL_NIFTY_UNDERLYING_VOLUME" in blockers
    assert "MISSING_NIFTY_CONSTITUENT_PARTICIPATION" in blockers


def test_tick_count_is_not_promoted_to_volume():
    raw = _ticks("NIFTY 50", "2026-07-09 09:15", 60, volume=0)
    bars = gw.resample_index_bars(gw.canonicalise_ticks(raw), 5)
    assert bars.tick_count.max() > 0
    assert (bars.volume.fillna(0) == 0).all()


def test_completed_htf_level_excludes_current_htf_extreme():
    ts = pd.date_range("2026-07-09 09:20", periods=18, freq="5min", tz="Asia/Kolkata")
    bars = pd.DataFrame({"timestamp": ts, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 10.0, "tick_count": 1, "session": "2026-07-09"})
    bars.loc[bars.timestamp == pd.Timestamp("2026-07-09 10:15", tz="Asia/Kolkata"), "high"] = 999.0
    out = gw.completed_htf_levels(bars, 15, 2)
    row = out[out.timestamp == pd.Timestamp("2026-07-09 10:15", tz="Asia/Kolkata")].iloc[0]
    assert row.prior_resistance < 999.0


def test_volume_weighted_center_uses_only_trailing_completed_rows():
    df = pd.DataFrame({"close": [10.0, 20.0, 30.0, 1000.0], "volume": [1.0, 1.0, 2.0, 100.0], "high": [10, 20, 30, 1000], "low": [10, 20, 30, 1000]})
    df = gw.add_causal_atr(df, 1)
    out = gw.add_volume_weighted_center(df, 3)
    assert out.gravity_center.iloc[2] == 22.5
    assert out.gravity_center.iloc[2] != out.gravity_center.iloc[3]


def test_option_parser_supports_observed_drive_formats():
    spaced = gw.parse_option_symbol("NIFTY 24100 PE 14 JUL 26")
    compact = gw.parse_option_symbol("NIFTY2670724150CE")
    assert spaced == {"strike": 24100, "option_type": "PE", "expiry": "2026-07-14"}
    assert compact == {"strike": 24150, "option_type": "CE", "expiry": "2026-07-07"}


def test_option_entry_is_strictly_after_completed_signal():
    signal = pd.Timestamp("2026-07-09 10:00", tz="Asia/Kolkata")
    events = pd.DataFrame([{"family": "CONTROL", "side": "LONG", "signal_time": signal.isoformat(), "session": "2026-07-09", "spot": 24102.0, "authority": "DIAGNOSTIC"}])
    raw = pd.DataFrame({
        "ts": [signal.timestamp(), (signal + pd.Timedelta(seconds=1)).timestamp(), (signal + pd.Timedelta(minutes=10, seconds=1)).timestamp()],
        "symbol": ["NIFTY 24100 CE 14 JUL 26"] * 3,
        "ltp": [100.0, 101.0, 105.0],
        "bid": [99.0, 100.0, 104.0],
        "ask": [101.0, 102.0, 106.0],
        "vol": [1.0, 2.0, 3.0],
    })
    mapped = gw.map_diagnostic_options(events, gw.canonicalise_ticks(raw), gw.FrozenSpec())
    assert len(mapped) == 1
    assert pd.Timestamp(mapped.entry_time.iloc[0]) > signal
    assert mapped.strike_identity.iloc[0] == "EXACT_ATM"


def test_missing_depth_never_creates_option_trade():
    signal = pd.Timestamp("2026-07-09 10:00", tz="Asia/Kolkata")
    events = pd.DataFrame([{"family": "CONTROL", "side": "LONG", "signal_time": signal.isoformat(), "session": "2026-07-09", "spot": 24102.0, "authority": "DIAGNOSTIC"}])
    raw = pd.DataFrame({"ts": [(signal + pd.Timedelta(seconds=1)).timestamp()], "symbol": ["NIFTY 24100 CE 14 JUL 26"], "ltp": [101.0], "bid": [0.0], "ask": [0.0], "vol": [1.0]})
    assert gw.map_diagnostic_options(events, gw.canonicalise_ticks(raw), gw.FrozenSpec()).empty


def test_primary_events_refuse_tick_count_as_volume():
    raw = _ticks("NIFTY 50", "2026-07-09 09:15", 180, volume=0)
    bars = gw.resample_index_bars(gw.canonicalise_ticks(raw), 5)
    constituents = pd.DataFrame({"timestamp": bars.timestamp.repeat(40), "symbol": [f"C{i}" for _ in range(len(bars)) for i in range(40)], "open": 100.0, "high": 101.0, "low": 99.0, "close": 101.0, "session": bars.session.repeat(40)})
    assert gw.generate_primary_events(bars, constituents, gw.FrozenSpec()).empty


def test_primary_events_require_minimum_constituent_count():
    spec2 = gw.FrozenSpec(center_length=3, atr_length=2, cluster_lookback_bars=2, minimum_constituents=40)
    ts = pd.date_range("2026-07-09 09:20", periods=20, freq="5min", tz="Asia/Kolkata")
    close = np.linspace(100, 130, len(ts))
    bars = pd.DataFrame({"timestamp": ts, "open": close-0.2, "high": close+0.5, "low": close-0.5, "close": close, "volume": 100.0, "tick_count": 5, "session": "2026-07-09"})
    rows=[]
    for i,t in enumerate(ts):
        for j in range(10): rows.append({"timestamp":t,"symbol":f"C{j}","open":100+i,"high":101+i,"low":99+i,"close":100+i+j/100,"session":"2026-07-09"})
    assert gw.generate_primary_events(bars, pd.DataFrame(rows), spec2).empty
