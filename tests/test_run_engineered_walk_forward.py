from __future__ import annotations

import pandas as pd

from scripts.run_engineered_walk_forward import run_engineered_walk_forward


def test_run_engineered_walk_forward_runs(tmp_path):
    src = tmp_path / "hist.csv"
    rows = []
    for idx in range(120):
        rows.append(
            {
                "timestamp": f"2022-01-{1 + idx // 6:02d}T09:{15 + (idx % 6):02d}:00+00:00",
                "open": 100 + idx,
                "high": 101 + idx,
                "low": 99 + idx,
                "close": 100.5 + idx,
                "volume": 1000 + idx * 10,
            }
        )
    pd.DataFrame(rows).to_csv(src, index=False)

    summary = run_engineered_walk_forward(
        input_csv=src,
        output_dir=tmp_path / "wf",
        train_window_days=5,
        test_window_days=2,
        step_days=2,
    )

    assert summary["config"]["window_count"] > 0
    assert "avg_return" in summary["aggregate"]
