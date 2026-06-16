from __future__ import annotations

import json
from pathlib import Path

from scripts.run_offline_aeron7_research import run_offline_aeron7_research


def test_run_offline_aeron7_research_end_to_end(tmp_path):
    source_root = tmp_path / "aeron7"
    rows = []
    for day in range(1, 9):
        input_dir = source_root / "2022" / "MAR" / f"{day:02d}MAR"
        input_dir.mkdir(parents=True, exist_ok=True)
        day_rows = []
        for idx in range(30):
            minute = 15 + (idx % 45)
            close = 16505 + (day * 10) + idx + (1 if idx % 4 == 0 else -1)
            day_rows.append(
                f"NIFTY,202203{day:02d},09:{minute:02d},{16500 + idx},{16510 + idx},{16495 + idx},{close},{1000 + idx},0"
            )
        (input_dir / "NIFTY_F1.txt").write_text("\n".join(day_rows))

    work_dir = tmp_path / "research"
    report = run_offline_aeron7_research(
        source_root=source_root,
        work_dir=work_dir,
        symbols=["NIFTY_F1"],
        horizons_bars=[1, 3],
        train_window_days=5,
        test_window_days=2,
        step_days=2,
        model_family="logistic",
    )

    summary_path = Path(report["summary_path"])
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text())
    assert payload["convert_report"]["written_files"]
    assert payload["label_reports"]
    assert payload["ev_reports"]
    assert payload["walk_forward_report"] is not None
    assert payload["regime_report"] is not None
    assert (work_dir / "canonical" / "NIFTY_F1_intraday.csv").exists()
    assert (work_dir / "labels" / "NIFTY_F1_multi_horizon.csv").exists()
    assert (work_dir / "ev_labels" / "NIFTY_F1_ev.csv").exists()
    assert list((work_dir / "models").glob("*.joblib"))
    assert list((work_dir / "walk_forward").glob("walk_forward_latest.json"))
    assert list((work_dir / "regime_reports").glob("regime_model_comparison.json"))
    assert list((work_dir / "regime_reports").glob("regime_model_comparison.csv"))
    assert list((work_dir / "regime_reports").glob("regime_model_comparison.md"))
