from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.test_reality import classify_tests


def test_package_initializers_are_not_classified_as_tests(tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests" / "auth"
    tests_dir.mkdir(parents=True)
    (tmp_path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_auth.py").write_text(
        "def test_auth_contract():\n    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "forensics.yaml"
    config_path.write_text(
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
exclude:
  directories: []
""",
        encoding="utf-8",
    )

    report = classify_tests(tmp_path, load_config(config_path))

    assert [item.path for item in report.tests] == ["tests/auth/test_auth.py"]
    assert report.unknown_tests == []
