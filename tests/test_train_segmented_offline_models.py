from __future__ import annotations

import pandas as pd

from scripts.train_segmented_offline_models import train_segmented_offline_models


def test_train_segmented_offline_models_writes_session_models(tmp_path):
    src = tmp_path / "labels.csv"
    rows = []
    for idx in range(240):
        hour = 9 + (idx // 80)
        rows.append(
            {
                "timestamp": f"2022-03-01T{hour:02d}:{(idx % 30):02d}:00+00:00",
                "open": 100 + idx,
                "high": 101 + idx,
                "low": 99 + idx,
                "close": 100.5 + idx,
                "volume": 1000 + idx * 10,
                "label_up": int(idx % 2 == 0),
            }
        )
    pd.DataFrame(rows).to_csv(src, index=False)

    out_dir = tmp_path / "models"
    report = train_segmented_offline_models(
        input_csv=src,
        model_dir=out_dir,
        label_column="label_up",
        model_family="logistic",
    )

    assert report["segments"]
    assert (out_dir / "open_logistic.joblib").exists()
