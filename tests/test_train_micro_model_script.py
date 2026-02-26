from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "models" / "train_micro_model.py"


def _run(args: list[str]):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _last_json(stdout: str) -> dict:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def test_train_micro_model_script_help():
    result = _run(["--help"])
    assert result.returncode == 0
    assert "Train microstructure model" in result.stdout


def test_train_micro_model_script_dry_run_from_csv(tmp_path):
    csv_path = tmp_path / "ticks.csv"
    rows = 30
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-02-24 09:15:00", periods=rows, freq="min"),
            "close": [100.0 + (i * 0.08) + (0.1 if i % 2 == 0 else -0.03) for i in range(rows)],
            "volume": [10 + (i % 7) for i in range(rows)],
        }
    )
    df.to_csv(csv_path, index=False)

    result = _run(
        [
            "--csv-path",
            str(csv_path),
            "--dry-run",
            "--horizon",
            "1",
            "--threshold",
            "0.0001",
            "--min-rows",
            "5",
        ]
    )
    assert result.returncode == 0
    payload = _last_json(result.stdout)
    assert payload["status"] == "DRY_RUN_OK"
    assert int(payload["rows"]) >= 5


def test_train_micro_model_script_invalid_csv_path_fails_cleanly(tmp_path):
    missing = tmp_path / "missing.csv"
    result = _run(["--csv-path", str(missing), "--dry-run"])
    assert result.returncode == 2
    payload = _last_json(result.stdout)
    assert payload["status"] == "NO_DATA"
    assert "No training data found" in str(payload.get("reason") or "")


def test_train_micro_model_script_sklearn_backend_trains_and_writes_pkl(tmp_path):
    csv_path = tmp_path / "ticks_train.csv"
    model_path = tmp_path / "microstructure_model.h5"
    fi_path = tmp_path / "micro_feature_importance.csv"
    rows = 80
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-02-24 09:15:00", periods=rows, freq="min"),
            "close": [100.0 + (i * 0.05) for i in range(rows)],
            "volume": [100 + (i % 9) for i in range(rows)],
            "oi": [1000 + (i % 13) for i in range(rows)],
            "target": [1 if (i % 3 == 0) else 0 for i in range(rows)],
        }
    )
    df.to_csv(csv_path, index=False)

    result = _run(
        [
            "--csv-path",
            str(csv_path),
            "--backend",
            "sklearn",
            "--model-path",
            str(model_path),
            "--feature-importance-path",
            str(fi_path),
            "--min-rows",
            "20",
        ]
    )
    assert result.returncode == 0
    payload = _last_json(result.stdout)
    assert payload["status"] == "TRAINED"
    assert payload["backend_used"] == "sklearn"
    assert payload["model_path"].endswith(".pkl")
    assert Path(payload["model_path"]).exists()
    assert fi_path.exists()
