from __future__ import annotations

from research.tradingview_public_library_benchmark_v1 import benchmark as B
from research.tradingview_public_library_benchmark_v1 import parameter_guard as P


def _record(title: str, description: str, primitives: list[str]):
    return {
        "script_id": "x",
        "title": title,
        "description": description,
        "primitives": primitives,
        "incompatibilities": [],
        "fetch_status": "OK",
        "initial_status": "TESTABLE_EXACT_DESCRIPTION_CANDIDATE",
    }


def test_9_21_lengths_before_ema_are_preserved() -> None:
    record = _record(
        "9/21 EMA CROSS",
        "The 9 EMA crossing above the 21 EMA is bullish and crossing below is bearish.",
        ["EMA", "MOMENTUM"],
    )
    spec, status = P.guarded_map_record(record)
    assert status == "TESTABLE_CANONICAL_MECHANISM"
    assert spec is not None
    assert spec.family == "EMA_CROSS"
    assert spec.param_dict() == {"fast": 9.0, "slow": 21.0}


def test_30_minute_orb_is_not_silently_tested_as_15_minute() -> None:
    record = _record(
        "ES ORB 15min RTH",
        "This strategy trades breaks of the first 30-minute regular-session range.",
        ["OPENING_RANGE", "BREAKOUT"],
    )
    spec, status = P.guarded_map_record(record)
    assert spec is None
    assert status == "OPENING_RANGE_WINDOW_NOT_IMPLEMENTED"
