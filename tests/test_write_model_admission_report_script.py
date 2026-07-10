from __future__ import annotations

import runpy
from pathlib import Path


def test_write_model_admission_report_script_writes_report(tmp_path, monkeypatch, capsys):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model-bytes")
    monkeypatch.setattr(
        "sys.argv",
        [
            "write_model_admission_report.py",
            "--type",
            "xgb",
            "--path",
            str(model_path),
            "--feature",
            "x",
            "--train-rows",
            "10",
            "--regime-coverage",
            "TREND=0.6",
            "--regime-coverage",
            "RANGE=0.4",
            "--min-regime-coverage",
            "0.2",
        ],
    )

    try:
        runpy.run_path(str(Path("scripts/write_model_admission_report.py")), run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "report_path" in out
