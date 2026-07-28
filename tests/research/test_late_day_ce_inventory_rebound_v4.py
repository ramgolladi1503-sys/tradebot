from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.audit_late_day_ce_inventory_rebound_v4 import (
    attach_exact_future_prices,
    metrics,
    oof_gate,
    profit_factor,
    two_half_positive,
)


def test_profit_factor_uses_positive_over_absolute_negative() -> None:
    assert profit_factor([3.0, 2.0, -1.0, -1.5]) == pytest.approx(2.0)


def test_exact_future_price_attachment_uses_timestamp_offsets(
    tmp_path: Path,
) -> None:
    timestamps = pd.date_range(
        "2026-01-05 09:15:00",
        periods=22,
        freq="min",
        tz="Asia/Kolkata",
    )
    raw = pd.DataFrame(
        {
            "expired_instrument_key": ["contract-a"] * len(timestamps),
            "timestamp": timestamps,
            "session": ["2026-01-05"] * len(timestamps),
            "open": np.arange(100.0, 122.0),
            "close": np.arange(100.5, 122.5),
        }
    )
    event_path = tmp_path / "events.parquet"
    raw.to_parquet(event_path, index=False)
    ledger = pd.DataFrame(
        {
            "expired_instrument_key": ["contract-a"],
            "session_id": ["2026-01-05"],
            "timestamp": [timestamps[0]],
        }
    )

    attached = attach_exact_future_prices(ledger, event_path)

    assert attached.loc[0, "future_open_1"] == pytest.approx(101.0)
    assert attached.loc[0, "future_close_5"] == pytest.approx(105.5)
    assert attached.loc[0, "future_close_10"] == pytest.approx(110.5)
    assert attached.loc[0, "future_close_15"] == pytest.approx(115.5)
    assert attached.loc[0, "future_close_20"] == pytest.approx(120.5)


def test_oof_gate_accepts_distributed_positive_economics() -> None:
    net = np.asarray(([2.0] * 30) + ([-1.0] * 10), dtype=float)
    frame = pd.DataFrame(
        {
            "net_5m_pct": net,
            "stress_5m_pct": net - 0.9,
            "fold_id": np.repeat(
                ["fold_1", "fold_2", "fold_3", "fold_4"],
                10,
            ),
        }
    )
    metric = metrics(frame, 5)

    assert metric.positive_folds == 4
    assert metric.remove_top_two_profit_factor is not None
    assert oof_gate(metric) is True


def test_two_half_positive_rejects_one_negative_half() -> None:
    frame = pd.DataFrame(
        {
            "session_id": [f"s{index:02d}" for index in range(10)],
            "timestamp": pd.date_range(
                "2026-01-01",
                periods=10,
                freq="D",
                tz="UTC",
            ),
            "net_5m_pct": ([-1.0] * 5) + ([2.0] * 5),
        }
    )
    assert two_half_positive(frame, 5) is False
