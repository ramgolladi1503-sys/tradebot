from __future__ import annotations

from types import SimpleNamespace

import pytest

import core.auth as auth


pytestmark = [pytest.mark.unit, pytest.mark.behavior]


def test_caller_module_name_falls_back_when_current_frame_is_unavailable(monkeypatch):
    monkeypatch.setattr(auth.inspect, "currentframe", lambda: None)

    assert auth._caller_module_name() == "unknown"


def test_caller_module_name_falls_back_when_frame_chain_has_no_module(monkeypatch):
    terminal = SimpleNamespace(f_globals={}, f_back=None)
    initial = SimpleNamespace(f_globals={}, f_back=terminal)
    monkeypatch.setattr(auth.inspect, "currentframe", lambda: initial)

    assert auth._caller_module_name() == "unknown"
