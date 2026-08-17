from __future__ import annotations

import importlib.util
import datetime as dt
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "research" / "run_20260818_operator_preflight_v1.py"
spec = importlib.util.spec_from_file_location("operator_preflight_v1", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _arrange(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, free_gib=20.0, gate_outcome="MARKET_CLOSED_PENDING_TICK_PROOF"):
    producer = tmp_path / "producer"
    runtime_parent = tmp_path / "runtime-parent"
    runtime = runtime_parent / "session"
    producer.mkdir(exist_ok=True)
    runtime_parent.mkdir(exist_ok=True)
    monkeypatch.setattr(mod, "_git", lambda root, *args: mod.FROZEN_PRODUCER_SHA if args == ("rev-parse", "HEAD") else "")
    monkeypatch.setattr(mod.shutil, "disk_usage", lambda path: SimpleNamespace(free=int(free_gib * 1024**3)))
    monkeypatch.setattr(mod.os, "access", lambda path, mode: True)
    monkeypatch.setattr(mod, "_competing_processes", lambda producer: [])
    monkeypatch.setattr(mod, "_readiness_gate", lambda producer, python_command="python": {"outcome": gate_outcome, "hard_fail": gate_outcome == "FAIL", "blockers": ["x"] if gate_outcome == "FAIL" else []})
    monkeypatch.setattr(mod, "_kite_network_auth", lambda producer, python_command="python": {
        "verified": True,
        "method": "FROZEN_CHECK_KITE_AUTH_PROFILE_REST",
        "user_id_present": True,
        "raw_profile_exposed": False,
        "access_token_exposed": False,
        "websocket_started": False,
        "broker_write_authority": False,
        "order_authority": False,
    })
    for name in mod.AUTHORITY_ENV:
        monkeypatch.delenv(name, raising=False)
    return producer, runtime


def test_market_closed_pending_tick_is_valid_premarket_not_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    result = mod.preflight(producer, runtime)
    assert result["status"] == "PREMARKET_OBSERVATION_READY"
    assert result["frozen_pre_live_gate_outcome"] == "MARKET_CLOSED_PENDING_TICK_PROOF"
    assert result["actual_live_tick_proof_required_after_open"] is True
    assert result["live_tick_proof_accepted_from_clock_only"] is False
    assert result["kite_network_auth_requested"] is False
    assert result["kite_network_auth_verified"] is False
    assert result["LIVE_READY"] is False
    assert result["LIVE_VERIFIED"] is False


def test_network_auth_can_pass_while_market_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    result = mod.preflight(producer, runtime, verify_kite_network_auth=True)
    assert result["frozen_pre_live_gate_outcome"] == "MARKET_CLOSED_PENDING_TICK_PROOF"
    assert result["kite_network_auth_requested"] is True
    assert result["kite_network_auth_verified"] is True
    assert result["kite_network_auth_method"] == "FROZEN_CHECK_KITE_AUTH_PROFILE_REST"
    assert result["kite_profile_user_id_present"] is True
    assert result["kite_profile_or_token_exposed"] is False
    assert result["kite_auth_probe_websocket_started"] is False
    assert result["LIVE_READY"] is False


def test_network_auth_failure_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    def fail_auth(producer, python_command="python"):
        raise mod.PreflightError("KITE_NETWORK_AUTH_FAILED:AUTH_REQUIRED:")
    monkeypatch.setattr(mod, "_kite_network_auth", fail_auth)
    with pytest.raises(mod.PreflightError, match="KITE_NETWORK_AUTH_FAILED:AUTH_REQUIRED"):
        mod.preflight(producer, runtime, verify_kite_network_auth=True)


def test_network_auth_checker_redacts_successful_user_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer = tmp_path / "producer"
    scripts = producer / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "check_kite_auth.py").write_text("# fixture\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_run", lambda cmd, cwd=None, env=None: SimpleNamespace(returncode=0, stdout="OK user_id=SECRET-USER\n", stderr=""))
    result = mod._kite_network_auth(producer)
    assert result["verified"] is True
    assert result["user_id_present"] is True
    assert "SECRET-USER" not in repr(result)
    assert result["access_token_exposed"] is False


