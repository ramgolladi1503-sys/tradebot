from core.feed.ws_mutation_queue import safe_subscribe_full_mode_observed


class DummySocket:
    MODE_FULL = "full"

    def __init__(self, *, mode_fails: bool = False):
        self.ws = object()
        self.mode_fails = mode_fails
        self.subscribed = []
        self.full_mode = []

    def subscribe(self, tokens):
        self.subscribed.extend(tokens)

    def set_mode(self, mode, tokens):
        if self.mode_fails:
            raise RuntimeError("mode callback failed")
        assert mode == self.MODE_FULL
        self.full_mode.extend(tokens)


def test_queued_subscription_is_not_applied(monkeypatch):
    socket = DummySocket()
    events = []
    monkeypatch.setattr(
        "core.feed.ws_mutation_queue._check_socket_health",
        lambda _ws: (True, False, "ws_disconnected"),
    )

    subscribed, mode = safe_subscribe_full_mode_observed(
        socket,
        [101],
        "test",
        100.0,
        socket_generation=4,
        active_generation=lambda: 4,
        event_callback=lambda event, payload: events.append((event, payload)),
    )

    assert subscribed.queued and not subscribed.applied
    assert mode.queued and not mode.applied
    assert socket.subscribed == []
    assert "FEED_SUBSCRIBE_QUEUED" in [event for event, _ in events]


def test_mode_full_failure_does_not_report_full_mode_applied(monkeypatch):
    socket = DummySocket(mode_fails=True)
    events = []
    monkeypatch.setattr(
        "core.feed.ws_mutation_queue._check_socket_health",
        lambda _ws: (True, True, None),
    )

    subscribed, mode = safe_subscribe_full_mode_observed(
        socket,
        [101],
        "test",
        100.0,
        socket_generation=4,
        active_generation=lambda: 4,
        event_callback=lambda event, payload: events.append((event, payload)),
    )

    assert subscribed.applied
    assert not mode.applied
    assert "FEED_SUBSCRIBE_CALLBACK_APPLIED" in [event for event, _ in events]
    assert "FEED_MODE_FULL_CALLBACK_FAILED" in [event for event, _ in events]


def test_old_generation_callback_cannot_mutate_current_truth(monkeypatch):
    socket = DummySocket()
    events = []
    applied = []
    monkeypatch.setattr(
        "core.feed.ws_mutation_queue._check_socket_health",
        lambda _ws: (True, True, None),
    )

    subscribed, mode = safe_subscribe_full_mode_observed(
        socket,
        [101],
        "test",
        100.0,
        on_applied_callback=lambda: applied.append(101),
        socket_generation=4,
        active_generation=lambda: 5,
        event_callback=lambda event, payload: events.append((event, payload)),
    )

    assert not subscribed.applied
    assert not mode.applied
    assert socket.subscribed == []
    assert applied == []
    assert "FEED_OLD_GENERATION_CALLBACK_IGNORED" in [event for event, _ in events]
