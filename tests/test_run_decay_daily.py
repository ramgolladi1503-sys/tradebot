from __future__ import annotations

from pathlib import Path

from scripts import run_decay_daily


def test_run_decay_daily_falls_back_to_build_decay_report(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    called = {"dataset": False}

    def _fake_build_dataset():
        called["dataset"] = True

    def _fake_build_report(day: str, out_path: Path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("{}")
        return out_path

    monkeypatch.setattr(run_decay_daily, "build_decay_dataset", _fake_build_dataset)
    monkeypatch.setattr(run_decay_daily.decay_report_module, "build_decay_report", _fake_build_report, raising=True)
    monkeypatch.delattr(run_decay_daily.decay_report_module, "run_decay_report", raising=False)

    result = run_decay_daily.main()

    assert called["dataset"] is True
    assert result["source"] == "build_decay_report"
    assert Path(result["path"]).exists()
