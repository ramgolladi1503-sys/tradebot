from __future__ import annotations

import runpy
from pathlib import Path

import pytest


def test_register_model_cli_writes_admission_report(tmp_path, monkeypatch, capsys):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model-bytes")
    reports = []

    def _write_admission_report(report, output_path=None):
        reports.append(("admit", report))
        out = tmp_path / "admission.json"
        out.write_text("{}")
        return out

    monkeypatch.setattr("core.model_registry.write_admission_report", _write_admission_report)
    monkeypatch.setattr("core.model_registry.write_rejection_artifact", lambda report, output_path=None: tmp_path / "reject.json")
    monkeypatch.setattr("core.model_registry.register_model", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr("core.model_registry.admit_model_entry", lambda entry: entry)
    monkeypatch.setattr("sys.argv", ["register_model.py", "--type", "xgb", "--path", str(model_path), "--metric", "train_rows=10"])

    runpy.run_path(str(Path("scripts/register_model.py")), run_name="__main__")
    out = capsys.readouterr().out
    assert "admission_report_path" in out
    assert reports


def test_activate_model_cli_rejects_missing_governance(tmp_path, monkeypatch):
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model-bytes")
    monkeypatch.setattr("core.model_registry.get_active_entry", lambda _type: None)
    monkeypatch.setattr(
        "core.model_registry.build_admission_report",
        lambda **kwargs: {
            "schema_version": 1,
            "timestamp": "2026-01-01T00:00:00Z",
            "model_type": kwargs["model_type"],
            "path": str(kwargs["path"]),
            "hash": "abc123",
            "status": "active",
            "admitted": False,
            "reason": "MODEL_ENTRY_MISSING_PROVENANCE",
            "metrics": {},
            "governance": {},
            "checks": {},
        },
    )
    monkeypatch.setattr("core.model_registry.write_rejection_artifact", lambda report, output_path=None: tmp_path / "reject.json")
    monkeypatch.setattr("core.model_registry.write_admission_report", lambda report, output_path=None: tmp_path / "admit.json")
    monkeypatch.setattr("core.model_registry.activate_model", lambda *args, **kwargs: {"active": True})
    monkeypatch.setattr("sys.argv", ["activate_model.py", "--type", "xgb", "--path", str(model_path)])

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path("scripts/activate_model.py")), run_name="__main__")
    assert exc.value.code == 2
