from __future__ import annotations

import pandas as pd

from scripts.build_next_bar_labels import build_next_bar_labels


def test_build_next_bar_labels_creates_labels(tmp_path):
    src = tmp_path / "nifty.csv"
    pd.DataFrame(
        [
            {"timestamp": "2022-03-01T09:15:00+00:00", "open": 1, "high": 2, "low": 1, "close": 10, "volume": 100},
            {"timestamp": "2022-03-01T09:20:00+00:00", "open": 2, "high": 3, "low": 2, "close": 12, "volume": 120},
            {"timestamp": "2022-03-01T09:25:00+00:00", "open": 3, "high": 4, "low": 3, "close": 11, "volume": 130},
        ]
    ).to_csv(src, index=False)

    out = tmp_path / "labels.csv"
    report = build_next_bar_labels(input_csv=src, output_csv=out, horizon_bars=1)

    assert out.exists()
    assert report["rows"] == 2
    frame = pd.read_csv(out)
    assert "future_close" in frame.columns
    assert "future_return" in frame.columns
    assert "label_up" in frame.columns
    assert "regime_tag" in frame.columns
    assert "session_bucket" in frame.columns
    assert frame["label_up"].tolist() == [1, 0]


def test_build_next_bar_labels_requires_canonical_columns(tmp_path):
    src = tmp_path / "bad.csv"
    pd.DataFrame([{"timestamp": "2022-03-01T09:15:00+00:00", "close": 10}]).to_csv(src, index=False)
    out = tmp_path / "labels.csv"

    try:
        build_next_bar_labels(input_csv=src, output_csv=out, horizon_bars=1)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing_required_columns" in str(exc)
