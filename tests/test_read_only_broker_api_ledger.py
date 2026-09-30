import json
from pathlib import Path

import pytest

from core.kite_client import KiteClient
from core.read_only_broker_api_ledger import (
    BrokerApiLedgerError,
    BrokerApiPolicyViolation,
    ReadOnlyBrokerApiLedger,
    verify_read_only_broker_api_ledger,
)


class _Response:
    def __init__(self, status_code=200):
        self.status_code = status_code


class _Session:
    def __init__(self, *, error=None, status_code=200):
        self.calls = []
        self.error = error
        self.status_code = status_code

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        return _Response(self.status_code)


class _Client:
    def __init__(self, *, error=None, status_code=200):
        self.reqsession = _Session(error=error, status_code=status_code)

    def profile(self):
        response = self.reqsession.request(
            "GET", "https://api.kite.trade/user/profile?secret=must-not-log",
            headers={"Authorization": "must-not-log"},
        )
        assert response.status_code == 200
        return {"user_id": "U123"}


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_ledger_counts_and_redacts_successful_rest_call(tmp_path):
    path = tmp_path / "broker_api_calls.jsonl"
    ledger = ReadOnlyBrokerApiLedger(path)
    client = _Client()
    ledger.instrument_client(client)

    assert client.profile() == {"user_id": "U123"}
    fields = ledger.safety_fields()
    assert fields["broker_api_measurement_scope"] == "KITE_CLIENT_REST_AND_KITE_MARKET_DATA_WEBSOCKET"
    assert fields["broker_api_called"] is True
    assert fields["broker_api_call_count"] == 1
    assert fields["broker_api_call_attempt_count"] == 1
    assert fields["broker_api_call_failure_count"] == 0
    assert fields["broker_api_rest_call_failure_count"] == 0
    assert fields["broker_write_authority"] is False
    assert fields["order_authority"] is False
    assert fields["paper_authorized"] is False
    assert fields["live_authorized"] is False
    rows = _rows(path)
    assert [row["event"] for row in rows] == [
        "BROKER_REST_CALL_DISPATCHED", "BROKER_REST_CALL_COMPLETED",
    ]
    assert rows[0]["endpoint_path"] == "/user/profile"
    assert client.reqsession.calls[0][2]["allow_redirects"] is False
    assert all("secret" not in json.dumps(row) and "Authorization" not in json.dumps(row) for row in rows)
    verified = verify_read_only_broker_api_ledger(path)
    assert verified["status"] == "VERIFIED"
    assert verified["broker_api_call_count"] == 1
    assert verified["ledger_head_sha256"] == rows[-1]["event_sha256"]
    ledger.close()


def test_ledger_counts_websocket_dispatch_separately_and_redacts_url_query(tmp_path):
    path = tmp_path / "broker_api_calls.jsonl"
    ledger = ReadOnlyBrokerApiLedger(path)
    call_id = ledger.record_websocket_connect_attempt(
        "wss://ws.kite.trade/?api_key=secret&access_token=credential"
    )
    ledger.record_websocket_connect_outcome(call_id)

    fields = ledger.verified_safety_fields()
    assert fields["broker_api_called"] is True
    assert fields["broker_api_call_count"] == 1
    assert fields["broker_api_rest_called"] is False
    assert fields["broker_api_rest_call_count"] == 0
    assert fields["broker_api_rest_call_failure_count"] == 0
    assert fields["broker_api_websocket_connect_count"] == 1
    assert fields["broker_api_websocket_failure_count"] == 0
    rows = _rows(path)
    assert [row["event"] for row in rows] == [
        "BROKER_WEBSOCKET_CALL_DISPATCHED", "BROKER_WEBSOCKET_CALL_SCHEDULED",
    ]
    assert all("api_key" not in json.dumps(row) and "access_token" not in json.dumps(row) for row in rows)
    ledger.close()


