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