def test_network_auth_checker_accepts_sanitized_diagnostic_before_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer = tmp_path / "producer"
    scripts = producer / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "check_kite_auth.py").write_text("# fixture\n", encoding="utf-8")
    output = "KITE_REST api_key_tail4=redacted access_token_tail4=redacted\nOK user_id=REDACTED\n"
    monkeypatch.setattr(mod, "_run", lambda cmd, cwd=None, env=None: SimpleNamespace(returncode=0, stdout=output, stderr=""))
    result = mod._kite_network_auth(producer)
    assert result["verified"] is True
    assert result["user_id_present"] is True
    assert result["access_token_exposed"] is False


def test_network_auth_checker_maps_auth_required_without_echoing_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer = tmp_path / "producer"
    scripts = producer / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "check_kite_auth.py").write_text("# fixture\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_run", lambda cmd, cwd=None, env=None: SimpleNamespace(returncode=3, stdout="AUTH_REQUIRED mode=LIVE reason=invalid session\n", stderr=""))
    with pytest.raises(mod.PreflightError, match="KITE_NETWORK_AUTH_FAILED:AUTH_REQUIRED") as exc:
        mod._kite_network_auth(producer)
    assert "invalid session" not in str(exc.value)


def test_wrong_sha_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_git", lambda root, *args: "0" * 40 if args == ("rev-parse", "HEAD") else "")
    with pytest.raises(mod.PreflightError, match="PRODUCER_SHA_MISMATCH"):
        mod.preflight(producer, runtime)


def test_dirty_producer_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_git", lambda root, *args: mod.FROZEN_PRODUCER_SHA if args == ("rev-parse", "HEAD") else " M core/x.py")
    with pytest.raises(mod.PreflightError, match="PRODUCER_WORKTREE_DIRTY"):
        mod.preflight(producer, runtime)


def test_low_disk_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch, free_gib=9.9)
    with pytest.raises(mod.PreflightError, match="DISK_FREE_BELOW_GATE"):
        mod.preflight(producer, runtime)


def test_authority_env_true_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    monkeypatch.setenv("LIVE_AUTHORIZED", "true")
    with pytest.raises(mod.PreflightError, match="AUTHORITY_ENV_ENABLED"):
        mod.preflight(producer, runtime)


def test_competing_process_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "_competing_processes", lambda producer: [{"pid": 123, "command": "python main.py"}])
    with pytest.raises(mod.PreflightError, match="COMPETING_LIVE_PROCESS"):
        mod.preflight(producer, runtime)


def test_cached_pre_live_gate_fail_fails_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch, gate_outcome="FAIL")
    with pytest.raises(mod.PreflightError, match="FROZEN_PRE_LIVE_GATE_FAIL"):
        mod.preflight(producer, runtime)


def test_all_authority_outputs_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    producer, runtime = _arrange(tmp_path, monkeypatch)
    result = mod.preflight(producer, runtime, verify_kite_network_auth=True)
    assert result["broker_write_authority"] is False
    assert result["order_authority"] is False
    assert result["paper_authorized"] is False
    assert result["live_authorized"] is False
    assert result["STRUCTURAL_EDGE_CERTIFIED"] is False


def test_frozen_gate_child_binds_producer_import_root_and_preserves_parent(monkeypatch, tmp_path: Path):
    producer = tmp_path / "producer"
    producer.mkdir()
    evaluator = producer / "core"
    evaluator.mkdir()
    (evaluator / "pre_live_readiness_gate.py").write_text("# fixture\n", encoding="utf-8")
    captured = {}
    monkeypatch.setenv("PYTHONPATH", "/existing/import/root")

    def fake_run(cmd, *, cwd=None, env=None):
        captured.update(cmd=cmd, cwd=cwd, env=env)
        return SimpleNamespace(returncode=0, stdout='{"outcome":"MARKET_CLOSED_PENDING_TICK_PROOF"}', stderr="")

    monkeypatch.setattr(mod, "_run", fake_run)
    mod._readiness_gate(producer)
    assert captured["cwd"] == producer
    assert captured["env"]["PYTHONPATH"].startswith(str(producer) + ":")
    assert captured["env"]["PYTHONPATH"].endswith("/existing/import/root")
    assert __import__("os").environ["PYTHONPATH"] == "/existing/import/root"


