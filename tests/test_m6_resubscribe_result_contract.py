from __future__ import annotations

import ast
from pathlib import Path


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
