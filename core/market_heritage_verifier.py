"""Independent verifier for published market heritage manifests.

Intentionally does not import or call the graph producer implementation.
It re-parses the serialized artifact and recomputes hashes and dependency
closure independently. Read-only, offline, and authority-free.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict, deque
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

MAX_MANIFEST_BYTES = 64 * 1_048_576
MAX_GRAPH_NODES = 10_000
MAX_GRAPH_EDGES = 50_000


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_prerequisite_semantics(*, nodes: dict[str, dict[str, Any]],
                                   edges: list[dict[str, Any]],
                                   manifest_session: dict[str, Any],
                                   decision_epoch: float | None) -> list[dict[str, str]]:
    """Independently verify frozen T-1 field semantics and their exact parents."""
    errors: list[dict[str, str]] = []
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if isinstance(edge, dict):
            incoming[str(edge.get("child_id"))].append(edge)
    required_strategy_ids = {
        "INTRADAY_OPENING_DRIVE_V1", "S1_MOMENTUM_OVERNIGHT_V1",
        "S4_MONDAY_OVERNIGHT_V1",
    }
    for node_id, node in nodes.items():
        body = node.get("payload")
        if not isinstance(body, dict) or body.get("strategy_id") not in required_strategy_ids:
            continue
        strategy_id = str(body.get("strategy_id"))
        field = str(body.get("field") or "")
        contract_id = body.get("contract_id")
        source_session = body.get("source_session")
        target_session = body.get("target_session")
        if target_session != manifest_session or not isinstance(source_session, dict):
            errors.append({"code": "T1_SESSION_IDENTITY_INVALID", "id": node_id})
            continue
        try:
            source_date = date.fromisoformat(str(source_session["trading_date"]))
            target_date = date.fromisoformat(str(target_session["trading_date"]))
        except (KeyError, TypeError, ValueError):
            errors.append({"code": "T1_SESSION_DATE_INVALID", "id": node_id})
            continue
        parents = incoming.get(node_id, [])
        source_edges = [edge for edge in parents
            if edge.get("outcome") == "VERIFIED"
            and edge.get("requirement") == contract_id
            and str(edge.get("parent_id")) in nodes]
        if len(source_edges) != 1:
            errors.append({"code": "T1_EXACT_SOURCE_ANCESTOR_REQUIRED", "id": node_id})
            continue
        source = nodes[str(source_edges[0]["parent_id"])]
        source_body = source.get("payload")
        source_hash = _canonical_hash({k: v for k, v in source.items() if k != "node_id"})
        if (source.get("node_id") != body.get("content_sha256")
                or source.get("node_id") != source_hash
                or source.get("contract_id") != body.get("source_contract_id")
                or source.get("status") != "VERIFIED"
                or source.get("session") != source_session
                or source.get("instrument") != body.get("instrument")):
            errors.append({"code": "T1_SOURCE_PARENT_BINDING_INVALID", "id": node_id})
            continue
        calendar_edges = [edge for edge in parents
            if edge.get("outcome") == "VERIFIED"
            and edge.get("requirement") == "PREVIOUS_ELIGIBLE_SESSION"
            and str(edge.get("parent_id")) in nodes]
        if len(calendar_edges) != 1:
            errors.append({"code": "T1_PREVIOUS_ELIGIBLE_CALENDAR_ANCESTOR_REQUIRED", "id": node_id})
            continue
        calendar = nodes[str(calendar_edges[0]["parent_id"])]
        calendar_body = calendar.get("payload")
        if (calendar.get("status") != "VERIFIED"
                or calendar.get("session") != manifest_session
                or not isinstance(calendar_body, dict)
                or calendar_body.get("record_type") != "calendar_predecessor"
                or calendar_body.get("eligible") is not True
                or calendar_body.get("verified") is not True
                or calendar_body.get("predecessor_session") != source_session
                or calendar_body.get("target_session") != manifest_session
                or calendar_body.get("calendar_id") != manifest_session.get("calendar_id")
                or calendar_body.get("calendar_version") != manifest_session.get("calendar_version")):
            errors.append({"code": "T1_CALENDAR_ANCESTOR_MISMATCH", "id": node_id})
            continue
        if not isinstance(source_body, dict):
            errors.append({"code": "T1_SOURCE_PAYLOAD_REQUIRED", "id": node_id})
            continue
        if field == "opening_drive_prev_contract_key":
            expected_key = (body.get("instrument") or {}).get("contract_key")
            if (not expected_key or body.get("value") != expected_key
                    or source_body.get("record_type") != "FUTURES_CONTRACT_IDENTITY"
                    or source_body.get("contract_key") != body.get("value")):
                errors.append({"code": "T1_FUTURES_CONTRACT_CONTINUITY_MISMATCH", "id": node_id})
        elif field == "opening_drive_prev_close_1529":
            exact_bar_time = f"{source_date.isoformat()}T15:29:00+05:30"
            try:
                exact_epoch = datetime.fromisoformat(exact_bar_time).timestamp()
                event_epoch = float(source.get("source_event_epoch"))
            except (TypeError, ValueError, OverflowError):
                event_epoch = None
                exact_epoch = -1.0
            if (source_body.get("record_type") != "FUTURES_BAR"
                    or source_body.get("bar_interval") != "1m"
                    or source_body.get("bar_timestamp_semantics") != "BAR_END"
                    or source_body.get("bar_timestamp_ist") != exact_bar_time
                    or source_body.get("bar_status") != "COMPLETE"
                    or source_body.get("close") != body.get("value")
                    or event_epoch != exact_epoch):
                errors.append({"code": "T1_EXACT_1529_FUTURES_BAR_REQUIRED", "id": node_id})
        elif field == "overnight_prev_daily_close":
            if (source_body.get("record_type") != "NIFTY50_DAILY_CLOSE"
                    or source_body.get("trading_date") != source_date.isoformat()
                    or source_body.get("close") != body.get("value")):
                errors.append({"code": "T1_PREVIOUS_SESSION_DAILY_CLOSE_REQUIRED", "id": node_id})
        elif field == "overnight_prev_sma200":
            rows = source_body.get("rolling_close_rows")
            dates = calendar_body.get("rolling_session_dates")
            instrument = body.get("instrument")
            formula_id = body.get("rolling_formula_id")
            adjustment_id = body.get("rolling_adjustment_id")
            if (not isinstance(rows, list) or len(rows) != 200
                    or not isinstance(dates, list) or len(dates) != 200
                    or dates[-1] != source_date.isoformat()
                    or formula_id != "sma200-daily-close-v1"):
                errors.append({"code": "T1_COMPLETE_SMA200_ANCESTRY_REQUIRED", "id": node_id})
                continue
            normalized = []
            valid = True
            for row in rows:
                if not isinstance(row, dict):
                    valid = False
                    break
                try:
                    row_date = date.fromisoformat(str(row["trading_date"]))
                    close = float(row["close"])
                    row_available = float(row["available_epoch"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    valid = False
                    break
                row_hash = row.get("content_sha256")
                if (row.get("verification_status") != "VERIFIED"
                        or row.get("instrument") != instrument
                        or row.get("calendar_id") != manifest_session.get("calendar_id")
                        or row.get("calendar_version") != manifest_session.get("calendar_version")
                        or row.get("formula_id") != formula_id
                        or row.get("eligible_session") is not True
                        or row.get("complete") is not True
                        or row.get("adjustment_id") != adjustment_id
                        or not isinstance(row_hash, str) or len(row_hash) != 64
                        or any(char not in "0123456789abcdef" for char in row_hash)
                        or row_hash != _canonical_hash({key: value for key, value in row.items()
                            if key != "content_sha256"})
                        or not math.isfinite(close) or close <= 0
                        or (decision_epoch is not None and row_available > float(decision_epoch))):
                    valid = False
                    break
                normalized.append((row_date, close, row_hash))
            normalized.sort(key=lambda item: item[0])
            actual_dates = [item[0].isoformat() for item in normalized]
            if (not valid or actual_dates != dates or dates != sorted(set(dates))
                    or dates[-1] >= target_date.isoformat()):
                errors.append({"code": "T1_SMA200_SERIES_INVALID_OR_INCOMPLETE", "id": node_id})
                continue
            recomputed = math.fsum(item[1] for item in normalized) / 200
            hashes = [item[2] for item in normalized]
            calculation = _canonical_hash({"formula_id": formula_id, "window": 200,
                "source_hashes": hashes, "value": recomputed,
                "target_session": target_date.isoformat()})
            if (recomputed != body.get("value")
                    or calculation != body.get("rolling_computation_sha256")):
                errors.append({"code": "T1_SMA200_INDEPENDENT_RECOMPUTATION_MISMATCH", "id": node_id})
    return errors


def _verify_cas_node_semantics(*, node_id: str, node: dict[str, Any],
                               manifest_session: dict[str, Any]) -> list[dict[str, str]]:
    """Verify serialized CAS event binding without importing its producer."""
    errors: list[dict[str, str]] = []
    outer = node.get("payload")
    if not isinstance(outer, dict) or outer.get("record_type") != "cas_primitive":
        return errors
    row = outer.get("primitive")
    if not isinstance(row, dict):
        return [{"code": "CAS_PRIMITIVE_SHAPE_INVALID", "id": node_id}]
    def fail(code: str) -> None:
        errors.append({"code": code, "id": node_id})
    token = row.get("underlying_token")
    event = row.get("source_event_payload")
    event_hash = row.get("source_event_sha256")
    name = row.get("primitive_name")
    targets = {"0915": "09:15:00.000", "1000": "10:00:00.000"}
    if (row.get("schema_version") != 1 or row.get("capture_status") != "CAPTURED"
            or row.get("captured_live_prospectively") is not True
            or row.get("immutable") is not True
            or row.get("admissible_for_prospective_campaign") is not True
            or row.get("underlying_symbol") != "NIFTY"
            or outer.get("run_id") != row.get("session_id")):
        fail("CAS_PRIMITIVE_STATUS_OR_RUN_ID_INVALID")
    if (row.get("target_timestamp_ist") != targets.get(name)
            or node.get("instrument") != {"symbol": "NIFTY", "token": token}
                or not isinstance(row.get("source_sha"), str)
                or len(row.get("source_sha", "")) not in {40, 64}
                or any(char not in "0123456789abcdef" for char in row.get("source_sha", ""))):
        fail("CAS_PRIMITIVE_TARGET_OR_INSTRUMENT_INVALID")
    try:
        if not isinstance(event, dict):
            raise ValueError("payload")
        calculated_event_hash = _canonical_hash(event)
        price = float(row["price"])
        selected = float(row["timestamp_epoch"])
        source = float(row["source_timestamp_epoch"])
        receive = float(row["receive_timestamp_epoch"])
        target = float(row["target_timestamp_epoch"])
        lateness = int(row["lateness_ms"])
        if (not all(math.isfinite(value) for value in (price, selected, source, receive, target))
                or price <= 0 or selected != source
                or source < target or (source - target) * 1000 > 2000
                or lateness != int(round((selected - target) * 1000))):
            fail("CAS_PRIMITIVE_TIME_OR_PRICE_INVALID")
        if (event_hash != calculated_event_hash
                or row.get("record_sha256") != _canonical_hash({k: v for k, v in row.items() if k != "record_sha256"})
                or node.get("source_sha256") != event_hash
                or not isinstance(row.get("source_event_id"), str)
                or not row["source_event_id"].endswith(f":{token}:{calculated_event_hash[:16]}")
                or event.get("instrument_token") != token
                or event.get("underlying_symbol") != row.get("underlying_symbol")
                or float(event.get("last_price")) != price
                or float(event.get("source_timestamp_epoch")) != source
                or event.get("source_timestamp_field") != row.get("timestamp_source_field")
                or node.get("source_event_epoch") != source
                or node.get("receive_epoch") != receive
                or node.get("available_epoch") != selected):
            fail("CAS_PRIMITIVE_SOURCE_EVENT_BINDING_INVALID")
        if row.get("timestamp_authority") != "EXCHANGE_TIMESTAMP" or row.get("timestamp_fallback_used") is not False:
            fail("CAS_PRIMITIVE_TIMESTAMP_AUTHORITY_INVALID")
        source_date = datetime.fromtimestamp(source, tz=ZoneInfo("Asia/Kolkata")).date()
        manifest_date = date.fromisoformat(str(manifest_session.get("trading_date")))
        expected_target = datetime.fromisoformat(
            f"{source_date.isoformat()}T{targets.get(name, '00:00:00.000')}+05:30").timestamp()
        target_date = datetime.fromtimestamp(target, tz=ZoneInfo("Asia/Kolkata")).date()
        if source_date != manifest_date or target_date != source_date or target != expected_target:
            fail("CAS_PRIMITIVE_TRADING_SESSION_OR_TARGET_DATE_INVALID")
    except (KeyError, TypeError, ValueError, OverflowError):
        fail("CAS_PRIMITIVE_FIELDS_MALFORMED")
    return errors


def _verify_run_coverage_node(*, node_id: str, node: dict[str, Any],
                              manifest_session: dict[str, Any]) -> list[dict[str, str]]:
    """Independently bind the run coverage record to its session and digest."""
    outer = node.get("payload")
    if not isinstance(outer, dict) or outer.get("record_type") != "run_coverage":
        return []
    report = outer.get("coverage_report")
    if not isinstance(report, dict):
        return [{"code": "RUN_COVERAGE_REPORT_REQUIRED", "id": node_id}]
    errors: list[dict[str, str]] = []
    try:
        report_hash = _canonical_hash(report)
        start = float(report["run_started_epoch"])
        end = float(report["run_ended_epoch"])
        intended = report["intended_tokens"]
        per_token = report["per_token"]
    except (KeyError, TypeError, ValueError, OverflowError):
        return [{"code": "RUN_COVERAGE_REPORT_MALFORMED", "id": node_id}]
    if (node.get("contract_id") != "READ_ONLY_TICK_COVERAGE_V1"
            or outer.get("run_id") != report.get("run_id")
            or node.get("logical_key") != f"coverage:{manifest_session.get('trading_date')}:{report.get('run_id')}"
            or node.get("source_ref") != f"coverage://{report.get('run_id')}/read-only-tick-callbacks"
            or node.get("session") != manifest_session
            or report.get("session_identity") != manifest_session
            or node.get("source_sha256") != report_hash
            or node.get("source_event_epoch") != start
            or node.get("receive_epoch") != end
            or node.get("available_epoch") != end
            or not math.isfinite(start) or not math.isfinite(end) or end < start
            or report.get("read_only") is not True
            or report.get("append") is not False
            or report.get("is_order_action") is not False
            or report.get("broker_api_called") is not False
            or report.get("broker_write_authority") is not False
            or report.get("order_authority") is not False
            or report.get("paper_authorized") is not False
            or report.get("live_authorized") is not False
            or report.get("allowed_for_live_execution") is not False
            or not isinstance(intended, list)
            or len(intended) != report.get("intended_token_count")
            or len({str(token) for token in intended}) != len(intended)
            or any(not isinstance(token, int) or isinstance(token, bool) or token <= 0 for token in intended)
            or not isinstance(per_token, dict)
            or {str(token) for token in intended} != set(per_token)):
        errors.append({"code": "RUN_COVERAGE_IDENTITY_OR_HASH_INVALID", "id": node_id})
    return errors


def verify_market_heritage_manifest(path: str | Path, *, decision_epoch: float | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    try:
        artifact = Path(path)
        if artifact.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("MANIFEST_SIZE_BOUND_EXCEEDED")
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("UNSUPPORTED_MANIFEST_SCHEMA")
        session = payload.get("session_identity")
        if not isinstance(session, dict) or not all(session.get(name) for name in ("trading_date", "venue", "calendar_id", "calendar_version")):
            errors.append({"code": "MANIFEST_SESSION_IDENTITY_REQUIRED", "id": "manifest"})
        nodes = payload.get("nodes")
        edges = payload.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise ValueError("MANIFEST_GRAPH_SHAPE_INVALID")
        if len(nodes) > MAX_GRAPH_NODES or len(edges) > MAX_GRAPH_EDGES:
            raise ValueError("MANIFEST_GRAPH_BOUND_EXCEEDED")
        by_id: dict[str, dict[str, Any]] = {}
        by_key: dict[str, set[str]] = defaultdict(set)
        for node in nodes:
            if not isinstance(node, dict):
                errors.append({"code": "NODE_SHAPE_INVALID", "id": "unknown"})
                continue
            node_id = node.get("node_id")
            body = {key: value for key, value in node.items() if key != "node_id"}
            try:
                calculated = _canonical_hash(body)
            except (TypeError, ValueError):
                calculated = ""
            if node.get("schema_version") != 1:
                errors.append({"code": "UNSUPPORTED_NODE_SCHEMA", "id": str(node_id)})
            if (not isinstance(node.get("logical_key"), str) or not node.get("logical_key")
                    or not isinstance(node.get("source_ref"), str) or not node.get("source_ref")
                    or not isinstance(node.get("source_sha256"), str) or len(node.get("source_sha256", "")) != 64
                    or any(char not in "0123456789abcdef" for char in node.get("source_sha256", ""))
                    or any(char not in "0123456789abcdef" for char in node.get("source_sha256", ""))
                    or not isinstance(node.get("session"), dict) or not node.get("session")
                    or not isinstance(node.get("instrument"), dict) or not node.get("instrument")
                    or not isinstance(node.get("contract_id"), str) or not node.get("contract_id")
                    or not isinstance(node.get("payload"), dict)
                    or not isinstance(node.get("coverage"), dict)):
                errors.append({"code": "NODE_SCHEMA_FIELDS_INVALID", "id": str(node_id)})
            for time_field in ("source_event_epoch", "receive_epoch", "available_epoch"):
                value = node.get(time_field)
                if value is not None:
                    try:
                        if not math.isfinite(float(value)):
                            raise ValueError
                    except (TypeError, ValueError):
                        errors.append({"code": "INVALID_NODE_TIME", "id": str(node_id) + ":" + time_field})
            if node_id != calculated:
                errors.append({"code": "NODE_HASH_MISMATCH", "id": str(node_id)})
            if node_id in by_id:
                errors.append({"code": "DUPLICATE_NODE_ID", "id": str(node_id)})
            if node_id not in by_id:
                by_id[str(node_id)] = node
            by_key[str(node.get("logical_key"))].add(str(node_id))
            available = node.get("available_epoch")
            if decision_epoch is not None and available is not None:
                try:
                    if float(available) > float(decision_epoch):
                        errors.append({"code": "FUTURE_INFORMATION", "id": str(node_id)})
                except (TypeError, ValueError):
                    errors.append({"code": "INVALID_AVAILABLE_EPOCH", "id": str(node_id)})
        for logical_key, ids in sorted(by_key.items()):
            if len(ids) > 1:
                errors.append({"code": "LOGICAL_KEY_CONFLICT", "id": logical_key})
        if isinstance(session, dict):
            for node_id, node in sorted(by_id.items()):
                errors.extend(_verify_cas_node_semantics(node_id=node_id,
                    node=node, manifest_session=session))
                errors.extend(_verify_run_coverage_node(node_id=node_id,
                    node=node, manifest_session=session))
        outgoing: dict[str, list[str]] = defaultdict(list)
        indegree = {node_id: 0 for node_id in by_id}
        for edge in edges:
            if not isinstance(edge, dict):
                errors.append({"code": "EDGE_SHAPE_INVALID", "id": "unknown"})
                continue
            parent = str(edge.get("parent_id"))
            child = str(edge.get("child_id"))
            if parent not in by_id or child not in by_id:
                errors.append({"code": "UNRESOLVED_ANCESTOR", "id": parent + "->" + child})
                continue
            parent_body = {key: value for key, value in by_id[parent].items() if key != "node_id"}
            if edge.get("parent_hash") != _canonical_hash(parent_body):
                errors.append({"code": "PARENT_HASH_MISMATCH", "id": parent})
            if edge.get("outcome") != "VERIFIED":
                errors.append({"code": "DEPENDENCY_NOT_VERIFIED", "id": parent + "->" + child})
            if not isinstance(edge.get("requirement"), str) or not edge.get("requirement"):
                errors.append({"code": "EDGE_REQUIREMENT_REQUIRED", "id": parent + "->" + child})
            outgoing[parent].append(child)
            indegree[child] += 1
        ready = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
        visited = 0
        while ready:
            current = ready.popleft()
            visited += 1
            for child in sorted(outgoing[current]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if visited != len(by_id):
            errors.append({"code": "DEPENDENCY_CYCLE", "id": "graph"})
        graph_hash = _canonical_hash({"session_identity": session,
                                      "nodes": sorted(by_id),
                                      "edges": sorted(edges, key=lambda row: (row.get("parent_id", ""), row.get("child_id", ""), row.get("requirement", "")))})
        if payload.get("graph_sha256") != graph_hash:
            errors.append({"code": "GRAPH_HASH_MISMATCH", "id": "manifest"})
        if isinstance(session, dict):
            errors.extend(_verify_prerequisite_semantics(nodes=by_id, edges=edges,
                manifest_session=session, decision_epoch=decision_epoch))
        return {"verdict": "PASS" if not errors else "BLOCKED",
                "errors": errors, "node_count": len(nodes), "edge_count": len(edges),
                "manifest_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "read_only": True, "is_order_action": False,
                "broker_api_called": False, "allowed_for_live_execution": False}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"verdict": "BLOCKED", "errors": [{"code": "INVALID_MANIFEST", "id": str(exc)}],
                "node_count": 0, "edge_count": 0, "read_only": True,
                "is_order_action": False, "broker_api_called": False,
                "allowed_for_live_execution": False}
