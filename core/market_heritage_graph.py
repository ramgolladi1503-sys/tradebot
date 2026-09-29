"""Content-addressed, read-only-verifiable market evidence heritage primitives.

This module records provenance and dependencies only. It has no runtime, broker,
strategy, candidate, or execution wiring. Unknown source authority stays unknown.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import tempfile
import time
import math
from collections import defaultdict, deque
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
MAX_NODE_BYTES = 1_048_576
MAX_GRAPH_NODES = 10_000
MAX_GRAPH_EDGES = 50_000
MAX_MANIFEST_BYTES = 64 * 1_048_576
MAX_INDEX_BYTES = 1_048_576
MAX_LEGACY_RUNS = 256
MAX_LEGACY_FILES = 4096
MAX_LEGACY_FILE_BYTES = 64 * 1_048_576
MAX_LEGACY_TOTAL_BYTES = 512 * 1_048_576
AUTHORITY = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def rolling_source_row_hash(row: Mapping[str, Any]) -> str:
    """Hash the complete normalized daily-close row except its digest field."""
    return content_hash({key: value for key, value in row.items()
        if key != "content_sha256"})


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def make_node(*, logical_key: str, payload: Mapping[str, Any], source_ref: str,
              source_sha256: str, session: Mapping[str, Any], instrument: Mapping[str, Any],
              contract_id: str, source_event_epoch: float | None,
              receive_epoch: float | None, available_epoch: float | None,
              status: str = "OBSERVED", coverage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a content addressed node without promoting its evidence status."""
    if not logical_key or not source_ref or not contract_id:
        raise ValueError("MISSING_NODE_IDENTITY")
    if not _valid_hash(source_sha256):
        raise ValueError("INVALID_SOURCE_HASH")
    if len(canonical_bytes(payload)) > MAX_NODE_BYTES:
        raise ValueError("NODE_PAYLOAD_BOUND_EXCEEDED")
    for name, epoch in (("source_event_epoch", source_event_epoch),
                        ("receive_epoch", receive_epoch),
                        ("available_epoch", available_epoch)):
        if epoch is not None and (not isinstance(epoch, (int, float)) or not math.isfinite(float(epoch))):
            raise ValueError("INVALID_NODE_TIME:" + name)
    if not isinstance(payload, Mapping) or not isinstance(coverage or {}, Mapping):
        raise ValueError("INVALID_NODE_PAYLOAD_OR_COVERAGE")
    for name, epoch in (("source_event_epoch", source_event_epoch),
                        ("receive_epoch", receive_epoch),
                        ("available_epoch", available_epoch)):
        if epoch is not None and (not isinstance(epoch, (int, float)) or not math.isfinite(float(epoch))):
            raise ValueError("INVALID_NODE_TIME:" + name)
    if not isinstance(payload, Mapping) or not isinstance(coverage or {}, Mapping):
        raise ValueError("INVALID_NODE_PAYLOAD_OR_COVERAGE")
    for field, identity in (("session", session), ("instrument", instrument)):
        if not isinstance(identity, Mapping) or not identity:
            raise ValueError("MISSING_" + field.upper() + "_IDENTITY")
    body = {
        "schema_version": SCHEMA_VERSION,
        "logical_key": logical_key,
        "payload": dict(payload),
        "source_ref": source_ref,
        "source_sha256": source_sha256,
        "session": dict(session),
        "instrument": dict(instrument),
        "contract_id": contract_id,
        "source_event_epoch": source_event_epoch,
        "receive_epoch": receive_epoch,
        "available_epoch": available_epoch,
        "status": str(status),
        "coverage": dict(coverage or {}),
    }
    return {**body, "node_id": content_hash(body)}


