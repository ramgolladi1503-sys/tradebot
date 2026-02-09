import json
from pathlib import Path

import pandas as pd

from ml.truth_dataset import build_truth_dataset


def test_truth_dataset_leakage(tmp_path: Path):
    jsonl = tmp_path / "decisions.jsonl"
    rows = [
        {
            "trade_id": "T1",
            "ts": "2026-01-01T10:00:00",
            "symbol": "NIFTY",
            "strategy_id": "S1",
            "pnl_horizon_15m": 10.0,
            "outcome_ts": "2026-01-01T09:59:59",
        }
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows))
    out_parquet = tmp_path / "truth.parquet"
    df, report = build_truth_dataset(
        decision_jsonl=jsonl,
        decision_sqlite=tmp_path / "none.db",
        out_parquet=out_parquet,
        out_csv=None,
    )
    assert report["leakage_count"] == 1
    assert bool(df.loc[0, "outcome_missing"]) is True
    assert pd.isna(df.loc[0, "pnl_15m"])
