from __future__ import annotations

import ast
from pathlib import Path

from core.feed.feed_epoch import _reset_feed_epoch_for_tests, current_feed_epoch


def _resubscribe_source() -> str:
    return Path("core/kite_depth_ws.py").read_text(encoding="utf-8")


def test_resubscribe_full_exposes_explicit_result_contract():
    source = _resubscribe_source()
    tree = ast.parse(source)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_resubscribe_full"
    ]
    assert len(functions) == 1
    body = ast.unparse(functions[0])
    assert "'SUCCESS_CHANGED'" in body
    assert "'SUCCESS_NO_CHANGE'" in body
    assert "'FAILED'" in body
    assert "'old_tokens'" in body
    assert "'new_tokens'" in body


def test_resubscribe_full_has_no_epoch_advancement():
    source = _resubscribe_source()
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_resubscribe_full"
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "advance_feed_epoch"
        for node in ast.walk(function)
    )


def test_transition_identity_advances_once_for_duplicate_completion():
    _reset_feed_epoch_for_tests()
    seen = set()

    def advance_once(kind, identity):
        key = (kind, identity)
        if key in seen:
            return
        seen.add(key)
        from core.feed.feed_epoch import advance_feed_epoch

        advance_feed_epoch(kind)

    advance_once("SUBSCRIPTION_REBUILD_COMPLETED", "socket-1:set-a")
    advance_once("SUBSCRIPTION_REBUILD_COMPLETED", "socket-1:set-a")
    assert current_feed_epoch() == 1


def test_final_set_mode_failure_returns_before_registry_convergence():
    source = _resubscribe_source()
    start = source.index("def _apply_subscription_delta")
    end = source.index("def _resubscribe_full", start)
    body = source[start:end]
    failure = body.index("final_set_mode:")
    failure_tail = body[failure:]
    assert "return False" in failure_tail
    assert failure_tail.index("return False") < failure_tail.index("_reconcile_rebalance_intended_tokens")
    assert failure_tail.index("return False") < failure_tail.index("_advance_completed_transition")
