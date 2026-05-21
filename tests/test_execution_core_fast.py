from types import SimpleNamespace

import pytest

from core.execution_core_fast import FastExecutionCore


def test_should_run_cycle_uses_timer_before_feed_debug(monkeypatch):
    core = FastExecutionCore(SimpleNamespace(poll_interval=1.0))
    calls = {"feed_debug": 0}

    def fail_if_called():
        calls["feed_debug"] += 1
        raise AssertionError("feed debug should not be called when timer cycle is already due")

    monkeypatch.setattr(core, "latest_feed_epoch", fail_if_called)

    should_run, feed_epoch = core.should_run_cycle(now_mono=1.0)

    assert should_run is True
    assert feed_epoch == 0.0
    assert calls["feed_debug"] == 0


def test_should_run_cycle_checks_feed_when_timer_not_due(monkeypatch):
    core = FastExecutionCore(SimpleNamespace(poll_interval=1.0))
    core.last_cycle_mono = 10.0
    core.last_feed_epoch = 100.0

    monkeypatch.setattr(core, "latest_feed_epoch", lambda: 101.0)

    should_run, feed_epoch = core.should_run_cycle(now_mono=10.1)

    assert should_run is True
    assert feed_epoch == 101.0


def test_should_run_cycle_idles_when_timer_not_due_and_feed_unchanged(monkeypatch):
    core = FastExecutionCore(SimpleNamespace(poll_interval=1.0))
    core.last_cycle_mono = 10.0
    core.last_feed_epoch = 100.0

    monkeypatch.setattr(core, "latest_feed_epoch", lambda: 100.0)

    should_run, feed_epoch = core.should_run_cycle(now_mono=10.1)

    assert should_run is False
    assert feed_epoch == 100.0
