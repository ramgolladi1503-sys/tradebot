import ast
from pathlib import Path

from core import kite_depth_ws as ws


def _watchdog_node():
    source = Path(ws.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_watchdog"
    )


def test_watchdog_binds_authoritative_intended_tokens_as_global():
    watchdog = _watchdog_node()
    declared_globals = {
        name
        for node in ast.walk(watchdog)
        if isinstance(node, ast.Global)
        for name in node.names
    }
    assert "_INTENDED_TOKENS" in declared_globals


def test_watchdog_emits_periodic_snapshots_without_tick_callback():
    watchdog = _watchdog_node()
    periodic_loops = [
        node
        for node in ast.walk(watchdog)
        if isinstance(node, ast.While)
        and isinstance(node.test, ast.Constant)
        and node.test.value is True
    ]
    assert periodic_loops

    for loop in periodic_loops:
        sleep_lines = [
            node.lineno
            for node in ast.walk(loop)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "time"
            and node.func.attr == "sleep"
        ]
        snapshot_lines = [
            node.lineno
            for node in ast.walk(loop)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_emit_snapshot"
        ]
        if sleep_lines and snapshot_lines and min(sleep_lines) < max(snapshot_lines):
            return

    raise AssertionError("watchdog timer loop must emit snapshots after waiting, without on_ticks")


def test_intended_token_statistics_preserve_exact_identity(monkeypatch):
    rows = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, extra=None, **kwargs: rows.append(extra))
    monkeypatch.setattr(ws, "_ensure_feed_session_id", lambda: "scope-test-session")
    monkeypatch.setattr(ws, "_INTENDED_TOKENS", [1, 2, 3])
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1, 2, 4])

    ws._log_subscription_mutation_diagnostic(
        action="delta",
        reason="scope_regression",
        requested_tokens=[],
        phase="before",
    )

    assert rows[0]["missing_tokens"] == [3]
    assert rows[0]["extra_tokens"] == [4]
    assert ws._INTENDED_TOKENS == [1, 2, 3]
