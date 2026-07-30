from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.import_graph import build_reference_graph


def _config(tmp_path):
    path = tmp_path / "forensics.yaml"
    path.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - run_live.sh
critical_modules:
  runtime:
    - core/startup_recovery.py
""",
        encoding="utf-8",
    )
    return load_config(path)


def test_shell_heredoc_python_import_is_production_caller(tmp_path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "startup_recovery.py").write_text(
        "def reap_stale_runtime_locks():\n    return []\n",
        encoding="utf-8",
    )
    (tmp_path / "run_live.sh").write_text(
        """#!/usr/bin/env bash
python - <<'PY'
from core.startup_recovery import reap_stale_runtime_locks
reap_stale_runtime_locks()
PY
""",
        encoding="utf-8",
    )

    graph = build_reference_graph(tmp_path, _config(tmp_path))

    assert graph.production_callers("core/startup_recovery.py") == {"run_live.sh"}
    assert graph.test_callers("core/startup_recovery.py") == set()


def test_shell_comments_echo_and_quoted_text_are_not_imports(tmp_path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "startup_recovery.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "run_live.sh").write_text(
        """#!/usr/bin/env bash
# from core.startup_recovery import reap_stale_runtime_locks
echo "from core.startup_recovery import reap_stale_runtime_locks"
TEXT='import core.startup_recovery'
""",
        encoding="utf-8",
    )

    graph = build_reference_graph(tmp_path, _config(tmp_path))

    assert graph.production_callers("core/startup_recovery.py") == set()
