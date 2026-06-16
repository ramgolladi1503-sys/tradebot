from __future__ import annotations

import json
from pathlib import Path

from scripts.run_offline_aeron7_research import load_offline_research_config


def test_load_offline_research_config(tmp_path):
    config = tmp_path / "aeron7.json"
    config.write_text(
        json.dumps(
            {
                "source_root": "data/aeron7_data",
                "work_dir": ".runtime/aeron7_research",
                "symbols": ["NIFTY_F1"],
                "horizons_bars": [1, 3],
                "train_window_days": 60,
                "test_window_days": 10,
                "step_days": 10,
                "model_family": "random_forest",
            }
        ),
        encoding="utf-8",
    )

    payload = load_offline_research_config(config)
    assert payload["source_root"] == "data/aeron7_data"
    assert payload["work_dir"] == ".runtime/aeron7_research"
    assert payload["symbols"] == ["NIFTY_F1"]
    assert payload["horizons_bars"] == [1, 3]
    assert payload["model_family"] == "random_forest"
