from __future__ import annotations

import sys
import types

import pytest

import core.auth as auth


pytestmark = [pytest.mark.unit, pytest.mark.behavior, pytest.mark.safety]


def test_feed_startup_event_dependency_is_loaded_lazily_and_delegated(monkeypatch):
    calls = []
    lifecycle = types.ModuleType("core.feed_startup_lifecycle")

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return {"recorded": True, "event": args[0]}

    lifecycle.record_feed_startup_event = recorder
    monkeypatch.setitem(sys.modules, "core.feed_startup_lifecycle", lifecycle)

    result = auth._record_feed_startup_event(
        "KITE_TICKER_CREATE_ATTEMPTED",
        source="qa.contract",
        details={"api_key_present": True},
    )

    assert result == {
        "recorded": True,
        "event": "KITE_TICKER_CREATE_ATTEMPTED",
    }
    assert calls == [
        (
            ("KITE_TICKER_CREATE_ATTEMPTED",),
            {
                "source": "qa.contract",
                "details": {"api_key_present": True},
            },
        )
    ]
