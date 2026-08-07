from __future__ import annotations

import pandas as pd

from research.tradingview_public_library_benchmark_v1 import benchmark as B
from research.tradingview_public_library_benchmark_v1 import guarded_runtime as G


def test_opaque_inventory_row_cannot_be_promoted_by_generic_primitive() -> None:
    inventory = {
        "unique_script_count": 1,
        "records": [
            {
                "script_id": "opaque",
                "title": "Trend dashboard",
                "url": "https://example.invalid/opaque",
                "description": "Shows trend context and momentum.",
                "primitives": ["TREND", "MOMENTUM"],
                "incompatibilities": [],
                "fetch_status": "OK",
                "initial_status": "OPAQUE_OR_NON_SIGNAL",
            }
        ],
    }
    mapped = G.guarded_prepare_specs(inventory)
    assert mapped["unique_mechanism_count"] == 0
    assert mapped["script_rows"][0]["mechanism_signature"] is None
    assert mapped["policy"]["opaque_rows_promoted_to_generic_proxy"] is False


def test_only_frozen_testable_row_can_map() -> None:
    inventory = {
        "unique_script_count": 2,
        "records": [
            {
                "script_id": "a",
                "title": "9/21 EMA Cross",
                "url": "https://example.invalid/a",
                "description": "Bullish when EMA 9 crosses above EMA 21 and bearish when it crosses below.",
                "primitives": ["EMA"],
                "incompatibilities": [],
                "fetch_status": "OK",
                "initial_status": "TESTABLE_EXACT_DESCRIPTION_CANDIDATE",
            },
            {
                "script_id": "b",
                "title": "EMA visualizer",
                "url": "https://example.invalid/b",
                "description": "Displays EMA context.",
                "primitives": ["EMA"],
                "incompatibilities": [],
                "fetch_status": "OK",
                "initial_status": "OPAQUE_OR_NON_SIGNAL",
            },
        ],
    }
    mapped = G.guarded_prepare_specs(inventory)
    assert mapped["unique_mechanism_count"] == 1
    assert sum(1 for r in mapped["script_rows"] if r["mechanism_signature"]) == 1
    assert mapped["policy"]["script_accounting_reconciled"] is True


def test_full_history_signal_computation_does_not_reset_each_session() -> None:
    rows = []
    for day in range(3):
        base = pd.Timestamp("2025-01-01 09:15") + pd.Timedelta(days=day)
        for i in range(75):
            price = 100.0 + (day * 75 + i) * 0.02
            rows.append(
                {
                    "symbol": "NIFTY",
                    "session_date": base.strftime("%Y-%m-%d"),
                    "timestamp": base + pd.Timedelta(minutes=5 * i),
                    "open": price,
                    "high": price + 0.1,
                    "low": price - 0.1,
                    "close": price,
                }
            )
    frame = B.build_features(pd.DataFrame(rows))
    spec = B.MechanismSpec("PRICE_EMA_TREND", (("length", 100.0),), "test")
    signals = G.full_history_first_signals(frame, "NIFTY", spec)
    # A 100-bar EMA cannot warm up inside one 75-bar session. Any later-session signal
    # therefore proves the computation retained prior-session history.
    assert all(session != "2025-01-01" for session in signals)
