from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.critical_module_checker import check_critical_modules


def _write_profile(repo_root):
    cfg = repo_root / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - app.py
critical_modules:
  runtime:
    - app.py
    - core/used.py
    - core/test_only.py
    - core/unreferenced.py
    - core/missing.py
""",
        encoding="utf-8",
    )
    return cfg


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_critical_module_checker_classifies_caller_strength_and_entrypoints(tmp_path):
    _write(tmp_path / "app.py", "from core.used import run\nrun()\n")
    _write(tmp_path / "core" / "used.py", "def run():\n    return None\n")
    _write(
        tmp_path / "core" / "test_only.py",
        "def helper():\n    return None\n",
    )
    _write(tmp_path / "core" / "unreferenced.py", "VALUE = 1\n")
    _write(
        tmp_path / "tests" / "test_only_usage.py",
        "from core.test_only import helper\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = check_critical_modules(tmp_path, config)
    statuses = {item.path: item.status for item in report.statuses["runtime"]}

    assert statuses["app.py"] == "ENTRYPOINT"
    assert statuses["core/used.py"] == "PRODUCTION_REFERENCED"
    assert statuses["core/test_only.py"] == "TEST_ONLY"
    assert statuses["core/unreferenced.py"] == "UNREFERENCED"
    assert statuses["core/missing.py"] == "MISSING"
    assert [item.path for item in report.entrypoints] == ["app.py"]
    assert [item.path for item in report.test_only] == ["core/test_only.py"]
    assert [item.path for item in report.unreferenced] == ["core/unreferenced.py"]
