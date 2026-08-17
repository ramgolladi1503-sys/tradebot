from __future__ import annotations

import importlib.util
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
    monkeypatch.setattr(mod, "_readiness_gate", lambda producer: {"outcome": gate_outcome, "hard_fail": gate_outcome == "FAIL", "blockers": ["x"] if gate_outcome == "FAIL" else []})
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
    assert result["LIVE_READY"] is False
    assert result["LIVE_VERIFIED"] is False


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
    result = mod.preflight(producer, runtime)
    assert result["broker_write_authority"] is False
    assert result["order_authority"] is False
    assert result["paper_authorized"] is False
    assert result["live_authorized"] is False
    assert result["STRUCTURAL_EDGE_CERTIFIED"] is False
