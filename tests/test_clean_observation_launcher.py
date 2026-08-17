from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run_clean_observation_session.py"
BASE_SHA = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _run(tmp_path: Path, **extra):
    env_file = tmp_path / "credentials.env"
    env_file.write_text("KITE_API_KEY=placeholder\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    env = {
        **os.environ,
        "TRADEBOT_ENV_FILE": str(env_file),
        "TRADEBOT_RUNTIME_ROOT": str(runtime),
        "EXPECTED_MAIN_SHA": BASE_SHA,
        **extra,
    }
    return subprocess.run([sys.executable, str(LAUNCHER), "--validate-only"], cwd=ROOT, env=env, capture_output=True, text=True), runtime


def test_launcher_emits_manifest_before_producer(tmp_path):
    result, runtime = _run(tmp_path, OBSERVATION_ONLY_MODE="true")
    assert result.returncode == 0, result.stderr
    manifests = list(runtime.glob("*/manifest/session_manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["observation_only_mode"] is True
    assert manifest["tracked_runtime_write_risk"] is False


def test_launcher_rejects_authority_conflict(tmp_path):
    result, _ = _run(tmp_path, OBSERVATION_ONLY_MODE="true", LIVE_TRADING_ENABLED="true")
    assert result.returncode == 2
    assert "AUTHORITY_CONFLICT" in result.stderr


def test_launcher_rejects_wrong_sha(tmp_path):
    result, _ = _run(tmp_path, OBSERVATION_ONLY_MODE="true", EXPECTED_MAIN_SHA="0" * 40)
    assert result.returncode == 2
    assert "HEAD_MISMATCH" in result.stderr


def test_launcher_rejects_missing_external_inputs(tmp_path):
    env = {**os.environ, "EXPECTED_MAIN_SHA": BASE_SHA, "OBSERVATION_ONLY_MODE": "true"}
    result = subprocess.run([sys.executable, str(LAUNCHER), "--validate-only"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert "TRADEBOT_ENV_FILE_REQUIRED" in result.stderr


def test_launcher_rejects_dirty_tree(tmp_path):
    marker = ROOT / "launcher_dirty_probe.txt"
    marker.write_text("probe\n", encoding="utf-8")
    try:
        result, _ = _run(tmp_path, OBSERVATION_ONLY_MODE="true")
        assert result.returncode == 2
        assert "CLEAN_TREE_REQUIRED" in result.stderr
    finally:
        marker.unlink()


def test_launcher_rejects_env_inside_repo(tmp_path):
    env_file = ROOT / "tests" / ".temporary_launcher.env"
    env_file.write_text("KITE_API_KEY=x\n", encoding="utf-8")
    try:
        env = {**os.environ, "TRADEBOT_ENV_FILE": str(env_file), "TRADEBOT_RUNTIME_ROOT": str(tmp_path / "runtime"), "EXPECTED_MAIN_SHA": BASE_SHA, "OBSERVATION_ONLY_MODE": "true"}
        result = subprocess.run([sys.executable, str(LAUNCHER), "--validate-only"], cwd=ROOT, env=env, capture_output=True, text=True)
        assert result.returncode == 2
        assert "INSIDE_REPOSITORY" in result.stderr
    finally:
        env_file.unlink()


def test_launcher_has_no_broad_kill_or_dirty_path():
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "/Users/madhuram/tradebot" not in source
    assert "SIGKILL" not in source
    assert "pkill" not in source
    assert "killall" not in source
    assert "run_all.sh" not in source
    assert "watchdog.sh" not in source
