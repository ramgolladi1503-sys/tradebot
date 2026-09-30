"""Fail-closed accounting for REST and websocket calls by a read-only Kite observer."""

from __future__ import annotations

import json
import hashlib
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class BrokerApiLedgerError(RuntimeError):
    """Raised when a broker request cannot be safely accounted for."""


class BrokerApiPolicyViolation(BrokerApiLedgerError):
    """Raised before transport for a non-approved observer API request."""


_READ_ONLY_GET_PATHS = frozenset({
    "/user/profile",
    "/user/margins",
    "/quote",
    "/quote/ohlc",
    "/quote/ltp",
    "/instruments",
})
_INSTRUMENT_EXCHANGES = frozenset({"NSE", "BSE", "NFO", "BFO", "CDS", "BCD", "MCX"})
_HISTORICAL_PATH = re.compile(r"^/instruments/historical/[0-9]+/[a-zA-Z0-9_]+$")
_MARGIN_PATH = re.compile(r"^/(?:user/margins(?:/(?:equity|commodity))?|margins/(?:equity|commodity))$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReadOnlyBrokerApiLedger:
    """Instrument Kite SDK request sessions and durably record each REST attempt.

    The log deliberately excludes headers, query parameters, request bodies, and
    exception messages because they can contain credentials or market data.
    Only HTTPS GET requests to explicitly approved Kite read-only REST paths and
    the fixed Kite market-data websocket endpoint are dispatched.
    """

    def __init__(self, evidence_path: Path):
        self.evidence_path = Path(evidence_path)
        if self.evidence_path.exists():
            raise BrokerApiLedgerError("BROKER_API_LEDGER_PATH_ALREADY_EXISTS")
        self._lock = threading.RLock()
        self._attempt_count = 0
        self._dispatched_count = 0
        self._rest_dispatched_count = 0
        self._rest_failure_count = 0
        self._websocket_dispatched_count = 0
        self._websocket_failure_count = 0
        self._failure_count = 0
        self._blocked_count = 0
        self._ledger_write_failure_count = 0
        self._ledger_event_count = 0
        self._ledger_head_sha256 = "0" * 64
        self._ledger_file_created = False
        self._sessions: dict[int, tuple[Any, Any, bool, Any]] = {}

    @staticmethod
    def _approved(method: str, url: str) -> tuple[bool, str, str]:
        try:
            parsed = urlsplit(str(url))
        except Exception:
            return False, "", ""
        path = parsed.path or "/"
        try:
            host_ok = (
                parsed.scheme.lower() == "https"
                and parsed.hostname == "api.kite.trade"
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
            )
        except ValueError:
            host_ok = False
        method_ok = str(method or "").upper() == "GET"
        path_ok = (
            path in _READ_ONLY_GET_PATHS
            or path in {f"/instruments/{exchange}" for exchange in _INSTRUMENT_EXCHANGES}
            or bool(_HISTORICAL_PATH.fullmatch(path))
            or bool(_MARGIN_PATH.fullmatch(path))
        )
        return host_ok and method_ok and path_ok, str(method or "").upper(), path

    def _append(self, row: dict[str, Any]) -> None:
        try:
            chained = {
                **row,
                "ledger_sequence": self._ledger_event_count + 1,
                "previous_event_sha256": self._ledger_head_sha256,
            }
            canonical = json.dumps(chained, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            event_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            chained["event_sha256"] = event_sha256
            encoded = json.dumps(chained, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            mode = "a" if self._ledger_file_created else "x"
            with self.evidence_path.open(mode, encoding="utf-8") as handle:
                handle.write(encoded + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._ledger_file_created = True
            self._ledger_event_count += 1
            self._ledger_head_sha256 = event_sha256
        except Exception as exc:
            with self._lock:
                self._ledger_write_failure_count += 1
            raise BrokerApiLedgerError("BROKER_API_LEDGER_WRITE_FAILED") from exc

    def instrument_client(self, client: Any) -> None:
        """Wrap a KiteConnect reqsession; fail closed if its transport is unknown."""
        session = getattr(client, "reqsession", None)
        if session is None or not callable(getattr(session, "request", None)):
            raise BrokerApiLedgerError("BROKER_API_ACCOUNTING_TRANSPORT_UNAVAILABLE")
        session_id = id(session)
        with self._lock:
            if session_id in self._sessions:
                return
            if getattr(session, "_tradebot_broker_api_ledger", None) is not None:
                raise BrokerApiLedgerError("BROKER_API_SESSION_ALREADY_INSTRUMENTED")
            original = session.request
            had_instance_override = "request" in getattr(session, "__dict__", {})
            previous_instance_value = getattr(session, "__dict__", {}).get("request")

            def tracked_request(method, url, *args, **kwargs):
                allowed, normalized_method, path = self._approved(method, url)
                with self._lock:
                    self._attempt_count += 1
                    call_id = self._attempt_count
                    if not allowed:
                        self._blocked_count += 1
                        self._append({
                            "event": "BROKER_REST_CALL_BLOCKED",
                            "call_id": call_id,
                            "method": normalized_method,
                            "endpoint_path": path if allowed else "<blocked>",
                            "recorded_at_utc": _utc_now(),
                            "read_only": True,
                            "is_order_action": path.startswith(("/orders", "/gtt", "/mf/orders")),
                            "broker_api_called": False,
                            "allowed_for_live_execution": False,
                        })
                        raise BrokerApiPolicyViolation("BROKER_REST_ENDPOINT_NOT_ALLOWED")
                    self._append({
                        "event": "BROKER_REST_CALL_DISPATCHED",
                        "call_id": call_id,
                        "method": normalized_method,
                        "endpoint_host": "api.kite.trade",
                        "endpoint_path": path,
                        "recorded_at_utc": _utc_now(),
                        "read_only": True,
                        "is_order_action": False,
                        "broker_api_called": True,
                        "allowed_for_live_execution": False,
                    })
                    self._dispatched_count += 1
                    self._rest_dispatched_count += 1
                try:
                    # Do not allow an approved URL to redirect the request to an
                    # unobserved host or endpoint.
                    transport_kwargs = dict(kwargs)
                    transport_kwargs["allow_redirects"] = False
                    response = original(normalized_method, url, *args, **transport_kwargs)
                except Exception as exc:
                    with self._lock:
                        self._failure_count += 1
                        self._rest_failure_count += 1
                        self._append({
                            "event": "BROKER_REST_CALL_FAILED",
                            "call_id": call_id,
                            "error_type": type(exc).__name__,
                            "recorded_at_utc": _utc_now(),
                            "read_only": True,
                            "is_order_action": False,
                            "broker_api_called": True,
                            "allowed_for_live_execution": False,
                        })
                    raise
                with self._lock:
                    try:
                        status = int(getattr(response, "status_code", 0) or 0)
                    except (TypeError, ValueError, OverflowError):
                        status = 0
                    is_http_error = status < 200 or status >= 300
                    if is_http_error:
                        self._failure_count += 1
                        self._rest_failure_count += 1
                    self._append({
                        "event": "BROKER_REST_CALL_HTTP_ERROR" if is_http_error else "BROKER_REST_CALL_COMPLETED",
                        "call_id": call_id,
                        "http_status": status,
                        "recorded_at_utc": _utc_now(),
                        "read_only": True,
                        "is_order_action": False,
                        "broker_api_called": True,
                        "allowed_for_live_execution": False,
                    })
                return response

            session.request = tracked_request
            session._tradebot_broker_api_ledger = self
            self._sessions[session_id] = (session, original, had_instance_override, previous_instance_value)

    def record_websocket_connect_attempt(self, url: str) -> int:
        """Durably record a Kite websocket dispatch before transport starts."""
        try:
            parsed = urlsplit(str(url))
            valid = (
                parsed.scheme.lower() == "wss"
                and parsed.hostname == "ws.kite.trade"
                and parsed.username is None
                and parsed.password is None
                and parsed.port in (None, 443)
                and (parsed.path or "/") == "/"
            )
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise BrokerApiPolicyViolation("BROKER_WEBSOCKET_ENDPOINT_NOT_ALLOWED")
        with self._lock:
            self._attempt_count += 1
            call_id = self._attempt_count
            self._append({
                "event": "BROKER_WEBSOCKET_CALL_DISPATCHED",
                "call_id": call_id,
                "transport": "websocket",
                "endpoint_host": "ws.kite.trade",
                "endpoint_path": "/",
                "recorded_at_utc": _utc_now(),
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": True,
                "allowed_for_live_execution": False,
            })
            self._dispatched_count += 1
            self._websocket_dispatched_count += 1
            return call_id

    def record_websocket_connect_outcome(self, call_id: int, *, error: Exception | None = None) -> None:
        """Record synchronous connect scheduling outcome without exception text."""
        with self._lock:
            if error is None:
                event = "BROKER_WEBSOCKET_CALL_SCHEDULED"
            else:
                event = "BROKER_WEBSOCKET_CALL_FAILED"
                self._failure_count += 1
                self._websocket_failure_count += 1
            self._append({
                "event": event,
                "call_id": int(call_id),
                "error_type": type(error).__name__ if error is not None else None,
                "recorded_at_utc": _utc_now(),
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": True,
                "allowed_for_live_execution": False,
            })

    def safety_fields(self) -> dict[str, Any]:
        with self._lock:
            return {
                "broker_api_measurement_scope": "KITE_CLIENT_REST_AND_KITE_MARKET_DATA_WEBSOCKET",
                "broker_api_called": self._dispatched_count > 0,
                "broker_api_call_count": self._dispatched_count,
                "broker_api_rest_call_count": self._rest_dispatched_count,
                "broker_api_rest_called": self._rest_dispatched_count > 0,
                "broker_api_rest_call_failure_count": self._rest_failure_count,
                "broker_api_websocket_connect_count": self._websocket_dispatched_count,
                "broker_api_websocket_failure_count": self._websocket_failure_count,
                "broker_api_call_attempt_count": self._attempt_count,
                "broker_api_call_failure_count": self._failure_count,
                "broker_api_call_blocked_count": self._blocked_count,
                "broker_api_ledger_write_failure_count": self._ledger_write_failure_count,
                "broker_api_call_ledger_event_count": self._ledger_event_count,
                "broker_api_call_ledger_head_sha256": self._ledger_head_sha256,
                "broker_api_call_ledger_verified": False,
                "broker_api_call_ledger_verification_status": "PENDING",
                "broker_write_authority": False,
                "order_authority": False,
                "paper_authorized": False,
                "live_authorized": False,
            }

    def verified_safety_fields(self) -> dict[str, Any]:
        verification = verify_read_only_broker_api_ledger(self.evidence_path)
        fields = self.safety_fields()
        if not self.evidence_path.exists() and fields["broker_api_call_attempt_count"] == 0:
            verification = {
                "status": "VERIFIED",
                "broker_api_measurement_scope": "KITE_CLIENT_REST_AND_KITE_MARKET_DATA_WEBSOCKET",
                "event_count": 0,
                "broker_api_called": False,
                "broker_api_call_count": 0,
                "broker_api_rest_call_count": 0,
                "broker_api_rest_called": False,
                "broker_api_rest_call_failure_count": 0,
                "broker_api_websocket_connect_count": 0,
                "broker_api_websocket_failure_count": 0,
                "broker_api_call_blocked_count": 0,
                "broker_api_call_failure_count": 0,
                "ledger_head_sha256": "0" * 64,
            }
        matches = (
            verification.get("status") == "VERIFIED"
            and verification.get("event_count") == fields["broker_api_call_ledger_event_count"]
            and verification.get("broker_api_called") == fields["broker_api_called"]
            and verification.get("broker_api_call_count") == fields["broker_api_call_count"]
            and verification.get("broker_api_rest_call_count") == fields["broker_api_rest_call_count"]
            and verification.get("broker_api_rest_call_failure_count") == fields["broker_api_rest_call_failure_count"]
            and verification.get("broker_api_websocket_connect_count") == fields["broker_api_websocket_connect_count"]
            and verification.get("broker_api_websocket_failure_count") == fields["broker_api_websocket_failure_count"]
            and verification.get("broker_api_call_blocked_count") == fields["broker_api_call_blocked_count"]
            and verification.get("broker_api_call_failure_count") == fields["broker_api_call_failure_count"]
            and verification.get("ledger_head_sha256") == fields["broker_api_call_ledger_head_sha256"]
            and fields["broker_api_ledger_write_failure_count"] == 0
            and fields["broker_api_call_attempt_count"] == (
                fields["broker_api_call_count"] + fields["broker_api_call_blocked_count"]
            )
        )
        if not matches:
            raise BrokerApiLedgerError("BROKER_API_LEDGER_VERIFICATION_FAILED")
        return {
            **fields,
            "broker_api_call_ledger_verified": True,
            "broker_api_call_ledger_verification_status": "VERIFIED",
        }

    def close(self) -> None:
        """Restore each request method and surface any transport ownership drift."""
        failures = []
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session, original, had_override, previous_value in sessions:
            if getattr(session, "_tradebot_broker_api_ledger", None) is not self:
                failures.append("BROKER_API_SESSION_OWNERSHIP_CHANGED")
                continue
            try:
                if had_override:
                    session.request = previous_value
                else:
                    delattr(session, "request")
                delattr(session, "_tradebot_broker_api_ledger")
            except Exception:
                failures.append("BROKER_API_SESSION_RESTORE_FAILED")
        if failures:
            raise BrokerApiLedgerError(failures[0])


def verify_read_only_broker_api_ledger(path: Path) -> dict[str, Any]:
    """Independently verify the append-only hash chain and call outcomes."""
    ledger_path = Path(path)
    if not ledger_path.is_file():
        return {
            "status": "BLOCKED", "reason": "BROKER_API_LEDGER_MISSING",
            "event_count": 0, "broker_api_called": False,
            "broker_api_call_count": 0, "broker_api_call_blocked_count": 0,
            "broker_api_rest_call_count": 0, "broker_api_websocket_connect_count": 0,
            "broker_api_rest_call_failure_count": 0,
            "broker_api_websocket_failure_count": 0,
            "broker_api_call_failure_count": 0, "ledger_head_sha256": "0" * 64,
        }
    previous_sha = "0" * 64
    rows: list[dict[str, Any]] = []
    try:
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("ledger_row_not_object")
            event_sha = str(row.pop("event_sha256", ""))
            canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            expected_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if row.get("ledger_sequence") != len(rows) + 1 or row.get("previous_event_sha256") != previous_sha or event_sha != expected_sha:
                raise ValueError("ledger_hash_chain_invalid")
            row["event_sha256"] = event_sha
            previous_sha = event_sha
            rows.append(row)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return {"status": "BLOCKED", "reason": f"BROKER_API_LEDGER_INVALID:{type(exc).__name__}"}
    dispatched: dict[int, dict[str, Any]] = {}
    terminal_ids: set[int] = set()
    attempt_ids: set[int] = set()
    blocked_count = 0
    failure_count = 0
    rest_dispatched_count = 0
    rest_failure_count = 0
    websocket_dispatched_count = 0
    websocket_failure_count = 0
    for row in rows:
        event = row.get("event")
        call_id = row.get("call_id")
        if not isinstance(call_id, int) or call_id <= 0:
            return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_CALL_ID_INVALID"}
        if event == "BROKER_REST_CALL_DISPATCHED":
            allowed, _, _ = ReadOnlyBrokerApiLedger._approved(
                row.get("method", ""),
                f"https://{row.get('endpoint_host', '')}{row.get('endpoint_path', '')}",
            )
            if (not allowed or row.get("read_only") is not True
                    or row.get("is_order_action") is not False
                    or row.get("broker_api_called") is not True
                    or row.get("allowed_for_live_execution") is not False
                    or call_id in attempt_ids):
                return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_DISPATCH_INVALID"}
            attempt_ids.add(call_id)
            dispatched[call_id] = row
            rest_dispatched_count += 1
        elif event == "BROKER_WEBSOCKET_CALL_DISPATCHED":
            valid_endpoint = (
                row.get("transport") == "websocket"
                and row.get("endpoint_host") == "ws.kite.trade"
                and row.get("endpoint_path") == "/"
            )
            if (not valid_endpoint or row.get("read_only") is not True
                    or row.get("is_order_action") is not False
                    or row.get("broker_api_called") is not True
                    or row.get("allowed_for_live_execution") is not False
                    or call_id in attempt_ids):
                return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_WEBSOCKET_DISPATCH_INVALID"}
            attempt_ids.add(call_id)
            dispatched[call_id] = row
            websocket_dispatched_count += 1
        elif event == "BROKER_REST_CALL_BLOCKED":
            blocked_count += 1
            if (row.get("read_only") is not True or row.get("broker_api_called") is not False
                    or row.get("allowed_for_live_execution") is not False
                    or call_id in attempt_ids):
                return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_BLOCKED_EVENT_INVALID"}
            attempt_ids.add(call_id)
        elif event in {"BROKER_REST_CALL_COMPLETED", "BROKER_REST_CALL_HTTP_ERROR", "BROKER_REST_CALL_FAILED", "BROKER_WEBSOCKET_CALL_SCHEDULED", "BROKER_WEBSOCKET_CALL_FAILED"}:
            is_ws = event.startswith("BROKER_WEBSOCKET_")
            if is_ws:
                if (call_id not in dispatched or call_id in terminal_ids
                        or dispatched[call_id].get("event") != "BROKER_WEBSOCKET_CALL_DISPATCHED"
                        or row.get("read_only") is not True
                        or row.get("is_order_action") is not False
                        or row.get("broker_api_called") is not True
                        or row.get("allowed_for_live_execution") is not False
                        or (event == "BROKER_WEBSOCKET_CALL_FAILED" and not row.get("error_type"))):
                    return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_WEBSOCKET_TERMINAL_INVALID"}
                if event == "BROKER_WEBSOCKET_CALL_FAILED":
                    failure_count += 1
                    websocket_failure_count += 1
                terminal_ids.add(call_id)
                continue
            status = row.get("http_status")
            valid_status = isinstance(status, int) and (200 <= status < 300)
            if event == "BROKER_REST_CALL_COMPLETED" and not valid_status:
                return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_SUCCESS_STATUS_INVALID"}
            if event == "BROKER_REST_CALL_HTTP_ERROR" and (not isinstance(status, int) or 200 <= status < 300):
                return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_ERROR_STATUS_INVALID"}
            if (call_id not in dispatched or call_id in terminal_ids
                    or row.get("read_only") is not True
                    or row.get("broker_api_called") is not True
                    or row.get("allowed_for_live_execution") is not False):
                return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_TERMINAL_EVENT_INVALID"}
            if event != "BROKER_REST_CALL_COMPLETED":
                failure_count += 1
                rest_failure_count += 1
            terminal_ids.add(call_id)
        else:
            return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_EVENT_UNKNOWN"}
    if set(dispatched) != terminal_ids:
        return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_CALL_OUTCOME_MISSING"}
    if attempt_ids != {row.get("call_id") for row in rows if row.get("event") in {
        "BROKER_REST_CALL_DISPATCHED", "BROKER_REST_CALL_BLOCKED",
        "BROKER_WEBSOCKET_CALL_DISPATCHED",
    }}:
        return {"status": "BLOCKED", "reason": "BROKER_API_LEDGER_ATTEMPT_IDENTITY_INVALID"}
    return {
        "status": "VERIFIED",
        "event_count": len(rows),
        "broker_api_called": bool(dispatched),
        "broker_api_call_count": len(dispatched),
        "broker_api_rest_call_count": rest_dispatched_count,
        "broker_api_rest_call_failure_count": rest_failure_count,
        "broker_api_websocket_connect_count": websocket_dispatched_count,
        "broker_api_websocket_failure_count": websocket_failure_count,
        "broker_api_call_blocked_count": blocked_count,
        "broker_api_call_failure_count": failure_count,
        "ledger_head_sha256": previous_sha,
    }
