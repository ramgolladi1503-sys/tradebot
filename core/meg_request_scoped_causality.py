"""Append-only MEG #803 primitive evidence and independent verification.

This module contains no broker, execution, or strategy imports.  It persists
facts only; all violation counts are computed offline by ``verify_root``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.read_only_live_evidence import append_jsonl_record

SCHEMA_VERSION = 1
FILES = {
    "request": "meg_request_events.jsonl",
    "tick": "meg_selected_tick_events.jsonl",
    "accepted": "meg_accepted_cycles.jsonl",
    "persisted": "meg_persisted_cycles.jsonl",
}


def _required(row: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    if any(row.get(field) in (None, "") for field in fields):
        raise ValueError("missing_required_primitive:" + ",".join(fields))


def append_primitives(root: Path, *, session_id: str, producer_commit_sha: str,
                      request: Mapping[str, Any] | None = None,
                      tick: Mapping[str, Any] | None = None,
                      accepted: Mapping[str, Any] | None = None,
                      persisted: Mapping[str, Any] | None = None) -> None:
    """Append factual rows, refusing incomplete rows before touching disk."""
    common = {"schema_version": SCHEMA_VERSION, "session_id": session_id,
              "producer_commit_sha": producer_commit_sha}
    specs = (
        (request, "request", ("request_event_id", "request_id", "request_generation",
                               "request_success_timestamp", "feed_session_id",
                               "reconnect_generation", "expected_instrument_token", "expected_symbol")),
        (tick, "tick", ("selected_tick_event_id", "cycle_id", "request_id", "request_generation",
                         "selected_tick_id", "selected_tick_receipt_timestamp",
                         "selected_tick_feed_session_id", "selected_tick_reconnect_generation",
                         "selected_tick_instrument_token", "selected_tick_symbol")),
        (accepted, "accepted", ("cycle_id", "accepted")),
        (persisted, "persisted", ("cycle_id", "persistence_identity")),
    )
    for row, kind, fields in specs:
        if row is None:
            continue
        payload = {**common, **dict(row), "evidence_kind": kind}
        _required(payload, fields)
        append_jsonl_record(root / FILES[kind], payload, hash_field="row_sha256")


def _rows(root: Path, kind: str) -> list[dict[str, Any]]:
    path = root / FILES[kind]
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("malformed_primitive_row")
            expected = row.pop("row_sha256", None)
            actual = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
            if expected != actual:
                raise ValueError("primitive_checksum_mismatch")
            row["row_sha256"] = expected
            out.append(row)
    return out


def verify_root(root: Path) -> dict[str, Any]:
    """Verify one sealed-root-shaped directory; never mutates it."""
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "evidence_root": str(root),
                              "manifest_verified": False, "seal_verified": False,
                              "verdict": "INCOMPLETE_MEG_REQUEST_SCOPED_CAUSALITY_EVIDENCE"}
    try:
        rows = {kind: _rows(root, kind) for kind in FILES}
        all_rows = [row for values in rows.values() for row in values]
        sessions = {row.get("session_id") for row in all_rows}
        commits = {row.get("producer_commit_sha") for row in all_rows}
        if len(sessions) != 1 or len(commits) != 1 or not all_rows:
            raise ValueError("mixed_or_missing_session")
        manifest = root / "manifest.json"
        if not manifest.is_file():
            raise ValueError("manifest_missing")
        result.update(session_id=next(iter(sessions)), producer_commit_sha=next(iter(commits)))
        for kind, values in rows.items():
            for row in values:
                _required(row, ("session_id", "producer_commit_sha", "schema_version"))
        requests, ticks, accepted, persisted = (rows[k] for k in ("request", "tick", "accepted", "persisted"))
        request_ids = {}
        request_reuse = 0
        for row in requests:
            key = row["request_id"]
            identity = tuple(row[x] for x in ("request_event_id", "request_generation", "expected_instrument_token"))
            if key in request_ids and request_ids[key] != identity:
                request_reuse += 1
            request_ids[key] = identity
        tick_ids = [row["selected_tick_id"] for row in ticks]
        selected_reuse = len(tick_ids) - len(set(tick_ids))
        request_by_id = {row["request_id"]: row for row in requests}
        wrong_generation = wrong_symbol = causal = 0
        for row in ticks:
            request = request_by_id.get(row["request_id"])
            if request is None:
                raise ValueError("tick_request_missing")
            if (row["selected_tick_reconnect_generation"] != request["reconnect_generation"] or
                    row["request_generation"] != request["request_generation"]):
                wrong_generation += 1
            if row["selected_tick_instrument_token"] != request["expected_instrument_token"]:
                wrong_symbol += 1
            if float(row["selected_tick_receipt_timestamp"]) < float(request["request_success_timestamp"]):
                causal += 1
        accepted_ids = {row["cycle_id"] for row in accepted if row.get("accepted") is True}
        persisted_ids = {row["cycle_id"] for row in persisted}
        mismatch = len(accepted_ids - persisted_ids) + len(persisted_ids - accepted_ids)
        result.update(request_event_count=len(requests), selected_tick_event_count=len(ticks),
                      accepted_cycle_count=len(accepted_ids), persisted_cycle_count=len(persisted_ids),
                      request_id_reuse=request_reuse, selected_tick_id_reuse=selected_reuse,
                      wrong_generation_ticks=wrong_generation, wrong_symbol_ticks=wrong_symbol,
                      causality_violations=causal, accepted_cycle_persistence_mismatch=mismatch,
                      accepted_not_persisted=sorted(accepted_ids - persisted_ids),
                      persisted_without_accepted_authority=sorted(persisted_ids - accepted_ids),
                      manifest_verified=True, seal_verified=(root / "SEALED").is_file())
        if result["manifest_verified"] and result["seal_verified"] and all(result[k] == 0 for k in (
            "request_id_reuse", "selected_tick_id_reuse", "wrong_generation_ticks",
            "wrong_symbol_ticks", "causality_violations", "accepted_cycle_persistence_mismatch")):
            result["verdict"] = "PASS_MEG_REQUEST_SCOPED_CAUSALITY"
        else:
            result["verdict"] = "FAIL_MEG_REQUEST_SCOPED_CAUSALITY"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
    return result