def _atomic_publish(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("PUBLISHED_ARTIFACT_SIZE_BOUND_EXCEEDED")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # Immutable manifest names are content addressed. Never replace a
        # different existing payload at the same path.
        try:
            os.link(tmp_name, path)
        except FileExistsError:
            if path.stat().st_size > MAX_MANIFEST_BYTES:
                raise ValueError("IMMUTABLE_ARTIFACT_SIZE_BOUND_EXCEEDED")
            if path.read_bytes() != encoded:
                raise ValueError("IMMUTABLE_MANIFEST_CONFLICT")
        os.unlink(tmp_name)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # Some filesystems do not support directory fsync. File content
            # and atomic no-clobber publication are still enforced.
            pass
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256(encoded).hexdigest():
            raise OSError("PUBLISHED_MANIFEST_HASH_MISMATCH")
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class HeritageGraph:
    """Append-only set of immutable nodes/edges with deterministic closure."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.logical_keys: dict[str, set[str]] = defaultdict(set)
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_node(self, node: Mapping[str, Any]) -> str:
        row = dict(node)
        node_id = row.get("node_id")
        body = {key: value for key, value in row.items() if key != "node_id"}
        if row.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_NODE_SCHEMA")
        if node_id not in self.nodes and len(self.nodes) >= MAX_GRAPH_NODES:
            raise ValueError("GRAPH_NODE_BOUND_EXCEEDED")
        if len(canonical_bytes(row)) > MAX_NODE_BYTES + 16_384:
            raise ValueError("NODE_SIZE_BOUND_EXCEEDED")
        if (not isinstance(row.get("logical_key"), str) or not row["logical_key"].strip()
                or not isinstance(row.get("source_ref"), str) or not row["source_ref"].strip()
                or not _valid_hash(row.get("source_sha256"))
                or not isinstance(row.get("session"), Mapping) or not row["session"]
                or not isinstance(row.get("instrument"), Mapping) or not row["instrument"]
                or not isinstance(row.get("contract_id"), str) or not row["contract_id"].strip()
                or not isinstance(row.get("payload"), Mapping)
                or not isinstance(row.get("coverage"), Mapping)):
            raise ValueError("NODE_SCHEMA_FIELDS_INVALID")
        for field in ("source_event_epoch", "receive_epoch", "available_epoch"):
            value = row.get(field)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(float(value))):
                raise ValueError("INVALID_NODE_TIME:" + field)
        if (not isinstance(row.get("logical_key"), str) or not row["logical_key"].strip()
                or not isinstance(row.get("source_ref"), str) or not row["source_ref"].strip()
                or not _valid_hash(row.get("source_sha256"))
                or not isinstance(row.get("session"), Mapping) or not row["session"]
                or not isinstance(row.get("instrument"), Mapping) or not row["instrument"]
                or not isinstance(row.get("contract_id"), str) or not row["contract_id"].strip()
                or not isinstance(row.get("payload"), Mapping)
                or not isinstance(row.get("coverage"), Mapping)):
            raise ValueError("NODE_SCHEMA_FIELDS_INVALID")
        for field in ("source_event_epoch", "receive_epoch", "available_epoch"):
            value = row.get(field)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(float(value))):
                raise ValueError("INVALID_NODE_TIME:" + field)
        if not isinstance(node_id, str) or content_hash(body) != node_id:
            raise ValueError("NODE_HASH_MISMATCH")
        if node_id in self.nodes and self.nodes[node_id] != row:
            raise ValueError("NODE_ID_COLLISION")
        self.nodes[node_id] = row
        self.logical_keys[str(row["logical_key"])].add(node_id)
        return node_id

    def add_edge(self, *, parent_id: str, child_id: str, requirement: str,
                 parent_hash: str, outcome: str = "VERIFIED", reason: str = "") -> None:
        if parent_id not in self.nodes or child_id not in self.nodes:
            raise ValueError("UNRESOLVED_ANCESTOR")
        if not isinstance(requirement, str) or not requirement.strip():
            raise ValueError("EDGE_REQUIREMENT_REQUIRED")
        if outcome not in {"VERIFIED", "BLOCKED", "UNKNOWN"}:
            raise ValueError("EDGE_OUTCOME_INVALID")
        if not isinstance(requirement, str) or not requirement.strip():
            raise ValueError("EDGE_REQUIREMENT_REQUIRED")
        if outcome not in {"VERIFIED", "BLOCKED", "UNKNOWN"}:
            raise ValueError("EDGE_OUTCOME_INVALID")
        if (parent_id, child_id, requirement) not in self.edges and len(self.edges) >= MAX_GRAPH_EDGES:
            raise ValueError("GRAPH_EDGE_BOUND_EXCEEDED")
        if self.nodes[parent_id]["node_id"] != parent_hash:
            raise ValueError("PARENT_HASH_MISMATCH")
        key = (parent_id, child_id, requirement)
        edge = {"parent_id": parent_id, "parent_hash": parent_hash,
                "child_id": child_id, "requirement": requirement,
                "outcome": outcome, "reason": reason}
        if key in self.edges and self.edges[key] != edge:
            raise ValueError("EDGE_CONFLICT")
        self.edges[key] = edge
        # Refuse the edge if it would close a cycle.
        try:
            self.topological_order()
        except ValueError:
            del self.edges[key]
            raise

    def topological_order(self) -> list[str]:
        outgoing: dict[str, list[str]] = defaultdict(list)
        indegree = {node_id: 0 for node_id in self.nodes}
        for parent, child, _ in self.edges:
            outgoing[parent].append(child)
            indegree[child] += 1
        ready = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
        order: list[str] = []
        while ready:
            node_id = ready.popleft()
            order.append(node_id)
            for child in sorted(outgoing[node_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(order) != len(self.nodes):
            raise ValueError("DEPENDENCY_CYCLE")
        return order

    def verify(self, *, decision_epoch: float | None = None) -> dict[str, Any]:
        errors: list[dict[str, str]] = []
        if decision_epoch is not None:
            try:
                if not math.isfinite(float(decision_epoch)):
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                errors.append({"code": "INVALID_DECISION_EPOCH", "id": "graph"})
        conflicts = {key: sorted(ids) for key, ids in self.logical_keys.items() if len(ids) > 1}
        for logical_key in sorted(conflicts):
            errors.append({"code": "LOGICAL_KEY_CONFLICT", "id": logical_key})
        for node_id, node in sorted(self.nodes.items()):
            if node.get("schema_version") != SCHEMA_VERSION:
                errors.append({"code": "UNSUPPORTED_NODE_SCHEMA", "id": node_id})
            if content_hash({k: v for k, v in node.items() if k != "node_id"}) != node_id:
                errors.append({"code": "NODE_HASH_MISMATCH", "id": node_id})
            available = node.get("available_epoch")
            if decision_epoch is not None and available is not None and float(available) > decision_epoch:
                errors.append({"code": "FUTURE_INFORMATION", "id": node_id})
        for key, edge in sorted(self.edges.items()):
            parent_id, child_id, _ = key
            if parent_id not in self.nodes or child_id not in self.nodes:
                errors.append({"code": "UNRESOLVED_ANCESTOR", "id": parent_id + "->" + child_id})
            elif edge.get("parent_hash") != content_hash({k: v for k, v in self.nodes[parent_id].items() if k != "node_id"}):
                errors.append({"code": "PARENT_HASH_MISMATCH", "id": parent_id})
            if edge.get("outcome") != "VERIFIED":
                errors.append({"code": "DEPENDENCY_NOT_VERIFIED", "id": parent_id + "->" + child_id})
        try:
            order = self.topological_order()
        except ValueError as exc:
            errors.append({"code": str(exc), "id": "graph"})
            order = []
        return {"schema_version": SCHEMA_VERSION, "node_count": len(self.nodes),
                "edge_count": len(self.edges), "conflicts": conflicts,
                "topological_order": order, "errors": errors,
                "verdict": "PASS" if not errors else "BLOCKED",
                **AUTHORITY}

    def publish(self, directory: str | Path, *, session_identity: Mapping[str, Any]) -> Path:
        report = self.verify()
        if report["verdict"] != "PASS":
            raise ValueError("GRAPH_NOT_PUBLISHABLE")
        session = dict(session_identity)
        if not all(session.get(key) for key in ("trading_date", "venue", "calendar_id", "calendar_version")):
            raise ValueError("MANIFEST_SESSION_IDENTITY_REQUIRED")
        graph_hash = content_hash({"session_identity": session, "nodes": sorted(self.nodes), "edges": [self.edges[k] for k in sorted(self.edges)]})
        payload = {"schema_version": SCHEMA_VERSION,
                   "session_identity": session,
                   "nodes": [self.nodes[node_id] for node_id in sorted(self.nodes)],
                   "edges": [self.edges[key] for key in sorted(self.edges)],
                   "graph_sha256": graph_hash,
                   **AUTHORITY}
        if len(canonical_bytes(payload)) > MAX_MANIFEST_BYTES:
            raise ValueError("MANIFEST_SIZE_BOUND_EXCEEDED")
        destination = Path(directory) / f"heritage-{payload['graph_sha256']}.json"
        _atomic_publish(destination, payload)
        return destination


def assemble_t1_heritage_graph(*, session_identity: Mapping[str, Any],
                               calendar_node: Mapping[str, Any],
                               source_nodes: list[Mapping[str, Any]],
                               prerequisite_nodes: list[Mapping[str, Any]],
                               required_fields: Mapping[str, Mapping[str, str]],
                               target_instruments: Mapping[str, Mapping[str, Any]],
                               decision_epoch: float) -> HeritageGraph:
    """Assemble a fail-closed T-1 dependency graph from verified evidence.

    This API wires caller-verified evidence and exact contracts only. It does
    not discover a calendar, verify upstream source files, or derive values.
    """
    try:
        epoch = float(decision_epoch)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_DECISION_EPOCH") from exc
    if not math.isfinite(epoch):
        raise ValueError("INVALID_DECISION_EPOCH")
    if not isinstance(session_identity, Mapping) or not all(
            session_identity.get(key) for key in
            ("trading_date", "venue", "calendar_id", "calendar_version")):
        raise ValueError("MANIFEST_SESSION_IDENTITY_REQUIRED")
    try:
        target_day = date.fromisoformat(str(session_identity["trading_date"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_TARGET_SESSION_DATE") from exc
    if not isinstance(required_fields, Mapping) or not required_fields:
        raise ValueError("REQUIRED_T1_FIELDS_REQUIRED")
    if not isinstance(target_instruments, Mapping):
        raise ValueError("TARGET_INSTRUMENTS_INVALID")
    if set(required_fields) != set(target_instruments):
        raise ValueError("TARGET_STRATEGY_INSTRUMENT_SET_MISMATCH")
    if any(not isinstance(value, Mapping) or not value
           for value in target_instruments.values()):
        raise ValueError("TARGET_INSTRUMENTS_INVALID")
    if not isinstance(calendar_node, Mapping):
        raise ValueError("VERIFIED_CALENDAR_PREDECESSOR_REQUIRED")
    calendar = dict(calendar_node)
    calendar_payload = calendar.get("payload")
    if (calendar.get("status") != "VERIFIED" or
            not isinstance(calendar_payload, Mapping) or
            calendar_payload.get("record_type") != "calendar_predecessor" or
            calendar_payload.get("verified") is not True or
            calendar_payload.get("eligible") is not True or
            calendar_payload.get("target_session") != dict(session_identity) or
            calendar.get("session") != dict(session_identity) or
            calendar.get("instrument") != {"calendar": session_identity["calendar_id"]} or
            calendar_payload.get("calendar_id") != session_identity["calendar_id"] or
            calendar_payload.get("calendar_version") != session_identity["calendar_version"]):
        raise ValueError("VERIFIED_CALENDAR_PREDECESSOR_REQUIRED")
    predecessor = calendar_payload.get("predecessor_session")
    if (not isinstance(predecessor, Mapping) or
            predecessor.get("venue") != session_identity["venue"] or
            predecessor.get("calendar_id") != session_identity["calendar_id"] or
            predecessor.get("calendar_version") != session_identity["calendar_version"]):
        raise ValueError("CALENDAR_PREDECESSOR_IDENTITY_MISMATCH")
    try:
        prior_day = date.fromisoformat(str(predecessor.get("trading_date")))
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_PREDECESSOR_SESSION_DATE") from exc
    if prior_day >= target_day:
        raise ValueError("CALENDAR_PREDECESSOR_NOT_BEFORE_TARGET")

    if not isinstance(source_nodes, list) or not isinstance(prerequisite_nodes, list):
        raise ValueError("T1_NODES_MUST_BE_LISTS")
    sources_by_id: dict[str, dict[str, Any]] = {}
    for raw in source_nodes:
        if not isinstance(raw, Mapping):
            raise ValueError("SOURCE_NODE_INVALID")
        node = dict(raw)
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or node_id in sources_by_id:
            raise ValueError("DUPLICATE_OR_INVALID_SOURCE_NODE")
        sources_by_id[node_id] = node

    expected: dict[tuple[str, str], str] = {}
    for strategy_id, fields in required_fields.items():
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError("REQUIRED_T1_FIELDS_INVALID")
        for field, contract_id in fields.items():
            if not all(isinstance(value, str) and value.strip()
                       for value in (strategy_id, field, contract_id)):
                raise ValueError("REQUIRED_T1_FIELDS_INVALID")
            expected[(strategy_id, field)] = contract_id
    observed: dict[tuple[str, str], dict[str, Any]] = {}
    used_source_ids: set[str] = set()
    for raw in prerequisite_nodes:
        if not isinstance(raw, Mapping):
            raise ValueError("PREREQUISITE_NODE_INVALID")
        node = dict(raw)
        payload = node.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("PREREQUISITE_PAYLOAD_INVALID")
        key = (payload.get("strategy_id"), payload.get("field"))
        if key not in expected:
            raise ValueError("UNEXPECTED_T1_PREREQUISITE_FIELD")
        if key in observed:
            raise ValueError("DUPLICATE_T1_PREREQUISITE_FIELD")
        contract_id = expected[key]
        source_id = payload.get("content_sha256")
        source = sources_by_id.get(source_id)
        instrument = target_instruments[key[0]]
        if (node.get("status") != "VERIFIED" or
                payload.get("verification_status") != "VERIFIED" or
                payload.get("target_session") != dict(session_identity) or
                node.get("session") != dict(session_identity) or
                payload.get("instrument") != dict(instrument) or
                node.get("instrument") != dict(instrument) or
                payload.get("contract_id") != contract_id or
                node.get("contract_id") != contract_id):
            raise ValueError("PREREQUISITE_IDENTITY_OR_CONTRACT_MISMATCH")
        if source is None:
            raise ValueError("EXACT_SOURCE_ANCESTOR_REQUIRED")
        if source_id in used_source_ids:
            raise ValueError("SOURCE_ANCESTOR_REUSED")
        source_session = source.get("session")
        if not isinstance(source_session, Mapping) or not isinstance(source.get("instrument"), Mapping):
            raise ValueError("SOURCE_ANCESTOR_IDENTITY_MISMATCH")
        if (source.get("status") != "VERIFIED" or
                source_session.get("trading_date") != prior_day.isoformat() or
                source_session.get("venue") != session_identity["venue"] or
                source_session.get("calendar_id") != session_identity["calendar_id"] or
                source_session.get("calendar_version") != session_identity["calendar_version"] or
                source.get("instrument") != dict(instrument) or
                payload.get("source_session") != dict(predecessor) or
                payload.get("source_contract_id") != source.get("contract_id")):
            raise ValueError("SOURCE_ANCESTOR_IDENTITY_MISMATCH")
        for evidence in (node, source):
            available = evidence.get("available_epoch")
            if (available is None or not isinstance(available, (int, float)) or
                    not math.isfinite(float(available)) or float(available) > epoch):
                raise ValueError("T1_EVIDENCE_NOT_AVAILABLE_AT_DECISION")
        observed[key] = node
        used_source_ids.add(source_id)
    if set(observed) != set(expected):
        raise ValueError("MISSING_T1_PREREQUISITE_FIELD")
    if set(sources_by_id) != used_source_ids:
        raise ValueError("UNRESOLVED_OR_UNUSED_SOURCE_NODE")

    graph = HeritageGraph()
    calendar_id = graph.add_node(calendar)
    for node in sources_by_id.values():
        graph.add_node(node)
    for key, node in observed.items():
        node_id = graph.add_node(node)
        source_id = node["payload"]["content_sha256"]
        graph.add_edge(parent_id=source_id, child_id=node_id,
                       requirement=expected[key], parent_hash=source_id)
        graph.add_edge(parent_id=calendar_id, child_id=node_id,
                       requirement="PREVIOUS_ELIGIBLE_SESSION", parent_hash=calendar_id)
    report = graph.verify(decision_epoch=epoch)
    if report.get("verdict") != "PASS":
        raise ValueError("ASSEMBLED_T1_GRAPH_VERIFICATION_FAILED")
    return graph


class SessionHeritageIndex:
    """Bounded, explicit index of immutable run manifests for one session.

    The index is updated with an exclusive lock and atomic replace. It is a
    lookup aid only: every returned manifest is reopened and hash-verified.
    No globbing or external-root discovery is performed.
    """

    def __init__(self, approved_root: str | Path, *, session: Mapping[str, Any],
                 max_entries: int = 512, lock_timeout_seconds: float = 2.0):
        self.root = Path(approved_root).resolve()
        if not isinstance(session, Mapping) or not session:
            raise ValueError("SESSION_IDENTITY_REQUIRED")
        if max_entries < 1 or max_entries > 10000:
            raise ValueError("INVALID_INDEX_BOUND")
        self.session = dict(session)
        self.max_entries = max_entries
        self.lock_timeout_seconds = lock_timeout_seconds
        self.index_path = self.root / "heritage-index-v1.json"
        self.lock_path = self.root / ".heritage-index-v1.lock"

    def _load(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema_version": 1, "session": self.session, "entries": []}
        if self.index_path.stat().st_size > MAX_INDEX_BYTES:
            raise ValueError("INDEX_SIZE_BOUND_EXCEEDED")
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or payload.get("session") != self.session:
            raise ValueError("INDEX_SESSION_OR_SCHEMA_MISMATCH")
        entries = payload.get("entries")
        if not isinstance(entries, list) or len(entries) > self.max_entries:
            raise ValueError("INDEX_ENTRY_BOUND_EXCEEDED")
        return payload

    def _lock(self) -> int:
        deadline = time.monotonic() + max(0.0, self.lock_timeout_seconds)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise TimeoutError("HERITAGE_INDEX_LOCK_TIMEOUT")
                time.sleep(0.01)

    def register(self, manifest_path: str | Path, *, run_id: str,
                 session: Mapping[str, Any]) -> dict[str, Any]:
        """Register a verified manifest; conflicting run identities are blocked."""
        if dict(session) != self.session:
            raise ValueError("WRONG_TRADING_SESSION")
        path = Path(manifest_path).resolve()
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError("MANIFEST_OUTSIDE_APPROVED_ROOT") from exc
        if not run_id or path.name.startswith(".") or path.name.endswith(".tmp"):
            raise ValueError("INVALID_RUN_MANIFEST_REFERENCE")
        fd = self._lock()
        try:
            verified = verify_manifest(path)
            if verified.get("verdict") != "PASS":
                raise ValueError("MANIFEST_NOT_VERIFIED")
            manifest_payload = json.loads(path.read_text(encoding="utf-8"))
            if manifest_payload.get("session_identity") != self.session:
                raise ValueError("MANIFEST_SESSION_IDENTITY_MISMATCH")
            manifest_hash = str(verified["manifest_sha256"])
            payload = self._load()
            if self.index_path.exists():
                expected_hash = content_hash({"schema_version": 1,
                    "session": self.session, "entries": payload["entries"]})
                if payload.get("index_sha256") != expected_hash:
                    raise ValueError("INDEX_HASH_MISMATCH")
            for existing in payload["entries"]:
                if (not isinstance(existing, Mapping) or not existing.get("run_id")
                        or not isinstance(existing.get("manifest"), str)
                        or not _valid_hash(existing.get("manifest_sha256"))
                        or existing.get("session") != self.session):
                    raise ValueError("INDEX_ENTRY_INVALID")
            entry = {"run_id": run_id, "manifest": relative,
                     "manifest_sha256": manifest_hash, "session": self.session}
            by_run = {row["run_id"]: row for row in payload["entries"]}
            prior = by_run.get(run_id)
            if prior is not None and prior != entry:
                raise ValueError("RUN_ID_MANIFEST_CONFLICT")
            if prior is None:
                if len(payload["entries"]) >= self.max_entries:
                    raise ValueError("INDEX_ENTRY_BOUND_EXCEEDED")
                payload["entries"].append(entry)
                payload["entries"].sort(key=lambda row: (row["run_id"], row["manifest_sha256"]))
                payload["index_sha256"] = content_hash({"schema_version": 1,
                    "session": self.session, "entries": payload["entries"]})
                _atomic_publish(self.index_path, payload) if not self.index_path.exists() else self._replace_index(payload)
            return entry
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _replace_index(self, payload: Mapping[str, Any]) -> None:
        """Atomically replace only the mutable lookup index while holding lock."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".heritage-index-v1.", suffix=".tmp", dir=str(self.root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(dict(payload), handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.index_path)
            try:
                dir_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def resolve(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        """Resolve only explicitly indexed runs, rechecking bytes and graph closure."""
        payload = self._load()
        expected_index_hash = content_hash({"schema_version": 1,
            "session": self.session, "entries": payload["entries"]})
        if payload.get("index_sha256") != expected_index_hash:
            raise ValueError("INDEX_HASH_MISMATCH")
        matches = [row for row in payload["entries"] if run_id is None or row.get("run_id") == run_id]
        resolved: list[dict[str, Any]] = []
        for entry in matches:
            path = (self.root / entry["manifest"]).resolve()
            try:
                path.relative_to(self.root)
            except ValueError as exc:
                raise ValueError("INDEX_PATH_ESCAPES_APPROVED_ROOT") from exc
            verification = verify_manifest(path)
            if (verification.get("verdict") != "PASS" or
                    verification.get("manifest_sha256") != entry.get("manifest_sha256") or
                    entry.get("session") != self.session):
                raise ValueError("INDEXED_MANIFEST_CHANGED_OR_UNVERIFIED")
            resolved.append({**entry, "path": str(path), "verification": verification})
        return resolved


def publish_verified_heritage_manifest(*, graph: HeritageGraph,
                                      approved_root: str | Path,
                                      session_identity: Mapping[str, Any],
                                      run_id: str,
                                      decision_epoch: float) -> dict[str, Any]:
    """Publish, independently verify, then index one immutable session graph.

    Caller-supplied evidence remains subject to the graph's source/contract
    checks. A failed independent check is never indexed; its content-addressed
    file, if already atomically published, remains an untrusted orphan for
    audit and cannot be resolved through the index.
    """
    if not isinstance(graph, HeritageGraph):
        return {"status": "BLOCKED", "reason": "HERITAGE_GRAPH_REQUIRED", **AUTHORITY}
    if not isinstance(run_id, str) or not run_id.strip() or not isinstance(session_identity, Mapping):
        return {"status": "BLOCKED", "reason": "RUN_AND_SESSION_IDENTITY_REQUIRED", **AUTHORITY}
    try:
        if not math.isfinite(float(decision_epoch)):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        return {"status": "BLOCKED", "reason": "INVALID_DECISION_EPOCH", **AUTHORITY}
    try:
        root = Path(approved_root).resolve()
        session = dict(session_identity)
        preflight = graph.verify(decision_epoch=decision_epoch)
        if preflight.get("verdict") != "PASS":
            return {"status": "BLOCKED", "reason": "GRAPH_PREFLIGHT_FAILED",
                    "verification": preflight, **AUTHORITY}
        path = graph.publish(root, session_identity=session)
        from core.market_heritage_verifier import verify_market_heritage_manifest
        independent = verify_market_heritage_manifest(path, decision_epoch=decision_epoch)
        if independent.get("verdict") != "PASS":
            return {"status": "BLOCKED", "reason": "INDEPENDENT_VERIFICATION_FAILED",
                    "manifest_path": str(path),
                    "manifest_sha256": independent.get("manifest_sha256"),
                    "independent_verification": independent, **AUTHORITY}
        entry = SessionHeritageIndex(root, session=session).register(
            path, run_id=run_id, session=session)
        return {"status": "PUBLISHED_VERIFIED", "reason": "INDEPENDENTLY_VERIFIED_AND_INDEXED",
                "manifest_path": str(path), "manifest_sha256": independent.get("manifest_sha256"),
                "graph_verification": preflight,
                "independent_verification": independent,
                "index_entry": entry, **AUTHORITY}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"status": "BLOCKED", "reason": str(exc) or "HERITAGE_PUBLICATION_FAILED", **AUTHORITY}


_LEGACY_FIXED_NAMES = {
    "native_pulse_stream.jsonl", "strategy_observations.jsonl",
    "candidate_pool.jsonl", "executable_pool.jsonl",
    "candidate_decisions.jsonl", "trade_truth_stream.jsonl",
    "feed_runtime_latest.json", "presession_manifest.json",
    # Immutable provenance and observer source references needed to audit
    # pulse-to-feed lineage. They are indexed as legacy-unverified; the
    # indexer never interprets these references as source-price authority.
    "meg_selected_tick_events.jsonl", "meg_request_events.jsonl",
    "meg_accepted_cycles.jsonl", "meg_persisted_cycles.jsonl",
    "meg_live_source_exports.jsonl", "captured_metadata.jsonl",
}
_LEGACY_AUTHORITY = {**AUTHORITY, "append": False}


def index_legacy_session_runs(*, sessions_root: str | Path,
                               legacy_session_root: str | Path,
                               destination_root: str | Path,
                               session_identity: Mapping[str, Any],
                               max_runs: int = MAX_LEGACY_RUNS,
                               max_files: int = MAX_LEGACY_FILES,
                               max_file_bytes: int = MAX_LEGACY_FILE_BYTES,
                               max_total_bytes: int = MAX_LEGACY_TOTAL_BYTES) -> dict[str, Any]:
    """Inventory a bounded legacy session tree without upgrading its authority.

    Only explicitly named top-level artifacts are hashed. All records remain
    LEGACY_UNVERIFIED because byte identity alone cannot prove capture-time
    provenance, schema validity, event timing, or a historical seal. The
    content-addressed inventory is written outside the protected sessions tree.
    """
    if not isinstance(session_identity, Mapping) or not session_identity:
        return {"status": "BLOCKED", "reason": "SESSION_IDENTITY_REQUIRED", **_LEGACY_AUTHORITY}
    try:
        trading_date = date.fromisoformat(str(session_identity["trading_date"]))
    except (KeyError, TypeError, ValueError):
        return {"status": "BLOCKED", "reason": "INVALID_TRADING_DATE", **_LEGACY_AUTHORITY}
    if (max_runs < 1 or max_runs > MAX_LEGACY_RUNS or max_files < 1
            or max_files > MAX_LEGACY_FILES or max_file_bytes < 1
            or max_file_bytes > MAX_LEGACY_FILE_BYTES or max_total_bytes < 1
            or max_total_bytes > MAX_LEGACY_TOTAL_BYTES):
        return {"status": "BLOCKED", "reason": "LEGACY_INDEX_BOUND_INVALID", **_LEGACY_AUTHORITY}

    sessions = Path(sessions_root).resolve()
    session_root = Path(legacy_session_root).resolve()
    output_root = Path(destination_root).resolve()
    try:
        session_root.relative_to(sessions)
    except ValueError:
        return {"status": "BLOCKED", "reason": "LEGACY_ROOT_OUTSIDE_APPROVED_SESSIONS", **_LEGACY_AUTHORITY}
    if (session_root.name != trading_date.isoformat()
            or session_root.parent.name != f"session_{trading_date.isoformat()}"):
        return {"status": "BLOCKED", "reason": "LEGACY_SESSION_PATH_MISMATCH", **_LEGACY_AUTHORITY}
    try:
        output_root.relative_to(sessions)
        return {"status": "BLOCKED", "reason": "INDEX_DESTINATION_INSIDE_PROTECTED_SESSIONS", **_LEGACY_AUTHORITY}
    except ValueError:
        pass

    try:
        run_dirs = []
        with os.scandir(session_root) as scanner:
            for entry in scanner:
                if entry.is_dir(follow_symlinks=False):
                    run_dirs.append(entry.name)
                    if len(run_dirs) > max_runs:
                        return {"status": "BLOCKED", "reason": "LEGACY_RUN_BOUND_EXCEEDED",
                                "run_count_lower_bound": len(run_dirs), **_LEGACY_AUTHORITY}
        run_dirs.sort()

        inventory: list[dict[str, Any]] = []
        total_bytes = 0
        file_count = 0
        for run_id in run_dirs:
            run_path = session_root / run_id
            run_entry = {"run_id": run_id, "status": "LEGACY_UNVERIFIED", "files": []}
            try:
                run_path.resolve().relative_to(session_root)
            except ValueError:
                run_entry["reason"] = "RUN_PATH_ESCAPES_SESSION_ROOT"
                inventory.append(run_entry)
                continue
            try:
                run_fd = os.open(run_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0))
            except OSError:
                run_entry["reason"] = "RUN_DIRECTORY_CHANGED_OR_UNSAFE"
                inventory.append(run_entry)
                continue
            with os.scandir(run_fd) as scanner:
                files = []
                for item in scanner:
                    if not item.is_file(follow_symlinks=False):
                        continue
                    if (item.name in _LEGACY_FIXED_NAMES
                            or (item.name.startswith("cas_short_horizon_primitives_")
                                and item.name.endswith(".json"))):
                        files.append(item.name)
                        if len(files) > max_files:
                            run_entry["reason"] = "LEGACY_FILE_COUNT_BOUND_EXCEEDED"
                            break
            for filename in sorted(files):
                if file_count >= max_files:
                    run_entry["reason"] = "LEGACY_FILE_COUNT_BOUND_EXCEEDED"
                    break
                try:
                    file_fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=run_fd)
                except OSError:
                    run_entry["files"].append({"path": f"{run_id}/{filename}",
                        "status": "LEGACY_UNVERIFIED", "reason": "FILE_CHANGED_OR_UNSAFE"})
                    continue
                file_count += 1
                before = os.fstat(file_fd)
                if before.st_size > max_file_bytes:
                    run_entry["files"].append({"path": f"{run_id}/{filename}",
                        "status": "LEGACY_UNVERIFIED", "reason": "FILE_SIZE_BOUND_EXCEEDED",
                        "byte_size": before.st_size})
                    os.close(file_fd)
                    continue
                if total_bytes + before.st_size > max_total_bytes:
                    run_entry["reason"] = "LEGACY_TOTAL_SIZE_BOUND_EXCEEDED"
                    os.close(file_fd)
                    break
                digest = hashlib.sha256()
                line_count = 0
                try:
                    with os.fdopen(file_fd, "rb", closefd=True) as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                            if filename.endswith(".jsonl"):
                                line_count += chunk.count(b"\n")
                        after = os.fstat(handle.fileno())
                except OSError:
                    run_entry["files"].append({"path": f"{run_id}/{filename}",
                        "status": "LEGACY_UNVERIFIED", "reason": "FILE_READ_FAILED"})
                    continue
                changed = (before.st_size, before.st_mtime_ns, before.st_ino) != (
                    after.st_size, after.st_mtime_ns, after.st_ino)
                total_bytes += before.st_size
                file_record = {"path": f"{run_id}/{filename}",
                    "byte_size": before.st_size,
                    "sha256": digest.hexdigest() if not changed else None,
                    "record_count": line_count if filename.endswith(".jsonl") else None,
                    "status": "LEGACY_UNVERIFIED",
                    "reason": "SOURCE_CHANGED_DURING_INDEX" if changed else "NO_CAPTURE_TIME_SEAL"}
                run_entry["files"].append(file_record)
            os.close(run_fd)
            inventory.append(run_entry)

        body = {"schema_version": 1, "status": "INVENTORIED_UNVERIFIED",
            "session_identity": dict(session_identity),
            "sessions_root_identity": str(sessions),
            "session_relative_root": session_root.relative_to(sessions).as_posix(),
            "run_count": len(run_dirs), "file_count": file_count,
            "hashed_byte_count": total_bytes, "runs": inventory,
            "authority": {**AUTHORITY, "append": False}}
        index_sha = content_hash(body)
        output_root.mkdir(parents=True, exist_ok=True)
        index_path = output_root / f"legacy-inventory-{index_sha}.json"
        _atomic_publish(index_path, {**body, "inventory_sha256": index_sha})
        return {"status": "INVENTORIED_UNVERIFIED", "inventory_path": str(index_path),
                "inventory_sha256": index_sha, "run_count": len(run_dirs),
                "file_count": file_count, "hashed_byte_count": total_bytes,
                "legacy_authority": "LEGACY_UNVERIFIED", **_LEGACY_AUTHORITY}
    except (OSError, ValueError, TypeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc) or "LEGACY_INDEX_IO_FAILURE", **_LEGACY_AUTHORITY}


