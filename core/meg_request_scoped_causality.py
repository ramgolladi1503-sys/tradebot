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
        path = root / FILES[kind]
        identity_field = {"request": "request_event_id", "tick": "selected_tick_event_id",
                          "accepted": "cycle_id", "persisted": "persistence_identity"}[kind]
        existing = set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    prior = json.loads(line)
                    if prior.get("session_id") == session_id:
                        existing.add(prior.get(identity_field))
                except (TypeError, json.JSONDecodeError):
                    raise ValueError("malformed_existing_primitive")
        if payload[identity_field] not in existing:
            append_jsonl_record(path, payload, hash_field="row_sha256")


def append_meg_cycle_primitives(root: Path, *, session_id: str, producer_commit_sha: str,
                                cycle_id: str, accepted: bool,
                                subscription_evidence: Mapping[str, Any]) -> None:
    """Project authoritative request/tick/cycle facts into append-only ledgers."""
    lifecycle = subscription_evidence.get("token_lifecycle") or {}
    for item in lifecycle.values():
        request_id = item.get("request_id")
        if not request_id or item.get("subscribe_call_succeeded_epoch") is None:
            continue
        common = dict(request_event_id=request_id, request_id=request_id,
                      request_generation=item.get("request_generation"),
                      request_success_timestamp=item.get("subscribe_call_succeeded_epoch"),
                      feed_session_id=item.get("feed_session_id"),
                      reconnect_generation=item.get("reconnect_generation"),
                      expected_instrument_token=item.get("instrument_token"),
                      expected_symbol=item.get("symbol"))
        append_primitives(root, session_id=session_id, producer_commit_sha=producer_commit_sha,
                          request=common)
        tick_id = item.get("selected_post_request_tick_id")
        if accepted and tick_id and item.get("first_post_request_tick_epoch") is not None:
            append_primitives(root, session_id=session_id, producer_commit_sha=producer_commit_sha,
                              tick=dict(selected_tick_event_id=f"{cycle_id}:{item['instrument_token']}",
                                        cycle_id=cycle_id, request_id=request_id,
                                        request_generation=item.get("request_generation"),
                                        selected_tick_id=tick_id,
                                        selected_tick_receipt_timestamp=item.get("first_post_request_tick_epoch"),
                                        selected_tick_feed_session_id=item.get("feed_session_id"),
                                        selected_tick_reconnect_generation=item.get("reconnect_generation"),
                                        selected_tick_instrument_token=item.get("instrument_token"),
                                        selected_tick_symbol=item.get("symbol")))
    if accepted:
        append_primitives(root, session_id=session_id, producer_commit_sha=producer_commit_sha,
                          accepted=dict(cycle_id=cycle_id, accepted=True),
                          persisted=dict(cycle_id=cycle_id, persistence_identity=f"{session_id}:{cycle_id}"))


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
