from __future__ import annotations

import pandas as pd

from scripts.build_trade_ev_labels import build_trade_ev_labels


def test_build_trade_ev_labels_adds_expected_value_columns(tmp_path):
    src = tmp_path / "nifty.csv"
    pd.DataFrame(
        [
            {"timestamp": "2022-03-01T09:15:00+00:00", "open": 1, "high": 2, "low": 1, "close": 10, "volume": 100},
            {"timestamp": "2022-03-01T09:20:00+00:00", "open": 2, "high": 3, "low": 2, "close": 12, "volume": 120},
            {"timestamp": "2022-03-01T09:25:00+00:00", "open": 3, "high": 4, "low": 3, "close": 9, "volume": 130},
        ]
    ).to_csv(src, index=False)

    out = tmp_path / "ev_labels.csv"
    report = build_trade_ev_labels(input_csv=src, output_csv=out, horizon_bars=1, cost_bps=20.0)

    assert out.exists()
    assert "expected_value" in report["ev_columns"]
    assert "expected_value_bps" in report["ev_columns"]
    frame = pd.read_csv(out)
    assert "expected_value" in frame.columns
    assert "expected_value_bps" in frame.columns
    assert "ev_positive" in frame.columns
    assert frame["cost_bps"].tolist() == [20.0, 20.0]
    assert frame["ev_positive"].tolist() == [1, 0]
