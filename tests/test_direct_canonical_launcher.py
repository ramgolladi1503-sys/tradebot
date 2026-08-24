import json
from pathlib import Path

import pytest

import scripts.run_canonical_readonly_live as launcher


def test_launcher_rejects_dirty_authority(monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "check_output", lambda *args, **kwargs: " M dirty.py\n")
    with pytest.raises(RuntimeError, match="CANONICAL_AUTHORITY_DIRTY"):
        launcher._require_clean_authority()


def test_startup_failure_redacts_all_credential_values(tmp_path, monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "api-secret-value")
    monkeypatch.setenv("KITE_API_SECRET", "app-secret-value")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "access-token-value")
    path = launcher.write_startup_failure(
        root=tmp_path, source_sha="d" * 40, session_id="session", phase="test", exc=RuntimeError("api_key=api-secret-value access_token=access-token-value"),
    )
    raw = path.read_text()
    payload = json.loads(raw)
    assert payload["source_sha"] == "d" * 40
    assert "api-secret-value" not in raw
    assert "app-secret-value" not in raw
    assert "access-token-value" not in raw
    assert payload["sanitized_message"].count("[REDACTED]") >= 2


def test_launcher_forbidden_startup_references_are_not_in_launcher():
    source = Path(launcher.__file__).read_text()
    assert "launchctl" not in source
    assert "run_live.sh" not in source
    assert "watchdog.sh" not in source
    assert "scheduler.py" not in source
    assert "main.py" not in source


def test_launcher_safety_metadata_fails_closed(monkeypatch, tmp_path):
    import core.kite_read_only_observation_runtime as runtime
    monkeypatch.setattr(
        runtime,
        "safe_environment",
        lambda: {
            "TRADING_MODE": "SIM",
            "EXECUTION_MODE": "SIM",
            "LIVE_BROKER_ADAPTER_ACTIVE": "1",
            "ALLOW_LIVE_ORDERS": "0",
            "PAPER_TRADING_ENABLED": "false",
            "LIVE_TRADING_ENABLED": "false",
            "TRADEBOT_READ_ONLY": "true",
        },
    )
    token = tmp_path / "token"
    token.write_text("opaque")
    token.chmod(0o600)
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    with pytest.raises(RuntimeError):
        launcher._metadata_guard(token_path=token)