def test_auth_checker_uses_same_producer_import_environment(monkeypatch, tmp_path: Path):
    producer = tmp_path / "producer"
    scripts = producer / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "check_kite_auth.py").write_text("# fixture\n", encoding="utf-8")
    captured = {}
    monkeypatch.setenv("PYTHONPATH", "/existing/import/root")

    def fake_run(cmd, *, cwd=None, env=None):
        captured.update(cmd=cmd, cwd=cwd, env=env)
        return SimpleNamespace(returncode=0, stdout="OK user_id=REDACTED\n", stderr="")

    monkeypatch.setattr(mod, "_run", fake_run)
    result = mod._kite_network_auth(producer)
    assert result["verified"] is True
    assert captured["cwd"] == producer
    assert captured["env"]["PYTHONPATH"].startswith(str(producer) + ":")
    assert captured["env"]["PYTHONPATH"].endswith("/existing/import/root")
    assert __import__("os").environ["PYTHONPATH"] == "/existing/import/root"


def test_json_normalization_preserves_date_datetime_and_path():
    assert mod._normalize_json_value(dt.date(2026, 8, 18)) == "2026-08-18"
    value = dt.datetime(2026, 8, 18, 9, 15, tzinfo=dt.timezone.utc)
    assert mod._normalize_json_value(value) == "2026-08-18T09:15:00+00:00"
    assert mod._normalize_json_value(Path("/tmp/evidence")) == "/tmp/evidence"


def test_json_normalization_unknown_type_fails_closed():
    with pytest.raises(mod.PreflightError, match="JSON_NORMALIZATION_UNKNOWN_TYPE"):
        mod._normalize_json_value(object())


def test_json_normalization_preserves_blocker_and_option_counts():
    payload = {
        "outcome": "FAIL",
        "blockers": ["token_universe_zero"],
        "checks": {"token_universe": {"option_token_count": 70, "rows": [{"count": 26, "status": "FULL"}, {"count": 26, "status": "FULL"}, {"count": 18, "status": "FULL"}]}},
    }
    normalized = mod._normalize_json_value(payload)
    assert normalized == payload


def test_readiness_gate_uses_selected_python_adapter_and_normalizes(monkeypatch, tmp_path: Path):
    producer = tmp_path / "producer"
    evaluator = producer / "core"
    evaluator.mkdir(parents=True)
    (evaluator / "pre_live_readiness_gate.py").write_text("# frozen evaluator fixture\n", encoding="utf-8")
    captured = {}
    parent_pythonpath = os.environ.get("PYTHONPATH", "")

    def fake_run(cmd, *, cwd=None, env=None):
        captured.update(cmd=cmd, cwd=cwd, env=env)
        return SimpleNamespace(returncode=0, stdout='{"outcome":"MARKET_CLOSED_PENDING_TICK_PROOF","blockers":[],"ready":false}', stderr="")

    monkeypatch.setattr(mod, "_run", fake_run)
    result = mod._readiness_gate(producer, python_command="/external/compatible/python")
    assert captured["cmd"][0] == "/external/compatible/python"
    assert captured["cmd"][1] == "-c"
    assert captured["cwd"] == producer
    assert result["outcome"] == "MARKET_CLOSED_PENDING_TICK_PROOF"
    assert result["_preflight_normalization_schema"] == "strict-json-v1"
    assert os.environ.get("PYTHONPATH", "") == parent_pythonpath
    assert captured["env"]["PYTHONPATH"].endswith(parent_pythonpath) if parent_pythonpath else True