def test_ledger_records_websocket_connect_failure_without_exception_text(tmp_path):
    path = tmp_path / "broker_api_calls.jsonl"
    ledger = ReadOnlyBrokerApiLedger(path)
    call_id = ledger.record_websocket_connect_attempt("wss://ws.kite.trade/")
    ledger.record_websocket_connect_outcome(call_id, error=TimeoutError("credential-bearing details"))

    fields = ledger.verified_safety_fields()
    assert fields["broker_api_called"] is True
    assert fields["broker_api_call_failure_count"] == 1
    assert fields["broker_api_rest_call_failure_count"] == 0
    assert fields["broker_api_websocket_failure_count"] == 1
    assert _rows(path)[-1]["error_type"] == "TimeoutError"
    assert "credential-bearing" not in path.read_text(encoding="utf-8")
    ledger.close()


@pytest.mark.parametrize("url", [
    "ws://ws.kite.trade/",
    "wss://example.invalid/",
    "wss://user:password@ws.kite.trade/",
    "wss://ws.kite.trade:444/",
    "wss://ws.kite.trade/other",
])
def test_ledger_rejects_unapproved_websocket_before_dispatch(tmp_path, url):
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")
    with pytest.raises(BrokerApiPolicyViolation, match="BROKER_WEBSOCKET_ENDPOINT_NOT_ALLOWED"):
        ledger.record_websocket_connect_attempt(url)
    assert ledger.safety_fields()["broker_api_called"] is False
    assert ledger.safety_fields()["broker_api_call_attempt_count"] == 0
    ledger.close()


def test_ledger_counts_transport_failure_as_a_dispatched_api_call(tmp_path):
    path = tmp_path / "broker_api_calls.jsonl"
    ledger = ReadOnlyBrokerApiLedger(path)
    client = _Client(error=TimeoutError("do not persist exception message"))
    ledger.instrument_client(client)

    with pytest.raises(TimeoutError):
        client.profile()
    fields = ledger.safety_fields()
    assert fields["broker_api_called"] is True
    assert fields["broker_api_call_count"] == 1
    assert fields["broker_api_call_failure_count"] == 1
    assert fields["broker_api_rest_call_failure_count"] == 1
    rows = _rows(path)
    assert rows[-1]["event"] == "BROKER_REST_CALL_FAILED"
    assert rows[-1]["error_type"] == "TimeoutError"
    assert "do not persist" not in path.read_text(encoding="utf-8")
    assert verify_read_only_broker_api_ledger(path)["status"] == "VERIFIED"
    ledger.close()


def test_ledger_counts_http_error_response_as_a_failed_api_call(tmp_path):
    path = tmp_path / "broker_api_calls.jsonl"
    ledger = ReadOnlyBrokerApiLedger(path)
    client = _Client(status_code=403)
    ledger.instrument_client(client)

    response = client.reqsession.request("GET", "https://api.kite.trade/user/profile")
    assert response.status_code == 403
    fields = ledger.safety_fields()
    assert fields["broker_api_called"] is True
    assert fields["broker_api_call_count"] == 1
    assert fields["broker_api_call_failure_count"] == 1
    assert fields["broker_api_rest_call_failure_count"] == 1
    assert _rows(path)[-1]["event"] == "BROKER_REST_CALL_HTTP_ERROR"
    ledger.close()


@pytest.mark.parametrize("url", [
    "https://api.kite.trade/user/profile",
    "https://api.kite.trade/user/margins",
    "https://api.kite.trade/user/margins/equity",
    "https://api.kite.trade/quote/ltp",
    "https://api.kite.trade/instruments/NSE",
    "https://api.kite.trade/instruments/historical/123/minute",
])
def test_read_only_allowlist_accepts_approved_get_endpoints(tmp_path, url):
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")
    client = _Client()
    ledger.instrument_client(client)
    response = client.reqsession.request("GET", url)
    assert response.status_code == 200
    assert ledger.safety_fields()["broker_api_call_count"] == 1
    ledger.close()


