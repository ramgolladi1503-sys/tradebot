import pandas as pd
from pathlib import Path

from ml.alpha_factory import run_alpha_factory


def test_alpha_factory_smoke(tmp_path):
    df = pd.DataFrame(
        {
            "ts": [
                "2026-01-01T09:15:00+00:00",
                "2026-01-02T09:15:00+00:00",
                "2026-01-03T09:15:00+00:00",
                "2026-01-04T09:15:00+00:00",
                "2026-01-05T09:15:00+00:00",
                "2026-01-06T09:15:00+00:00",
                "2026-01-07T09:15:00+00:00",
                "2026-01-08T09:15:00+00:00",
                "2026-01-09T09:15:00+00:00",
                "2026-01-10T09:15:00+00:00",
            ],
            "symbol": ["NIFTY"] * 10,
            "spread_pct": [0.01] * 10,
            "depth_imbalance": [0.1] * 10,
            "quote_age_sec": [1.0] * 10,
            "regime_entropy": [0.5] * 10,
            "shock_score": [0.1] * 10,
            "uncertainty_index": [0.1] * 10,
            "score_0_100": [60, 62, 58, 65, 63, 61, 59, 64, 66, 62],
            "ensemble_proba": [0.55, 0.57, 0.52, 0.6, 0.58, 0.56, 0.53, 0.61, 0.62, 0.57],
            "ensemble_uncertainty": [0.2] * 10,
            "pnl_15m": [10, -5, 3, -2, 7, -1, 4, -3, 6, -4],
            "primary_regime": ["RANGE"] * 10,
        }
    )
    truth = tmp_path / "truth.parquet"
    df.to_parquet(truth, index=False)
    report = tmp_path / "report.json"
    result = run_alpha_factory(truth_path=truth, days=90, dry_run=True, out_report=report, min_rows=5)
    assert report.exists()
    assert result.best_name in {"logreg", "gboost"}
