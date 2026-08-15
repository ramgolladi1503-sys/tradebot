from types import SimpleNamespace

import core.kite_depth_ws as ws


def test_subscription_mutation_diagnostic_captures_target_membership(monkeypatch):
    rows = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, extra=None, **kwargs: rows.append((event, extra)))
    monkeypatch.setattr(ws, "_ensure_feed_session_id", lambda: "test-session")
    monkeypatch.setattr(ws, "_FEED_RECONNECT_GENERATION", 7)
    monkeypatch.setattr(ws, "_SOCKET_GENERATION", 11)
    monkeypatch.setattr(ws, "_INTENDED_TOKENS", [215731205, 1])
    monkeypatch.setattr(ws, "_LAST_TOKENS", [1])
    monkeypatch.setattr(ws, "_RUNTIME_STATE", "RUNNING")
    monkeypatch.setenv("TRADEBOT_RUN_ID", "diagnostic-test")

    ws._log_subscription_mutation_diagnostic(
        action="delta",
        reason="stale_option_prune_refresh",
        requested_tokens=[215731205],
        phase="before",
        result={"applied": False},
    )

    assert len(rows) == 1
    event, payload = rows[0]
    assert event == "FEED_SUBSCRIPTION_MUTATION_DIAGNOSTIC"
    assert payload["target_token"] == 215731205
    assert payload["target_intended_before_or_after"] is True
    assert payload["target_subscribed_before_or_after"] is False
    assert payload["missing_tokens"] == [215731205]
    assert payload["run_id"] == "diagnostic-test"
    assert payload["feed_session_id"] == "test-session"
    assert payload["reconnect_generation"] == 7
    assert payload["socket_generation"] == 11
