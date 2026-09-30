import builtins
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

from core.daily_instrument_authority import produce_authority
from core.market_event_graph_live_launch_plan import build_launch_plan, write_launch_plan


ROOT = Path(__file__).resolve().parents[1]


def _offline_inputs(tmp_path: Path, *, plan_session: str = "2026-09-30") -> list[str]:
    master = tmp_path / "instruments.json"
    master.write_text(json.dumps([{
        "exchange": "NSE", "instrument_token": 256265, "tradingsymbol": "NIFTY 50",
        "segment": "INDICES", "instrument_type": "INDEX", "expiry": None,
        "lot_size": 0, "tick_size": 0, "strike": 0,
    }]), encoding="utf-8")
    authority_path = tmp_path / "authority.json"
    produce_authority(
        master_path=master, output_path=authority_path, session_date="2026-09-30",
        source_sha="", required_tokens=[], reviewed_pass=True,
    )
    plan = build_launch_plan(
        session_date=plan_session,
        production_tokens=[256265],
        production_resolution=[{"index_token": 256265}],
        sticky_tokens=[],
        observation_tokens=list(range(1000, 1051)),
        budget=100,
        master_sha256="synthetic-master-sha",
        universe_sha256="synthetic-universe-sha",
        configuration={},
        broker_metadata_called=False,
    )
    plan_path = tmp_path / "launch-plan.json"
    write_launch_plan(plan_path, plan)
    return [
        "--session-date", "2026-09-30",
        "--output-root", str(tmp_path / "runtime-output"),
        "--kite-instruments-file", str(master),
        "--launch-plan", str(plan_path),
        "--validate-only",
        "--authority-artifact", str(authority_path),
    ]


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("kite_observer_entrypoint_test", ROOT / "scripts/run_kite_read_only_observation_v1.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_governed_runner_uses_only_read_only_entrypoint():
    source = Path("scripts/run_market_event_graph_live_session_v1.py").read_text()
    assert "run_kite_read_only_observation_v1.py" in source
    assert 'subprocess.run(["bash", "run_live.sh"]' not in source
    assert "run_live_observation.sh" not in source


def test_entrypoint_requires_explicit_launch_inputs():
    source = Path("scripts/run_kite_read_only_observation_v1.py").read_text()
    for flag in ("--session-date", "--output-root", "--kite-instruments-file", "--launch-plan"):
        assert flag in source


def test_validate_only_needs_no_token_or_runtime_and_makes_no_network_attempt(tmp_path, monkeypatch):
    args = _offline_inputs(tmp_path)
    attempted = []
    original_import = builtins.__import__

    def guarded_import(name, *positional, **kwargs):
        if (
            name == "core.auth" or name.startswith("core.auth.")
            or name == "core.kite_client" or name.startswith("core.kite_client.")
            or name == "core.auth_health" or name.startswith("core.auth_health.")
            or name == "kiteconnect" or name.startswith("kiteconnect.")
            or name == "core.kite_read_only_observation_runtime"
        ):
            raise AssertionError(f"offline_import_forbidden:{name}")
        return original_import(name, *positional, **kwargs)

    def forbidden_network(*_args, **_kwargs):
        attempted.append(True)
        raise AssertionError("offline_network_attempt_forbidden")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(sys, "argv", ["run_kite_read_only_observation_v1.py", *args])
    assert _load_entrypoint().main() == 0
    assert attempted == []
    assert not (tmp_path / "runtime-output").exists()
    assert "--token-path" not in args


def test_validate_only_fails_closed_on_launch_plan_session_mismatch(tmp_path, monkeypatch):
    args = _offline_inputs(tmp_path, plan_session="2026-09-29")
    monkeypatch.setattr(sys, "argv", ["run_kite_read_only_observation_v1.py", *args])
    with pytest.raises(SystemExit, match="BLOCKED_BY_LAUNCH_PLAN_SESSION_DATE"):
        _load_entrypoint().main()


def test_observer_mode_requires_token_before_runtime_initialization(tmp_path, monkeypatch):
    args = _offline_inputs(tmp_path)
    args.remove("--validate-only")
    original_import = builtins.__import__

    def guarded_import(name, *positional, **kwargs):
        if name == "core.runtime_storage_authority" or name.startswith("core.runtime_storage_authority."):
            raise AssertionError("runtime_storage_import_before_token_check")
        return original_import(name, *positional, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(sys, "argv", ["run_kite_read_only_observation_v1.py", *args])
    with pytest.raises(SystemExit, match="KITE_TOKEN_PATH_REQUIRED_FOR_OBSERVATION"):
        _load_entrypoint().main()
