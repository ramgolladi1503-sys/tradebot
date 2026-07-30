from pathlib import Path

from core.runtime_authority_audit import audit_runtime_authority, inspect_module


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_orchestrator_authority_audit_detects_scale_and_shadowing():
    report = inspect_module(REPO_ROOT / "core" / "orchestrator.py")
    assert report.line_count > 8000
    assert "Orchestrator" in report.class_names
    assert "_trade_attr" in report.locally_redefined_imports
    assert "_candidate_origin" in report.locally_redefined_imports
    assert "_is_synthetic_candidate" in report.locally_redefined_imports
    assert report.file_write_references


def test_trade_builder_authority_audit_detects_scale_and_mixed_responsibility():
    report = inspect_module(REPO_ROOT / "strategies" / "trade_builder.py")
    assert report.line_count > 10000
    assert "TradeBuilder" in report.class_names
    assert report.file_write_references


def test_combined_audit_is_read_only_and_deterministic():
    paths = ("core/orchestrator.py", "strategies/trade_builder.py")
    first = audit_runtime_authority(REPO_ROOT, paths)
    second = audit_runtime_authority(REPO_ROOT, paths)
    assert first == second
    assert first["read_only"] is True
    assert first["summary"]["module_count"] == 2
    assert first["summary"]["total_lines"] > 18000
    assert first["summary"]["locally_redefined_import_count"] >= 3


def test_audit_does_not_import_runtime_modules(monkeypatch):
    imported = []

    def fail_import(*args, **kwargs):
        imported.append((args, kwargs))
        raise AssertionError("runtime import attempted")

    monkeypatch.setattr("builtins.__import__", fail_import)
    source = (REPO_ROOT / "core" / "orchestrator.py").read_text(encoding="utf-8")
    assert "class Orchestrator" in source
    assert imported == []
