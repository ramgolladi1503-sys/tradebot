from __future__ import annotations

import types


def test_index_rest_quote_refresh_async_does_not_block(monkeypatch):
    """
    Regression guard:
    _refresh_index_quote_from_rest() must not call kite.quote() inline when async mode is enabled
    (force=False). It should schedule and return immediately.
    """

    import core.market_data as md
    from config import config as cfg

    monkeypatch.setattr(cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(cfg, "INDEX_REST_QUOTE_REFRESH_ASYNC", True, raising=False)
    monkeypatch.setattr(cfg, "INDEX_REST_QUOTE_REFRESH_ASYNC_MAX_WORKERS", 1, raising=False)
    monkeypatch.setattr(cfg, "INDEX_REST_QUOTE_REFRESH_SEC", 0.0, raising=False)

    # Ensure no cached bid/ask so refresh path is considered.
    monkeypatch.setattr(md, "get_index_quote_snapshot", lambda sym: {}, raising=False)
    monkeypatch.setattr(md, "now_utc_epoch", lambda: 1000.0, raising=False)
    monkeypatch.setattr(md, "_index_quote_keys", lambda sym: [f"NSE:{sym}"], raising=False)
    monkeypatch.setattr(md, "_log_index_quote_request", lambda *a, **k: None, raising=False)

    # If kite.quote is called inline, fail the test.
    class _FakeKite:
        def quote(self, instruments):
            raise AssertionError("kite.quote called inline despite async enabled")

    fake_kite_client = types.SimpleNamespace(kite=_FakeKite(), ensure=lambda: None)
    monkeypatch.setattr(md, "kite_client", fake_kite_client, raising=False)

    # Make executor submit a no-op and track that it was called.
    called = {"submit": 0}

    class _FakeExec:
        def submit(self, fn):
            called["submit"] += 1
            # Do not run fn in test; we only care that it was scheduled.
            return None

    monkeypatch.setattr(md, "_index_rest_quote_executor", lambda: _FakeExec(), raising=False)
    monkeypatch.setattr(md, "_INDEX_REST_QUOTE_INFLIGHT", set(), raising=False)
    monkeypatch.setattr(md, "_INDEX_REST_QUOTE_REFRESH_TS", {}, raising=False)

    ok = md._refresh_index_quote_from_rest("NIFTY", force=False)
    assert ok is False
    assert called["submit"] == 1