def publish_same_session_cas_manifest(*, heritage_root: str | Path,
                                      session_identity: Mapping[str, Any],
                                      run_id: str, source_sha: str,
                                      underlying_token: int,
                                      primitives: Mapping[str, Mapping[str, Any]],
                                      coverage_report: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Publish verified CAS captures and optional observed run coverage."""
    from core.cas_primitive_producer import SPEC_SHA, verify_primitive

    if (not run_id or not isinstance(source_sha, str)
            or len(source_sha) not in {40, 64}
            or any(char not in "0123456789abcdef" for char in source_sha)):
        return {"status": "BLOCKED", "reason": "RUN_OR_SOURCE_IDENTITY_INVALID", **AUTHORITY}
    graph = HeritageGraph()
    accepted = 0
    coverage_published = False
    try:
        for name, row in sorted(primitives.items()):
            if name not in {"0915", "1000"} or not isinstance(row, Mapping):
                continue
            valid, reason = verify_primitive(dict(row), session_id=run_id,
                source_sha=source_sha, underlying_token=underlying_token)
            if not valid:
                continue
            node = make_node(
                logical_key=f"cas:{session_identity['trading_date']}:{name}",
                payload={"record_type": "cas_primitive", "run_id": run_id,
                         "primitive_name": name, "primitive": dict(row)},
                source_ref=f"cas://{run_id}/{name}",
                source_sha256=str(row["source_event_sha256"]),
                session=session_identity,
                instrument={"symbol": "NIFTY", "token": underlying_token},
                contract_id=SPEC_SHA,
                source_event_epoch=float(row["source_timestamp_epoch"]),
                receive_epoch=float(row["receive_timestamp_epoch"]),
                available_epoch=float(row["timestamp_epoch"]),
                status="VERIFIED", coverage={"single_event": True, "gap_free_claim": False})
            graph.add_node(node)
            accepted += 1
        if coverage_report is not None:
            report = dict(coverage_report)
            if (report.get("run_id") != run_id
                    or report.get("session_identity") != dict(session_identity)
                    or not isinstance(report.get("run_started_epoch"), (int, float))
                    or not isinstance(report.get("run_ended_epoch"), (int, float))
                    or report.get("read_only") is not True
                    or report.get("broker_api_called") is not False
                    or report.get("allowed_for_live_execution") is not False):
                return {"status": "BLOCKED", "reason": "RUN_COVERAGE_IDENTITY_OR_AUTHORITY_INVALID", **AUTHORITY}
            coverage_hash = content_hash(report)
            graph.add_node(make_node(
                logical_key=f"coverage:{session_identity['trading_date']}:{run_id}",
                payload={"record_type": "run_coverage", "run_id": run_id,
                    "coverage_report": report},
                source_ref=f"coverage://{run_id}/read-only-tick-callbacks",
                source_sha256=coverage_hash, session=session_identity,
                instrument={"scope": "final_union_tokens",
                    "token_count": report.get("intended_token_count", 0)},
                contract_id="READ_ONLY_TICK_COVERAGE_V1",
                source_event_epoch=float(report["run_started_epoch"]),
                receive_epoch=float(report["run_ended_epoch"]),
                available_epoch=float(report["run_ended_epoch"]),
                status="OBSERVED", coverage={"per_token": True,
                    "scheduler_cadence_known": False,
                    "downstream_correlation_known": False}))
            coverage_published = True
        if accepted == 0 and not coverage_published:
            return {"status": "BLOCKED", "reason": "NO_VERIFIED_CAS_OR_COVERAGE_RECORDS", **AUTHORITY}
        path = graph.publish(heritage_root, session_identity=session_identity)
        index = SessionHeritageIndex(heritage_root, session=session_identity)
        entry = index.register(path, run_id=run_id, session=session_identity)
        return {"status": "PUBLISHED", "manifest_path": str(path),
                "manifest_sha256": entry["manifest_sha256"],
                "primitive_count": accepted,
                "coverage_published": coverage_published, **AUTHORITY}
    except (OSError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        return {"status": "BLOCKED", "reason": str(exc) or "CAS_HERITAGE_PUBLICATION_FAILED", **AUTHORITY}


def load_same_session_cas_references(*, heritage_root: str | Path,
                                     session_identity: Mapping[str, Any],
                                     current_run_id: str,
                                     source_sha: str,
                                     underlying_token: int) -> dict[str, Any]:
    """Resolve only independently reverified prior-run captures for this date."""
    from core.cas_primitive_producer import SPEC_SHA, verify_primitive
    from core.market_heritage_verifier import verify_market_heritage_manifest

    empty = {"primitives": {}, "coverage": [], "blockers": [], "status": "EMPTY", **AUTHORITY}
    root = Path(heritage_root).resolve()
    index_path = root / "heritage-index-v1.json"
    if not index_path.is_file():
        return empty
    try:
        index = SessionHeritageIndex(root, session=session_identity)
        entries = index.resolve()
        candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
        coverage_reports: list[dict[str, Any]] = []
        blockers: list[dict[str, str]] = []
        for entry in entries:
            if entry["run_id"] == current_run_id:
                continue
            path = Path(entry["path"])
            independent = verify_market_heritage_manifest(path, decision_epoch=time.time())
            if independent.get("verdict") != "PASS":
                blockers.append({"run_id": entry["run_id"], "reason": "INDEPENDENT_MANIFEST_VERIFICATION_FAILED"})
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            for node in payload.get("nodes", []):
                body = node.get("payload", {})
                if body.get("record_type") == "run_coverage":
                    report = body.get("coverage_report")
                    if (node.get("contract_id") == "READ_ONLY_TICK_COVERAGE_V1"
                            and body.get("run_id") == entry["run_id"]
                            and isinstance(report, Mapping)
                            and report.get("run_id") == entry["run_id"]
                            and report.get("session_identity") == dict(session_identity)
                            and content_hash(report) == node.get("source_sha256")
                            and isinstance(report.get("run_started_epoch"), (int, float))
                            and isinstance(report.get("run_ended_epoch"), (int, float))
                            and float(report["run_ended_epoch"]) >= float(report["run_started_epoch"])
                            and report.get("read_only") is True
                            and report.get("broker_api_called") is False
                            and report.get("allowed_for_live_execution") is False):
                        coverage_reports.append({"source_run_id": entry["run_id"],
                            "source_manifest_sha256": entry["manifest_sha256"],
                            "coverage_report_sha256": content_hash(report),
                            "status": "VERIFIED_SAME_SESSION_RUN_COVERAGE",
                            **dict(report)})
                    else:
                        blockers.append({"run_id": entry["run_id"],
                            "reason": "RUN_COVERAGE_IDENTITY_OR_AUTHORITY_INVALID"})
                    continue
                if body.get("record_type") != "cas_primitive":
                    continue
                name = body.get("primitive_name")
                row = body.get("primitive")
                if name not in {"0915", "1000"} or not isinstance(row, dict):
                    blockers.append({"run_id": entry["run_id"], "reason": "INVALID_CAS_NODE_SHAPE"})
                    continue
                valid, reason = verify_primitive(row, session_id=entry["run_id"],
                    source_sha=source_sha, underlying_token=underlying_token)
                if (not valid or row.get("primitive_name") != name
                        or node.get("contract_id") != SPEC_SHA
                        or float(row.get("source_timestamp_epoch", float("inf"))) > time.time()
                        or row.get("capture_status") != "CAPTURED"):
                    blockers.append({"run_id": entry["run_id"], "reason": "CAS_SOURCE_NOT_ADMISSIBLE:" + reason})
                    continue
                source_day = datetime.fromtimestamp(float(row["source_timestamp_epoch"]), tz=__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date().isoformat()
                if source_day != session_identity.get("trading_date"):
                    blockers.append({"run_id": entry["run_id"], "reason": "CROSS_SESSION_CAS_REFERENCE_REJECTED"})
                    continue
                candidates[name].append({
                    "primitive": row,
                    "lineage": {"lineage_status": "INHERITED_VERIFIED",
                        "original_capture_status": row["capture_status"],
                        "source_run_id": entry["run_id"],
                        "source_manifest_sha256": entry["manifest_sha256"],
                        "source_node_id": node["node_id"],
                        "session_identity": dict(session_identity),
                        **AUTHORITY},
                })
        references: dict[str, Any] = {}
        for name, rows in candidates.items():
            identities = {(item["primitive"].get("source_event_id"),
                           item["primitive"].get("source_event_sha256"),
                           item["primitive"].get("price")) for item in rows}
            if len(identities) != 1:
                blockers.append({"primitive_name": name, "reason": "CONFLICTING_SAME_SESSION_CAS_SOURCES"})
                continue
            references[name] = sorted(rows, key=lambda item: (
                item["lineage"]["source_run_id"], item["lineage"]["source_manifest_sha256"]))[0]
        status = ("VERIFIED" if references and not blockers else
            "PARTIAL" if references or coverage_reports else
            "BLOCKED" if blockers else "EMPTY")
        return {"status": status, "primitives": references, "coverage": coverage_reports,
                "blockers": blockers, **AUTHORITY}
    except (OSError, ValueError, KeyError, TypeError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "BLOCKED", "primitives": {}, "coverage": [],
                "blockers": [{"reason": str(exc) or "SAME_SESSION_INDEX_INVALID"}], **AUTHORITY}


def resolve_previous_eligible_session(*, target_session: Mapping[str, Any],
                                      eligible_sessions: list[Mapping[str, Any]],
                                      calendar_id: str, calendar_version: str,
                                      venue: str, instrument_id: str) -> dict[str, Any]:
    """Resolve T-1 only from an explicit, versioned eligible-session authority.

    This helper intentionally does not infer sessions from weekdays/holidays.
    The caller must supply the calendar's complete candidate records and exact
    instrument identity. Invalid/ambiguous calendars return typed blockers.
    """
    required = (calendar_id, calendar_version, venue, instrument_id)
    if any(not str(value).strip() for value in required):
        return {"status": "BLOCKED", "reason": "CALENDAR_OR_INSTRUMENT_AUTHORITY_MISSING", **AUTHORITY}
    try:
        target_date = date.fromisoformat(str(target_session["trading_date"]))
        if target_session.get("calendar_id") != calendar_id or target_session.get("calendar_version") != calendar_version:
            raise ValueError("TARGET_CALENDAR_MISMATCH")
        if target_session.get("venue") != venue or target_session.get("instrument_id") != instrument_id:
            raise ValueError("TARGET_INSTRUMENT_OR_VENUE_MISMATCH")
        dates: set[date] = set()
        for row in eligible_sessions:
            if row.get("calendar_id") != calendar_id or row.get("calendar_version") != calendar_version:
                raise ValueError("ANCESTOR_CALENDAR_MISMATCH")
            if row.get("venue") != venue or row.get("instrument_id") != instrument_id:
                raise ValueError("ANCESTOR_INSTRUMENT_OR_VENUE_MISMATCH")
            if row.get("eligible") is not True or row.get("verified") is not True:
                continue
            current = date.fromisoformat(str(row["trading_date"]))
            if current >= target_date:
                continue
            dates.add(current)
        if not dates:
            return {"status": "BLOCKED", "reason": "PREVIOUS_ELIGIBLE_SESSION_NOT_FOUND", **AUTHORITY}
        prior = max(dates)
        matches = [row for row in eligible_sessions if row.get("trading_date") == prior.isoformat()
                   and row.get("eligible") is True and row.get("verified") is True]
        if len(matches) != 1:
            return {"status": "BLOCKED", "reason": "AMBIGUOUS_PREVIOUS_SESSION", "trading_date": prior.isoformat(), **AUTHORITY}
        return {"status": "RESOLVED", "reason": "VERIFIED_CALENDAR_ANCESTOR",
                "trading_date": prior.isoformat(), "calendar_id": calendar_id,
                "calendar_version": calendar_version, "venue": venue,
                "instrument_id": instrument_id, **AUTHORITY}
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "BLOCKED", "reason": str(exc) or "INVALID_SESSION_IDENTITY", **AUTHORITY}


def evaluate_prerequisite_readiness(*, strategy_id: str, required_fields: Mapping[str, str],
                                    verified_fields: Mapping[str, Mapping[str, Any]],
                                    decision_epoch: float,
                                    target_instrument: Mapping[str, Any],
                                    target_session: Mapping[str, Any]) -> dict[str, Any]:
    """Return per-strategy typed readiness; never infers authority from values."""
    blockers: list[dict[str, str]] = []
    accepted: dict[str, dict[str, Any]] = {}
    for field, contract_id in required_fields.items():
        row = verified_fields.get(field)
        if not isinstance(row, Mapping):
            blockers.append({"field": field, "reason": "MISSING"})
            continue
        if row.get("verification_status") != "VERIFIED":
            blockers.append({"field": field, "reason": str(row.get("reason") or "INVALID")})
            continue
        if row.get("contract_id") != contract_id:
            blockers.append({"field": field, "reason": "CONTRACT_MISMATCH"})
            continue
        if dict(row.get("instrument") or {}) != dict(target_instrument):
            blockers.append({"field": field, "reason": "WRONG_INSTRUMENT"})
            continue
        if field.endswith("contract_key"):
            expected_key = target_instrument.get("contract_key")
            if not expected_key or row.get("value") != expected_key:
                blockers.append({"field": field, "reason": "CONTRACT_MISMATCH"})
                continue
        if dict(row.get("target_session") or {}) != dict(target_session):
            blockers.append({"field": field, "reason": "WRONG_SESSION"})
            continue
        try:
            if float(row["available_epoch"]) > decision_epoch:
                blockers.append({"field": field, "reason": "TEMPORALLY_INADMISSIBLE"})
                continue
            if not _valid_hash(row["content_sha256"]):
                blockers.append({"field": field, "reason": "INVALID_CONTENT_HASH"})
                continue
        except (KeyError, TypeError, ValueError):
            blockers.append({"field": field, "reason": "MISSING_ASOF_OR_HASH"})
            continue
        accepted[field] = {"content_sha256": row["content_sha256"],
                           "contract_id": contract_id,
                           "source_session": row.get("source_session")}
    return {"strategy_id": strategy_id,
            "status": "READY" if not blockers else "BLOCKED",
            "accepted_fields": accepted, "blockers": blockers,
            "evaluation_eligible": not blockers,
            "entry_eligible": False,
            **AUTHORITY}


def load_verified_t1_prerequisites(*, manifest_path: str | Path | None,
                                   expected_manifest_sha256: str | None,
                                   approved_root: str | Path,
                                   target_session: Mapping[str, Any],
                                   decision_epoch: float,
                                   required_fields: Mapping[str, Mapping[str, str]],
                                   target_instruments: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Load strategy prerequisites only from an explicitly pinned verified graph.

    The expected artifact hash is supplied by the caller's governed launch plan;
    path discovery, environment fallbacks and unsealed legacy values are refused.
    Each graph node must carry strategy_id, field, contract_id, value, instrument,
    target_session, available_epoch, verification_status and content_sha256 in
    its hash-bound payload. A valid graph hash alone never grants live authority.
    """
    empty = {
        "opening_drive_prev_contract_key": None,
        "opening_drive_prev_close_1529": None,
        "opening_drive_target_expiry": None,
        "overnight_prev_daily_close": None,
        "overnight_prev_sma200": None,
    }
    if not manifest_path or not _valid_hash(expected_manifest_sha256):
        return {**empty, "heritage_verification": {
            "status": "BLOCKED", "reason": "PINNED_HERITAGE_MANIFEST_REQUIRED",
            "manifest_sha256": None, "strategy_readiness": {}, **AUTHORITY}}
    root = Path(approved_root).resolve()
    path = Path(manifest_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return {**empty, "heritage_verification": {
            "status": "BLOCKED", "reason": "MANIFEST_OUTSIDE_APPROVED_ROOT",
            "manifest_sha256": None, "strategy_readiness": {}, **AUTHORITY}}
    try:
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha != expected_manifest_sha256:
            raise ValueError("PINNED_MANIFEST_HASH_MISMATCH")
        verification = verify_manifest(path, decision_epoch=decision_epoch)
        if verification.get("verdict") != "PASS":
            reasons = sorted({row.get("code", "INVALID_MANIFEST") for row in verification.get("errors", [])})
            raise ValueError("MANIFEST_NOT_VERIFIED:" + ",".join(reasons))
        payload = json.loads(path.read_text(encoding="utf-8"))
        session = payload.get("session_identity")
        if not isinstance(session, Mapping) or any(session.get(key) != value for key, value in target_session.items()):
            raise ValueError("TARGET_SESSION_MISMATCH")

        fields: dict[tuple[str, str], dict[str, Any]] = {}
        conflicts: set[tuple[str, str]] = set()
        nodes_by_id = {str(node.get("node_id")): node for node in payload.get("nodes", [])
                       if isinstance(node, Mapping) and node.get("node_id")}
        incoming: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for edge in payload.get("edges", []):
            if isinstance(edge, Mapping):
                incoming[str(edge.get("child_id"))].append(edge)
        for node in payload.get("nodes", []):
            body = node.get("payload") if isinstance(node, Mapping) else None
            if not isinstance(body, Mapping):
                continue
            strategy_id, field = body.get("strategy_id"), body.get("field")
            key = (str(strategy_id), str(field))
            if key[0] not in required_fields or key[1] not in required_fields[key[0]]:
                continue
            parents = incoming.get(str(node.get("node_id")), [])
            valid_parent = False
            valid_calendar_ancestor = False
            source_parents: list[Mapping[str, Any]] = []
            try:
                source_session = body.get("source_session")
                target_date = date.fromisoformat(str(target_session["trading_date"]))
                source_date = date.fromisoformat(str(source_session["trading_date"])) if isinstance(source_session, Mapping) else target_date
                source_parents = [
                    nodes_by_id[str(edge.get("parent_id"))]
                    for edge in parents
                    if edge.get("outcome") == "VERIFIED"
                    and edge.get("requirement") == body.get("contract_id")
                    and node.get("contract_id") == body.get("contract_id")
                    and str(edge.get("parent_id")) in nodes_by_id
                    and nodes_by_id[str(edge.get("parent_id"))].get("status") == "VERIFIED"
                    and nodes_by_id[str(edge.get("parent_id"))].get("session", {}).get("trading_date") == source_date.isoformat()
                    and nodes_by_id[str(edge.get("parent_id"))].get("session", {}).get("venue") == target_session.get("venue")
                    and nodes_by_id[str(edge.get("parent_id"))].get("session", {}).get("calendar_id") == target_session.get("calendar_id")
                    and nodes_by_id[str(edge.get("parent_id"))].get("session", {}).get("calendar_version") == target_session.get("calendar_version")
                    and nodes_by_id[str(edge.get("parent_id"))].get("instrument") == dict(target_instruments.get(strategy_id) or {})
                    and source_date < target_date
                ]
                valid_parent = (len(source_parents) == 1
                    and body.get("content_sha256") == source_parents[0].get("node_id")
                    and body.get("source_contract_id") == source_parents[0].get("contract_id"))
                valid_calendar_ancestor = any(
                    edge.get("outcome") == "VERIFIED"
                    and edge.get("requirement") == "PREVIOUS_ELIGIBLE_SESSION"
                    and str(edge.get("parent_id")) in nodes_by_id
                    and nodes_by_id[str(edge.get("parent_id"))].get("status") == "VERIFIED"
                    and isinstance(nodes_by_id[str(edge.get("parent_id"))].get("payload"), Mapping)
                    and nodes_by_id[str(edge.get("parent_id"))].get("session") == dict(target_session)
                    and nodes_by_id[str(edge.get("parent_id"))]["payload"].get("record_type") == "calendar_predecessor"
                    and nodes_by_id[str(edge.get("parent_id"))]["payload"].get("eligible") is True
                    and nodes_by_id[str(edge.get("parent_id"))]["payload"].get("verified") is True
                    and nodes_by_id[str(edge.get("parent_id"))]["payload"].get("predecessor_session") == dict(source_session or {})
                    and nodes_by_id[str(edge.get("parent_id"))]["payload"].get("target_session") == dict(target_session)
                    and nodes_by_id[str(edge.get("parent_id"))]["payload"].get("calendar_id") == target_session.get("calendar_id")
                    and nodes_by_id[str(edge.get("parent_id"))]["payload"].get("calendar_version") == target_session.get("calendar_version")
                    for edge in parents
                )
            except (KeyError, TypeError, ValueError):
                valid_parent = False
                valid_calendar_ancestor = False
            row = {**dict(body), "verification_status": body.get("verification_status") if valid_parent and valid_calendar_ancestor else "INVALID",
                   "reason": body.get("reason") if valid_parent and valid_calendar_ancestor else (
                       "VERIFIED_ANCESTOR_EDGE_REQUIRED" if not valid_parent else "VERIFIED_CALENDAR_PREDECESSOR_REQUIRED"),
                   "content_sha256": body.get("content_sha256")}
            value = row.get("value")
            if row.get("verification_status") == "VERIFIED":
                if len(source_parents) != 1:
                    row["verification_status"] = "INVALID"
                    row["reason"] = "EXACTLY_ONE_VERIFIED_SOURCE_ANCESTOR_REQUIRED"
                if key[1].endswith(("close_1529", "daily_close", "sma200")):
                    try:
                        numeric = float(value)
                        if not math.isfinite(numeric) or numeric <= 0:
                            raise ValueError
                    except (TypeError, ValueError, OverflowError):
                        row["verification_status"] = "INVALID"
                        row["reason"] = "INVALID_NUMERIC_PREREQUISITE"
                elif key[1].endswith("contract_key") and (not isinstance(value, str) or not value.strip()):
                        row["verification_status"] = "INVALID"
                        row["reason"] = "INVALID_CONTRACT_KEY_PREREQUISITE"
                if row.get("verification_status") == "VERIFIED" and key[1].endswith("contract_key"):
                    expected_key = dict(target_instruments.get(strategy_id) or {}).get("contract_key")
                    source_body = source_parents[0].get("payload") if source_parents else None
                    if not expected_key or value != expected_key:
                        row["verification_status"] = "INVALID"
                        row["reason"] = "CONTRACT_MISMATCH"
                    elif (not isinstance(source_body, Mapping)
                            or source_body.get("record_type") != "FUTURES_CONTRACT_IDENTITY"
                            or source_body.get("contract_key") != value):
                        row["verification_status"] = "INVALID"
                        row["reason"] = "FUTURES_CONTRACT_SOURCE_IDENTITY_MISSING"
                if row.get("verification_status") == "VERIFIED" and key[1].endswith("close_1529"):
                    exact_timestamp = f"{source_date.isoformat()}T15:29:00+05:30"
                    expected_epoch = datetime.fromisoformat(exact_timestamp).timestamp()
                    source_body = source_parents[0].get("payload") if source_parents else None
                    try:
                        source_time = float(source_parents[0].get("source_event_epoch")) if source_parents else None
                    except (TypeError, ValueError, OverflowError):
                        source_time = None
                    if (not isinstance(source_body, Mapping)
                            or source_body.get("record_type") != "FUTURES_BAR"
                            or source_body.get("bar_interval") != "1m"
                            or source_body.get("bar_timestamp_semantics") != "BAR_END"
                            or source_body.get("bar_timestamp_ist") != exact_timestamp
                            or source_body.get("bar_status") != "COMPLETE"
                            or source_body.get("close") != value
                            or source_time != expected_epoch):
                        row["verification_status"] = "INVALID"
                        row["reason"] = "EXACT_1529_REGULAR_SESSION_FUTURES_BAR_REQUIRED"
                if row.get("verification_status") == "VERIFIED" and key[1].endswith("daily_close"):
                    source_body = source_parents[0].get("payload") if source_parents else None
                    if (not isinstance(source_body, Mapping)
                            or source_body.get("record_type") != "NIFTY50_DAILY_CLOSE"
                            or source_body.get("trading_date") != source_date.isoformat()
                            or source_body.get("close") != value):
                        row["verification_status"] = "INVALID"
                        row["reason"] = "PREVIOUS_ELIGIBLE_DAILY_CLOSE_SOURCE_REQUIRED"
                if row.get("verification_status") == "VERIFIED" and key[1].endswith("sma200"):
                    source_body = source_parents[0].get("payload") if source_parents else None
                    calendar_body = next((nodes_by_id[str(edge.get("parent_id"))].get("payload")
                        for edge in parents if edge.get("requirement") == "PREVIOUS_ELIGIBLE_SESSION"
                        and str(edge.get("parent_id")) in nodes_by_id), None)
                    try:
                        if not isinstance(source_body, Mapping) or not isinstance(calendar_body, Mapping):
                            raise ValueError("SMA200_VERIFIED_SERIES_AND_CALENDAR_REQUIRED")
                        expected_dates = calendar_body.get("rolling_session_dates")
                        rows = source_body.get("rolling_close_rows")
                        formula_id = body.get("rolling_formula_id")
                        adjustment_id = body.get("rolling_adjustment_id")
                        if (not isinstance(expected_dates, list) or len(expected_dates) != 200
                                or not isinstance(rows, list) or len(rows) != 200
                                or formula_id != "sma200-daily-close-v1"
                                or calendar_body.get("rolling_session_dates")[-1] != source_date.isoformat()):
                            raise ValueError("SMA200_COMPLETE_200_SESSION_ANCESTRY_REQUIRED")
                        rolling = verify_rolling_close_series(rows=rows,
                            target_session=target_date.isoformat(),
                            instrument=dict(target_instruments.get(strategy_id) or {}),
                            calendar_id=str(target_session["calendar_id"]),
                            calendar_version=str(target_session["calendar_version"]),
                            formula_id=formula_id, expected_session_dates=expected_dates,
                            window=200, decision_epoch=decision_epoch,
                            expected_adjustment_id=adjustment_id)
                        if rolling.get("status") != "VERIFIED":
                            raise ValueError(str(rolling.get("reason") or "SMA200_SOURCE_SERIES_INVALID"))
                        if (float(rolling.get("value")) != float(value)
                                or rolling.get("computation_sha256") != body.get("rolling_computation_sha256")):
                            raise ValueError("SMA200_INDEPENDENT_RECOMPUTATION_MISMATCH")
                    except (KeyError, TypeError, ValueError, OverflowError) as exc:
                        row["verification_status"] = "INVALID"
                        row["reason"] = str(exc) or "SMA200_INDEPENDENT_RECOMPUTATION_MISMATCH"
            if key in fields and fields[key] != row:
                conflicts.add(key)
            fields[key] = row
        readiness: dict[str, Any] = {}
        accepted: dict[tuple[str, str], dict[str, Any]] = {}
        for strategy_id, contracts in required_fields.items():
            candidates: dict[str, Mapping[str, Any]] = {}
            local_contracts = dict(contracts)
            local_instrument = target_instruments.get(strategy_id)
            if not isinstance(local_instrument, Mapping):
                local_instrument = {}
            for field in contracts:
                key = (strategy_id, field)
                if key in conflicts:
                    candidates[field] = {"verification_status": "CONFLICT", "reason": "CONFLICTING_PREREQUISITE_NODES"}
                elif key in fields:
                    candidates[field] = fields[key]
            result = evaluate_prerequisite_readiness(
                strategy_id=strategy_id, required_fields=local_contracts,
                verified_fields=candidates, decision_epoch=decision_epoch,
                target_instrument=local_instrument, target_session=target_session)
            readiness[strategy_id] = result
            if result["status"] == "READY":
                for field in contracts:
                    accepted[(strategy_id, field)] = dict(candidates[field])

        # Preserve the legacy adapter interface while exposing only values whose
        # entire strategy prerequisite set passed the field-local contract.
        od = readiness.get("INTRADAY_OPENING_DRIVE_V1", {})
        if od.get("status") == "READY":
            for field, output in (("opening_drive_prev_contract_key", "opening_drive_prev_contract_key"),
                                  ("opening_drive_prev_close_1529", "opening_drive_prev_close_1529"),
                                  ("opening_drive_target_expiry", "opening_drive_target_expiry")):
                item = accepted.get(("INTRADAY_OPENING_DRIVE_V1", field))
                if item is not None:
                    empty[output] = item.get("value")
        for strategy_id in ("S1_MOMENTUM_OVERNIGHT_V1", "S4_MONDAY_OVERNIGHT_V1"):
            if readiness.get(strategy_id, {}).get("status") == "READY":
                close = accepted.get((strategy_id, "overnight_prev_daily_close"))
                sma = accepted.get((strategy_id, "overnight_prev_sma200"))
                if close is not None and sma is not None:
                    # Both frozen strategies require the same source values. If
                    # their manifests disagree, keep both strategies blocked.
                    prior = empty.get("overnight_prev_daily_close")
                    prior_sma = empty.get("overnight_prev_sma200")
                    if prior is not None and (prior != close.get("value") or prior_sma != sma.get("value")):
                        readiness[strategy_id] = {"status": "BLOCKED", "reason": "STRATEGY_PREREQUISITE_VALUE_CONFLICT", **AUTHORITY}
                    else:
                        empty["overnight_prev_daily_close"] = close.get("value")
                        empty["overnight_prev_sma200"] = sma.get("value")
        all_ready = bool(readiness) and all(row.get("status") == "READY" for row in readiness.values())
        return {**empty, "heritage_verification": {
            "status": "VERIFIED" if all_ready else "PARTIAL",
            "reason": "PINNED_HASH_BOUND_HERITAGE_MANIFEST",
            "manifest_path": str(path), "manifest_sha256": actual_sha,
            "target_session": dict(session), "strategy_readiness": readiness,
            **AUTHORITY}}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return {**{key: None for key in empty}, "heritage_verification": {
            "status": "BLOCKED", "reason": str(exc) or "INVALID_HERITAGE_MANIFEST",
            "manifest_path": str(path), "manifest_sha256": None,
            "strategy_readiness": {}, **AUTHORITY}}


def verify_rolling_close_series(*, rows: list[Mapping[str, Any]], target_session: str,
                                instrument: Mapping[str, Any], calendar_id: str,
                                calendar_version: str, formula_id: str,
                                expected_session_dates: list[str],
                                window: int = 200, decision_epoch: float | None = None,
                                expected_adjustment_id: str | None = None) -> dict[str, Any]:
    """Validate a complete frozen close series and independently calculate SMA.

    Rows must be one verified close per eligible session, already resolved by
    an authoritative calendar. This function does not discover or synthesize
    rows and deliberately rejects incomplete or ambiguous history.
    """
    if window < 1 or not formula_id or not calendar_id or not calendar_version:
        return {"status": "BLOCKED", "reason": "INVALID_ROLLING_CONTRACT", **AUTHORITY}
    try:
        expected_dates = [date.fromisoformat(str(item)).isoformat() for item in expected_session_dates]
    except (TypeError, ValueError):
        return {"status": "BLOCKED", "reason": "INVALID_EXPECTED_SESSION_SEQUENCE", **AUTHORITY}
    if len(expected_dates) != window or expected_dates != sorted(set(expected_dates)) or expected_dates[-1] >= target_session:
        return {"status": "BLOCKED", "reason": "INVALID_EXPECTED_SESSION_SEQUENCE", **AUTHORITY}
    if len(rows) != window:
        return {"status": "BLOCKED", "reason": "ROLLING_COVERAGE_COUNT_MISMATCH",
                "expected_count": window, "actual_count": len(rows), **AUTHORITY}
    normalized: list[tuple[date, float, str]] = []
    seen_dates: set[str] = set()
    hashes: list[str] = []
    for row in rows:
        try:
            session_date = date.fromisoformat(str(row["trading_date"]))
            close_value = float(row["close"])
            if row.get("verification_status") != "VERIFIED":
                raise ValueError("SOURCE_NOT_VERIFIED")
            if dict(row.get("instrument") or {}) != dict(instrument):
                raise ValueError("WRONG_INSTRUMENT_OR_CONTRACT")
            if row.get("calendar_id") != calendar_id or row.get("calendar_version") != calendar_version:
                raise ValueError("CALENDAR_VERSION_MISMATCH")
            if row.get("formula_id") != formula_id:
                raise ValueError("FORMULA_VERSION_MISMATCH")
            if row.get("eligible_session") is not True or row.get("complete") is not True:
                raise ValueError("INCOMPLETE_OR_INELIGIBLE_SESSION")
            if row.get("adjustment_id") != expected_adjustment_id:
                raise ValueError("ADJUSTMENT_OR_ROLL_AMBIGUITY")
            available = float(row["available_epoch"])
            if decision_epoch is not None and available > decision_epoch:
                raise ValueError("FUTURE_INFORMATION")
            if not math.isfinite(close_value) or close_value <= 0:
                raise ValueError("INVALID_CLOSE")
            if not _valid_hash(row.get("content_sha256")):
                raise ValueError("INVALID_SOURCE_HASH")
            if rolling_source_row_hash(row) != row["content_sha256"]:
                raise ValueError("SOURCE_ROW_HASH_MISMATCH")
            session_text = session_date.isoformat()
            if session_text in seen_dates:
                raise ValueError("DUPLICATE_SESSION_BAR")
            if session_text >= target_session:
                raise ValueError("POST_TARGET_SESSION_BAR")
            seen_dates.add(session_text)
            normalized.append((session_date, close_value, str(row["content_sha256"])))
            hashes.append(str(row["content_sha256"]))
        except (KeyError, TypeError, ValueError) as exc:
            return {"status": "BLOCKED", "reason": str(exc) or "INVALID_ROLLING_SOURCE_ROW", **AUTHORITY}
    normalized.sort(key=lambda item: item[0])
    observed_dates = [item[0].isoformat() for item in normalized]
    if observed_dates != expected_dates:
        return {"status": "BLOCKED", "reason": "ROLLING_SESSION_SEQUENCE_MISMATCH", **AUTHORITY}
    hashes = [item[2] for item in normalized]
    value = math.fsum(item[1] for item in normalized) / window
    result = {"status": "VERIFIED", "reason": "INDEPENDENT_CLOSE_SERIES_RECOMPUTATION",
              "field": f"sma{window}", "value": value, "unit": "price_points",
              "window": window, "first_session": normalized[0][0].isoformat(),
              "last_session": normalized[-1][0].isoformat(),
              "target_session": target_session, "formula_id": formula_id,
              "calendar_id": calendar_id, "calendar_version": calendar_version,
              "instrument": dict(instrument), "adjustment_id": expected_adjustment_id,
              "source_hashes": hashes,
              "computation_sha256": content_hash({"formula_id": formula_id,
                  "window": window, "source_hashes": hashes, "value": value,
                  "target_session": target_session}), **AUTHORITY}
    return result


def verify_manifest(path: str | Path, *, decision_epoch: float | None = None) -> dict[str, Any]:
    """Independently load and verify a published graph; never writes to it."""
    manifest_path = Path(path)
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("MANIFEST_SIZE_BOUND_EXCEEDED")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("UNSUPPORTED_MANIFEST_SCHEMA")
        session_identity = payload.get("session_identity")
        if not isinstance(session_identity, dict) or not all(session_identity.get(key) for key in ("trading_date", "venue", "calendar_id", "calendar_version")):
            raise ValueError("MANIFEST_SESSION_IDENTITY_REQUIRED")
        graph = HeritageGraph()
        for node in payload.get("nodes", []):
            graph.add_node(node)
        for edge in payload.get("edges", []):
            graph.add_edge(parent_id=edge["parent_id"], child_id=edge["child_id"],
                           requirement=edge["requirement"], parent_hash=edge["parent_hash"],
                           outcome=edge.get("outcome", ""), reason=edge.get("reason", ""))
        result = graph.verify(decision_epoch=decision_epoch)
        expected_graph_hash = content_hash({"session_identity": session_identity, "nodes": sorted(graph.nodes), "edges": [graph.edges[k] for k in sorted(graph.edges)]})
        if payload.get("graph_sha256") != expected_graph_hash:
            result["errors"].append({"code": "GRAPH_HASH_MISMATCH", "id": "manifest"})
        raw_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        result["manifest_sha256"] = raw_hash
        if result["errors"]:
            result["verdict"] = "BLOCKED"
        return result
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        code = str(exc) if str(exc) in {
            "NODE_HASH_MISMATCH", "UNRESOLVED_ANCESTOR", "PARENT_HASH_MISMATCH",
            "DEPENDENCY_CYCLE", "UNSUPPORTED_NODE_SCHEMA", "UNSUPPORTED_MANIFEST_SCHEMA",
        } else "INVALID_MANIFEST"
        return {"schema_version": SCHEMA_VERSION, "node_count": 0, "edge_count": 0,
                "errors": [{"code": code, "id": str(exc)}],
                "verdict": "BLOCKED", **AUTHORITY}
