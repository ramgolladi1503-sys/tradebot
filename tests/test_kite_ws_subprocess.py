from __future__ import annotations

import core.kite_ws_subprocess as ws_subprocess


def test_feed_subprocess_uses_spawn_context(monkeypatch):
    calls = []

    class FakeProcess:
        def __init__(self, *, target, args, name):
            calls.append(("process", target, args, name))
            self.daemon = False
            self.pid = 12345

        def start(self):
            calls.append(("start",))

        def is_alive(self):
            return False

    class FakeContext:
        def Process(self, **kwargs):
            return FakeProcess(**kwargs)

        def Event(self):
            return object()

    monkeypatch.setattr(
        ws_subprocess.multiprocessing,
        "get_context",
        lambda method: calls.append(("context", method)) or FakeContext(),
    )
    monkeypatch.setattr(ws_subprocess, "_WS_PROCESS", None)
    monkeypatch.setattr(ws_subprocess, "_LAST_TOKENS", [])

    ws_subprocess.start_depth_ws_subprocess([101, 202], profile_verified=False)

    assert calls[0] == ("context", "spawn")
    assert calls[1] == (
        "process",
        ws_subprocess._run_in_child,
        ([101, 202], False, ws_subprocess._WS_PROCESS_RESTART_EVENT),
        "kite_depth_ws_subprocess",
    )
    assert calls[2] == ("start",)
    assert ws_subprocess._WS_PROCESS.daemon is True


def test_child_installs_parent_restart_event_before_feed_start(monkeypatch):
    calls = []
    event = object()
    monkeypatch.setattr(ws_subprocess.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(
        "core.kite_depth_ws.set_process_restart_event",
        lambda value: calls.append(("event", value)),
    )
    monkeypatch.setattr(
        ws_subprocess,
        "start_depth_ws",
        lambda tokens, profile_verified: calls.append(("start", tokens, profile_verified)),
    )

    ws_subprocess._run_in_child([101], True, event)

    assert calls == [("event", event), ("start", [101], True)]


def test_monitor_replaces_child_when_callback_latch_requires_process_restart(monkeypatch):
    actions = []

    class LiveProcess:
        def is_alive(self):
            return True

    monkeypatch.setattr(ws_subprocess, "_WS_PROCESS", LiveProcess())
    monkeypatch.setattr(ws_subprocess, "_LAST_TOKENS", [101])
    monkeypatch.setattr(ws_subprocess, "_PROFILE_VERIFIED", True)
    monkeypatch.setattr(ws_subprocess, "_LAST_RESTART_TIME", 0.0)
    monkeypatch.setattr(ws_subprocess.time, "time", lambda: 100.0)
    monkeypatch.setattr(
        ws_subprocess,
        "load_current_feed_runtime",
        lambda: {"valid": True, "payload": {
            "runtime_state": "RESTART_REQUIRED",
            "process_restart_required": True,
            "last_error": "callback_queue_full",
        }},
    )
    monkeypatch.setattr(ws_subprocess, "stop_depth_ws_subprocess", lambda: actions.append("stop"))
    monkeypatch.setattr(
        ws_subprocess,
        "start_depth_ws_subprocess",
        lambda tokens, profile_verified: actions.append(("start", tokens, profile_verified)),
    )

    ws_subprocess.monitor_depth_ws_subprocess()

    assert actions == ["stop", ("start", [101], True)]


def test_monitor_uses_child_restart_event_when_runtime_artifact_is_unavailable(monkeypatch):
    actions = []

    class LiveProcess:
        def is_alive(self):
            return True

    class RestartEvent:
        def is_set(self):
            return True

    monkeypatch.setattr(ws_subprocess, "_WS_PROCESS", LiveProcess())
    monkeypatch.setattr(ws_subprocess, "_WS_PROCESS_RESTART_EVENT", RestartEvent())
    monkeypatch.setattr(ws_subprocess, "_LAST_TOKENS", [101])
    monkeypatch.setattr(ws_subprocess, "_PROFILE_VERIFIED", True)
    monkeypatch.setattr(ws_subprocess, "_LAST_RESTART_TIME", 0.0)
    monkeypatch.setattr(ws_subprocess.time, "time", lambda: 100.0)

    def unavailable_artifact():
        raise AssertionError("restart IPC must not depend on the runtime artifact queue")

    monkeypatch.setattr(ws_subprocess, "load_current_feed_runtime", unavailable_artifact)
    monkeypatch.setattr(ws_subprocess, "stop_depth_ws_subprocess", lambda: actions.append("stop"))
    monkeypatch.setattr(
        ws_subprocess,
        "start_depth_ws_subprocess",
        lambda tokens, profile_verified: actions.append(("start", tokens, profile_verified)),
    )

    ws_subprocess.monitor_depth_ws_subprocess()

    assert actions == ["stop", ("start", [101], True)]
