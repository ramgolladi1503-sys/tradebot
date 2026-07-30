from core.feed.ws_mutation_queue import safe_subscribe_full_mode_observed
import core.kite_depth_ws as depth_ws


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


OPTION_TOKENS = {
    "BANKNIFTY": [
        15123714, 15123970, 15119618, 15124482, 15124226, 15122946,
        15119106, 15124994, 15124738, 15119362, 15118594, 15125506,
        15125250, 15118850, 15118082, 15126274, 15126018, 15118338,
        15116546, 15126786, 15126530, 15116802, 15116034, 15127298,
        15127042, 15116290,
    ],
    "NIFTY": [
        16838146, 16838658, 16818946, 16846594, 16846338, 16819202,
        16818434, 16847106, 16846850, 16818690, 16817922, 16858370,
        16858114, 16818178, 16817410, 16858882, 16858626, 16817666,
        16816898, 16859906, 16859650, 16817154, 16816386, 16860418,
        16860162, 16816642,
    ],
    "SENSEX": [
        293282053, 294191365, 292074501, 293171973, 292248325, 292948485,
        293064197, 292161797, 293547525, 293979653, 294094853, 293395973,
        292479237, 292607749, 292810245, 292362245, 291728645, 293652741,
    ],
}
UNDERLYING_TOKENS = [260105, 256265, 265]
BOUNDARY_PAIRS = {
    "BANKNIFTY": {15116034, 15116290},
    "NIFTY": {16816386, 16816642},
    "SENSEX": {292810245, 293652741},
}


def test_exact_73_token_inventory_retains_outer_boundary_pairs(monkeypatch):
    desired = UNDERLYING_TOKENS + [token for tokens in OPTION_TOKENS.values() for token in tokens]
    assert len(desired) == 73
    retained, truncated, metadata = depth_ws._enforce_subscription_budget(
        desired,
        max_tokens=150,
        underlying_tokens=set(UNDERLYING_TOKENS),
    )
    assert not truncated
    assert metadata["dropped_count"] == 0
    assert set(retained) == set(desired)
    for boundary_pair in BOUNDARY_PAIRS.values():
        assert boundary_pair.issubset(retained)

    socket = DummySocket()
    monkeypatch.setattr(
        "core.feed.ws_mutation_queue._check_socket_health",
        lambda _ws: (True, True, None),
    )
    subscribed, mode = safe_subscribe_full_mode_observed(
        socket,
        retained,
        "exact_73_inventory",
        100.0,
        socket_generation=1,
        active_generation=lambda: 1,
    )
    assert subscribed.applied and mode.applied
    assert set(socket.subscribed) == set(desired)
    assert set(socket.full_mode) == set(desired)


def test_callback_applied_zero_tick_pair_is_not_subscription_failure(monkeypatch):
    desired = OPTION_TOKENS["NIFTY"]
    socket = DummySocket()
    monkeypatch.setattr(
        "core.feed.ws_mutation_queue._check_socket_health",
        lambda _ws: (True, True, None),
    )
    subscribed, mode = safe_subscribe_full_mode_observed(
        socket,
        desired,
        "zero_tick_boundary",
        100.0,
        socket_generation=3,
        active_generation=lambda: 3,
    )
    tick_seen = set(desired) - BOUNDARY_PAIRS["NIFTY"]
    zero_tick = set(desired) - tick_seen
    assert subscribed.applied and mode.applied
    assert zero_tick == {16816386, 16816642}
    assert zero_tick.issubset(socket.subscribed)
    assert zero_tick.issubset(socket.full_mode)
