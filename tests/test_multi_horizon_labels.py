from __future__ import annotations

import pandas as pd

from scripts.build_next_bar_labels import build_multi_horizon_labels


def test_build_multi_horizon_labels_creates_multiple_targets(tmp_path):
    src = tmp_path / "nifty.csv"
    pd.DataFrame(
        [
            {"timestamp": "2022-03-01T09:15:00+00:00", "open": 1, "high": 2, "low": 1, "close": 10, "volume": 100},
            {"timestamp": "2022-03-01T09:20:00+00:00", "open": 2, "high": 3, "low": 2, "close": 12, "volume": 120},
            {"timestamp": "2022-03-01T09:25:00+00:00", "open": 3, "high": 4, "low": 3, "close": 11, "volume": 130},
            {"timestamp": "2022-03-01T09:30:00+00:00", "open": 4, "high": 5, "low": 4, "close": 13, "volume": 140},
        ]
    ).to_csv(src, index=False)

    out = tmp_path / "labels.csv"
    report = build_multi_horizon_labels(input_csv=src, output_csv=out, horizons_bars=[1, 2])

    assert out.exists()
    assert report["rows"] == 2
    frame = pd.read_csv(out)
    assert "label_up_1" in frame.columns
    assert "label_up_2" in frame.columns
    assert "regime_tag" in frame.columns
    assert "session_bucket" in frame.columns
    assert report["label_columns"] == ["label_up_1", "label_up_2"]