@pytest.mark.parametrize(
    "method,url",
    [
        ("POST", "https://api.kite.trade/orders/regular"),
        ("GET", "https://api.kite.trade/orders"),
        ("GET", "http://api.kite.trade/user/profile"),
        ("GET", "https://example.invalid/user/profile"),
        ("GET", "https://api.kite.trade/session/token"),
    ],
)
def test_ledger_blocks_non_read_only_or_unapproved_requests_before_transport(tmp_path, method, url):
    path = tmp_path / "broker_api_calls.jsonl"
    ledger = ReadOnlyBrokerApiLedger(path)
    client = _Client()
    ledger.instrument_client(client)

    with pytest.raises(BrokerApiPolicyViolation, match="BROKER_REST_ENDPOINT_NOT_ALLOWED"):
        client.reqsession.request(method, url)
    assert client.reqsession.calls == []
    fields = ledger.safety_fields()
    assert fields["broker_api_called"] is False
    assert fields["broker_api_call_count"] == 0
    assert fields["broker_api_call_attempt_count"] == 1
    assert fields["broker_api_call_blocked_count"] == 1
    row = _rows(path)[0]
    assert row["event"] == "BROKER_REST_CALL_BLOCKED"
    assert row["is_order_action"] is ("/orders" in url)
    assert verify_read_only_broker_api_ledger(path)["status"] == "VERIFIED"
    ledger.close()


def test_ledger_fails_closed_when_request_transport_cannot_be_instrumented(tmp_path):
    class UnknownClient:
        pass

    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")
    with pytest.raises(BrokerApiLedgerError, match="BROKER_API_ACCOUNTING_TRANSPORT_UNAVAILABLE"):
        ledger.instrument_client(UnknownClient())


def test_ledger_write_failure_prevents_request_dispatch(tmp_path):
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "missing-parent" / "broker_api_calls.jsonl")
    client = _Client()
    ledger.instrument_client(client)
    with pytest.raises(BrokerApiLedgerError, match="BROKER_API_LEDGER_WRITE_FAILED"):
        client.profile()
    assert client.reqsession.calls == []
    assert ledger.safety_fields()["broker_api_called"] is False
    assert ledger.safety_fields()["broker_api_call_attempt_count"] == 1
    assert ledger.safety_fields()["broker_api_ledger_write_failure_count"] == 1
    ledger.close()


def test_ledger_verifier_detects_tampered_event(tmp_path):
    path = tmp_path / "broker_api_calls.jsonl"
    ledger = ReadOnlyBrokerApiLedger(path)
    client = _Client()
    ledger.instrument_client(client)
    client.profile()
    ledger.close()

    row = _rows(path)[0]
    row["endpoint_path"] = "/orders"
    path.write_text(json.dumps(row) + "\n" + "\n".join(json.dumps(item) for item in _rows(path)[1:]) + "\n", encoding="utf-8")
    result = verify_read_only_broker_api_ledger(path)
    assert result["status"] == "BLOCKED"
    assert "LEDGER_INVALID" in result["reason"]


