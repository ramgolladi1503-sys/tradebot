from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from models import train_micro_model as tm


def test_train_micro_model_emits_admission_metadata(tmp_path, monkeypatch):
    df = pd.DataFrame(
        [
            {
                "timestamp": f"2026-01-01 09:{15 + i:02d}:00",
                "close": 100.0 + i,
                "volume": 10.0 + i,
                "oi": 5.0 + i,
                "target": i % 2,
            }
            for i in range(24)
        ]
    )

    csv_path = tmp_path / "micro.csv"
    df.to_csv(csv_path, index=False)
    model_path = tmp_path / "microstructure_model.pkl"
    fi_path = tmp_path / "feature_importance.csv"
    metadata_path = tmp_path / "microstructure_model.json"

    code, report = tm._train(
        tm.parse_args(
            [
                "--csv-path",
                str(csv_path),
                "--model-path",
                str(model_path),
                "--feature-importance-path",
                str(fi_path),
                "--min-rows",
                "4",
                "--backend",
                "sklearn",
            ]
        )
    )

    assert code == 0
    assert report["status"] == "TRAINED"
    assert report["split_strategy"] == "time_ordered_holdout"
    assert report["governance_ready"] is False
    assert Path(report["metadata_path"]).exists()
    metadata = json.loads(Path(report["metadata_path"]).read_text())
    assert metadata["provenance"]["source"].startswith("csv:")
    assert metadata["admission"]["min_val_accuracy"] >= 0.55
    assert report["admission_report"]["admitted"] is False
