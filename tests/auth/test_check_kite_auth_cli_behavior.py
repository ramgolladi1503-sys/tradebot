from __future__ import annotations

import sys

import pytest

import scripts.check_kite_auth as check_auth


pytestmark = [pytest.mark.unit, pytest.mark.behavior, pytest.mark.safety]


class _Lock:
    def __init__(self, *, acquired=True, holder=None, error=None):
        self.acquired = acquired
        self.holder = holder or {}
        self.error = error
        self.lock_path = "/tmp/tradebot.lock"
        self.release_calls = 0

    def acquire(self):
        if self.error is not None:
            raise self.error
        return self.acquired, self.holder

    def release(self):
        self.release_calls += 1


def _install_common(monkeypatch, *, mode="SIM", payload=None, lock=None):
    monkeypatch.setattr(sys, "argv", ["check_kite_auth.py", "--mode", mode])
    monkeypatch.setattr(
        check_auth,
        "validate_kite_startup_credentials",
        lambda **_kwargs: {"api_key": "api", "access_token": "token"},
    )
    monkeypatch.setattr(check_auth, "validate_token", lambda **_kwargs: payload or {})
    if lock is not None:
        monkeypatch.setattr(check_auth, "InstanceLock", lambda **_kwargs: lock)


def test_execution_mode_normalizes_valid_and_invalid_values(monkeypatch):
    monkeypatch.setattr(check_auth.cfg, "EXECUTION_MODE", "paper", raising=False)

    assert check_auth._execution_mode() == "PAPER"
    assert check_auth._execution_mode("live") == "LIVE"
    assert check_auth._execution_mode("invalid") == "SIM"


def test_config_failure_returns_two_without_token_validation(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check_kite_auth.py", "--mode", "SIM"])
    monkeypatch.setattr(
        check_auth,
        "validate_kite_startup_credentials",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("missing token")),
    )
    called = {"validate": False}
    monkeypatch.setattr(
        check_auth,
        "validate_token",
        lambda **_kwargs: called.__setitem__("validate", True),
    )

    assert check_auth.main() == 2
    assert called["validate"] is False
    assert "AUTH_CONFIG_ERROR missing token" in capsys.readouterr().out


def test_lock_error_returns_four_before_validation(monkeypatch, capsys):
    lock = _Lock(error=RuntimeError("lock corrupt"))
    _install_common(monkeypatch, mode="LIVE", payload={"ok": True}, lock=lock)

    assert check_auth.main() == 4
    assert "LOCK_ERROR lock corrupt" in capsys.readouterr().out
    assert lock.release_calls == 0


def test_held_lock_returns_two_with_holder_details(monkeypatch, capsys):
    lock = _Lock(
        acquired=False,
        holder={"pid": 101, "host": "qa-host", "lock_path": "/tmp/held.lock"},
    )
    _install_common(monkeypatch, mode="PAPER", payload={"ok": True}, lock=lock)

    assert check_auth.main() == 2
    output = capsys.readouterr().out
    assert "LOCK_HELD pid=101 host=qa-host path=/tmp/held.lock" in output
    assert lock.release_calls == 0


def test_verified_profile_is_only_success_path_and_releases_lock(monkeypatch, capsys):
    lock = _Lock()
    _install_common(
        monkeypatch,
        mode="LIVE",
        payload={"ok": True, "auth_state": "OK", "user_id": "LLL209"},
        lock=lock,
    )

    assert check_auth.main() == 0
    assert capsys.readouterr().out.strip() == "OK user_id=LLL209"
    assert lock.release_calls == 1


def test_unknown_network_is_unverified_and_returns_five(monkeypatch, capsys):
    lock = _Lock()
    _install_common(
        monkeypatch,
        mode="PAPER",
        payload={
            "ok": False,
            "auth_state": "UNKNOWN_NETWORK",
            "error": "profile_error:TimeoutError",
        },
        lock=lock,
    )

    assert check_auth.main() == 5
    output = capsys.readouterr().out
    assert "AUTH_UNVERIFIED_NETWORK mode=PAPER" in output
    assert "restore network access" in output
    assert lock.release_calls == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": True, "auth_state": "UNKNOWN_NETWORK", "user_id": "LLL209"},
        {"ok": True, "auth_state": "OK", "user_id": ""},
        {"ok": False, "auth_state": "OK", "user_id": "LLL209"},
        {"ok": False, "auth_state": "AUTH_REQUIRED", "error": "invalid session"},
    ],
)
def test_any_incomplete_or_contradictory_success_claim_is_rejected(
    monkeypatch, capsys, payload
):
    _install_common(monkeypatch, mode="SIM", payload=payload)

    result = check_auth.main()

    assert result in {3, 5}
    assert result != 0
    assert "OK user_id=" not in capsys.readouterr().out
