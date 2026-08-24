from types import SimpleNamespace
import sys

import core.auth as auth


def test_api_key_fallback_reads_only_governed_launchctl_binding(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        auth.subprocess, "run",
        lambda *args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(returncode=0, stdout="opaque-key\n"),
    )
    assert auth._governed_launchctl_value("KITE_API_KEY") == "opaque-key"
    assert calls[0][0][0] == ["launchctl", "getenv", "KITE_API_KEY"]
    assert calls[0][1]["capture_output"] is True
    assert auth._governed_launchctl_value("KITE_API_SECRET") == ""


def test_launchctl_fallback_is_fail_closed_on_error(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(auth.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""))
    assert auth._governed_launchctl_value("KITE_API_KEY") == ""
