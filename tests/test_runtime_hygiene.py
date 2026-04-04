from pathlib import Path

from config import config as cfg


def test_runtime_hygiene_config_defaults_present():
    assert int(cfg.TB_LOG_ROTATE_MAX_MB) == 20
    assert int(cfg.TB_LOG_ROTATE_BACKUPS) == 3
    assert int(cfg.TB_LOG_RETENTION_DAYS) == 7
    assert int(cfg.TB_DB_RETENTION_DAYS) == 3
    assert int(cfg.TB_COMPRESS_LOGS_AFTER_DAYS) == 1
    assert int(cfg.TB_FORCE_COMPRESS_LARGE_LOG_MB) == 20


def test_cleanup_runtime_script_uses_strict_mode():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_runtime.sh"
    content = script_path.read_text(encoding="utf-8")

    assert script_path.exists()
    assert content.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in content