def test_kite_client_scopes_accounting_across_cached_clients_and_restores_transport(monkeypatch, tmp_path):
    import core.kite_client as kite_client_module

    manager = KiteClient()
    client = _Client()
    manager.kite = client
    manager._active_api_key = "api-key"
    manager._active_access_token = "access-token"
    monkeypatch.setattr(kite_client_module, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")
    original_request = client.reqsession.request

    with manager.observe_broker_api_calls(ledger):
        assert manager.ensure() is client
        manager.ensure().profile()
        assert ledger.safety_fields()["broker_api_call_count"] == 1

    assert client.reqsession.request == original_request
    manager.ensure().profile()
    assert ledger.safety_fields()["broker_api_call_count"] == 1
    assert len(_rows(tmp_path / "broker_api_calls.jsonl")) == 2


def test_kite_client_accounts_for_each_recreated_rest_session(monkeypatch, tmp_path):
    import core.kite_client as kite_client_module
    from config import config as cfg

    manager = KiteClient()
    clients = [_Client(), _Client()]
    next_client = iter(clients)
    manager._create_kite = lambda **_: next(next_client)
    monkeypatch.setattr(kite_client_module, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    monkeypatch.setattr(cfg, "KITE_CLIENT_REUSE_SESSION", False, raising=False)
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")

    with manager.observe_broker_api_calls(ledger):
        manager.ensure().profile()
        manager.ensure().profile()

    assert ledger.safety_fields()["broker_api_call_count"] == 2
    assert len(_rows(tmp_path / "broker_api_calls.jsonl")) == 4
    assert all("request" not in client.reqsession.__dict__ for client in clients)


def test_auth_health_profile_probe_is_accounted_by_observation_scope(monkeypatch, tmp_path):
    import core.auth_health as auth_health
    import core.kite_client as kite_client_module
    from config import config as cfg

    manager = KiteClient()
    fake = _Client()
    manager._create_kite = lambda **_: fake
    monkeypatch.setattr(kite_client_module, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    monkeypatch.setattr(auth_health, "kite_client", manager)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(auth_health, "LOG_PATH", tmp_path / "auth-health.jsonl")
    auth_health._reset_cache_for_tests()
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")

    with manager.observe_broker_api_calls(ledger):
        payload = auth_health._kite_profile_payload()

    assert payload["ok"] is True
    assert ledger.safety_fields()["broker_api_call_count"] == 1
    assert _rows(tmp_path / "broker_api_calls.jsonl")[0]["endpoint_path"] == "/user/profile"


def test_feed_auth_failure_is_accounted_and_remains_blocked(monkeypatch, tmp_path):
    import core.auth_health as auth_health
    import core.kite_client as kite_client_module
    import core.kite_depth_ws as feed
    from config import config as cfg

    class MissingUserClient(_Client):
        def profile(self):
            self.reqsession.request("GET", "https://api.kite.trade/user/profile")
            return {}

    manager = KiteClient()
    fake = MissingUserClient()
    manager._create_kite = lambda **_: fake
    monkeypatch.setattr(kite_client_module, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    monkeypatch.setattr(auth_health, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    monkeypatch.setattr(auth_health, "kite_client", manager)
    monkeypatch.setattr(feed, "kite_client", manager)
    monkeypatch.setattr(feed, "get_kite_auth_health", lambda **kwargs: auth_health.get_kite_auth_health(**kwargs))
    monkeypatch.setattr(feed, "_reconnect_recovery_blocked_active", lambda: False)
    monkeypatch.setattr(feed, "_reactor_terminal_restart_block_active", lambda: False)
    monkeypatch.setattr(feed, "_persist_runtime_snapshot_row", lambda **_: None)
    monkeypatch.setattr(feed, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed, "_mark_auth_required", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed, "_RUNTIME_STATE", "STOPPED", raising=False)
    monkeypatch.setattr(feed, "_LAST_RUNTIME_ERROR", "", raising=False)
    monkeypatch.setattr(feed, "KiteTicker", object(), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api-key", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "KITE_AUTH_RETRY_BACKOFF_SEC", 0, raising=False)
    monkeypatch.setattr(auth_health, "LOG_PATH", tmp_path / "auth-health.jsonl")
    auth_health._reset_cache_for_tests()
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")

    with manager.observe_broker_api_calls(ledger):
        started = feed.start_depth_ws([256265], skip_lock=True, skip_guard=True)

    assert started is False
    assert ledger.safety_fields()["broker_api_called"] is True
    assert ledger.safety_fields()["broker_api_call_count"] == 2
    assert ledger.safety_fields()["broker_api_call_failure_count"] == 0
    assert len(fake.reqsession.calls) == 2
    assert fake.reqsession.calls[0][1] == "https://api.kite.trade/user/profile"
    auth_health._reset_cache_for_tests()


def test_feed_lifecycle_evidence_uses_observer_run_accounting(monkeypatch, tmp_path):
    import core.kite_client as kite_client_module
    import core.kite_depth_ws as feed

    manager = KiteClient()
    fake = _Client()
    manager._create_kite = lambda **_: fake
    monkeypatch.setattr(kite_client_module, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    monkeypatch.setattr(feed, "kite_client", manager)
    monkeypatch.setattr(feed, "_nifty_mode_lifecycle_path", lambda: None)
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")

    with manager.observe_broker_api_calls(ledger):
        manager.ensure().profile()
        payload = feed._record_ws_subscription_operation(
            object(), [256265], callsite="synthetic", operation="subscribe",
            local_call_result="succeeded",
        )

    assert payload["broker_api_called"] is True
    assert payload["broker_api_measurement_scope"] == "KITE_CLIENT_REST_AND_KITE_MARKET_DATA_WEBSOCKET"
    assert payload["broker_api_call_count"] == 1
    assert payload["is_order_action"] is False
    assert payload["broker_write_authority"] is False


def test_observer_feed_accounts_websocket_attempt_without_claiming_rest_call(monkeypatch, tmp_path):
    import core.auth_health as auth_health
    import core.kite_client as kite_client_module
    import core.kite_depth_ws as feed
    from config import config as cfg

    class FakeTicker:
        socket_url = "wss://ws.kite.trade/?api_key=secret&access_token=secret"
        MODE_FULL = "full"
        MODE_QUOTE = "quote"

        def __init__(self):
            self.on_connect = None

        def subscribe(self, _tokens):
            pass

        def set_mode(self, _mode, _tokens):
            pass

        def connect(self, threaded=True):
            assert threaded is True
            self.on_connect(self, {})

        def close(self):
            pass

    manager = KiteClient()
    client = _Client()
    manager._create_kite = lambda **_: client
    ticker = FakeTicker()
    monkeypatch.setattr(kite_client_module, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    monkeypatch.setattr(auth_health, "get_kite_credentials", lambda **_: ("api-key", "access-token"))
    monkeypatch.setattr(auth_health, "kite_client", manager)
    monkeypatch.setattr(feed, "kite_client", manager)
    monkeypatch.setattr(feed, "get_kite_auth_health", lambda **_: {"ok": False, "auth_state": "PENDING_WEBSOCKET_AUTH"})
    monkeypatch.setattr(feed, "get_kite_ticker", lambda **_: ticker)
    monkeypatch.setattr(feed, "_reconnect_recovery_blocked_active", lambda: False)
    monkeypatch.setattr(feed, "_reactor_terminal_restart_block_active", lambda: False)
    monkeypatch.setattr(feed, "_persist_runtime_snapshot_row", lambda **_: None)
    monkeypatch.setattr(feed, "_log_ws", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed, "_mark_auth_required", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed, "_RUNTIME_STATE", "STOPPED", raising=False)
    monkeypatch.setattr(feed, "_LAST_RUNTIME_ERROR", "", raising=False)
    monkeypatch.setattr(feed, "KiteTicker", object(), raising=False)
    monkeypatch.setattr(cfg, "KITE_API_KEY", "api-key", raising=False)
    monkeypatch.setattr(cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(cfg, "KITE_AUTH_RETRY_BACKOFF_SEC", 0, raising=False)
    monkeypatch.setattr(auth_health, "LOG_PATH", tmp_path / "auth-health.jsonl")
    auth_health._reset_cache_for_tests()
    ledger = ReadOnlyBrokerApiLedger(tmp_path / "broker_api_calls.jsonl")

    with manager.observe_broker_api_calls(ledger):
        started = feed.start_depth_ws(
            [256265], auth_mode="read_only_observer", skip_lock=True, skip_guard=True,
        )
        assert started is True
        fields = ledger.verified_safety_fields()
        assert fields["broker_api_called"] is True
        assert fields["broker_api_call_count"] == 1
        assert fields["broker_api_rest_call_count"] == 0
        assert fields["broker_api_websocket_connect_count"] == 1

    auth_health._reset_cache_for_tests()
    feed.stop_depth_ws(reason="test_cleanup")
