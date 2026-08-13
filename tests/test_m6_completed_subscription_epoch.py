from __future__ import annotations

from core import kite_depth_ws
from core.feed.feed_epoch import _reset_feed_epoch_for_tests, current_feed_epoch


def setup_function() -> None:
    _reset_feed_epoch_for_tests()
    with kite_depth_ws._FEED_EPOCH_TRANSITION_LOCK:
        kite_depth_ws._FEED_EPOCH_TRANSITION_IDS.clear()


def test_completed_changed_delta_advances_once_for_duplicate_callbacks() -> None:
    kite_depth_ws._record_completed_subscription_delta(
        old_tokens=[1], new_tokens=[2], reason="atm_shift_steps=1", socket_generation=7
    )
    kite_depth_ws._record_completed_subscription_delta(
        old_tokens=[1], new_tokens=[2], reason="atm_shift_steps=1", socket_generation=7
    )
    assert current_feed_epoch() == 1


def test_completed_noop_delta_does_not_advance() -> None:
    kite_depth_ws._record_completed_subscription_delta(
        old_tokens=[1, 2], new_tokens=[2, 1], reason="no_op", socket_generation=7
    )
    assert current_feed_epoch() == 0


def test_handshake_path_consumes_only_changed_resubscribe_status() -> None:
    source = open("core/kite_depth_ws.py", encoding="utf-8").read()
    handshake = source[source.index('resubscribe_result = _resubscribe_full(ws, reason="handshake_soft_reset")') :]
    assert 'get("status") == "SUCCESS_CHANGED"' in handshake
    assert 'resubscribe_result = _resubscribe_full(ws, reason="handshake_soft_reset")' in handshake
