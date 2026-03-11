from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.advisory_schema import AdvisorySchemaError, log_advisory_schema_error, serialize_advisory_row
from core.learning_paths import canonical_suggestions_log_path
from core.market_snapshot_store import DEFAULT_MARKET_SNAPSHOT_PATH, read_market_snapshot
from core.paths import logs_dir
from core.runtime_snapshot_store import (
    ADVISORY_LATEST_PATH,
    FEED_RUNTIME_LATEST_PATH,
    MARKET_SNAPSHOT_PATH,
    TOKEN_RESOLUTION_LATEST_PATH,
    write_snapshot_atomic,
)


logger = logging.getLogger(__name__)


def _read_json_payload(path: Path) -> tuple[Any, list[str]]:
    notes: list[str] = []
    if not path.exists():
        notes.append(f"missing:{path}")
        return {"missing": True, "source_path": str(path)}, notes
    try:
        return json.loads(path.read_text(encoding="utf-8")), notes
    except Exception as exc:
        notes.append(f"parse_error:{path}:{type(exc).__name__}")
        return {
            "missing": False,
            "parse_error": f"{type(exc).__name__}:{exc}",
            "source_path": str(path),
        }, notes


def _tail_jsonl_rows(path: Path, limit: int = 200) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if str(line).strip()]
        if limit <= 0:
            return lines
        return lines[-int(limit) :]
    except Exception:
        return []


def _build_advisory_latest_payload(limit: int = 200) -> dict[str, Any]:
    path = canonical_suggestions_log_path()
    rows: list[dict[str, Any]] = []
    notes: list[str] = []
    for raw_line in _tail_jsonl_rows(path, limit=limit):
        try:
            payload = json.loads(raw_line)
        except Exception as exc:
            notes.append(f"parse_error:{type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            notes.append("row_not_object")
            continue
        try:
            rows.append(serialize_advisory_row(payload, allow_legacy=True))
        except AdvisorySchemaError as exc:
            log_advisory_schema_error("runtime_snapshot_producer", payload, exc)
            notes.append(f"schema_error:{exc}")
    return {
        "rows": rows,
        "row_count": int(len(rows)),
        "source_path": str(path),
        "notes": notes,
    }


def produce_and_store_runtime_snapshots(
    *,
    market_snapshot: dict[str, Any] | None,
    producer: str,
    loop_id: str | None = None,
) -> dict[str, Any]:
    del loop_id  # reserved for future producer metadata if needed
    outputs: dict[str, Any] = {}

    market_payload = market_snapshot
    if not isinstance(market_payload, dict):
        try:
            market_payload = read_market_snapshot(DEFAULT_MARKET_SNAPSHOT_PATH)
        except Exception as exc:
            market_payload = {"missing": True, "error": f"{type(exc).__name__}:{exc}"}
    outputs["market_snapshot"] = market_payload

    advisory_payload = _build_advisory_latest_payload()
    outputs["advisory_latest"] = advisory_payload

    feed_payload, _feed_notes = _read_json_payload(logs_dir() / "feed_runtime_latest.json")
    outputs["feed_runtime_latest"] = feed_payload

    token_payload, _token_notes = _read_json_payload(logs_dir() / "token_resolution.json")
    outputs["token_resolution_latest"] = token_payload

    paths = {
        "market_snapshot": MARKET_SNAPSHOT_PATH,
        "advisory_latest": ADVISORY_LATEST_PATH,
        "feed_runtime_latest": FEED_RUNTIME_LATEST_PATH,
        "token_resolution_latest": TOKEN_RESOLUTION_LATEST_PATH,
    }
    for name, path in paths.items():
        write_snapshot_atomic(path, payload=outputs[name], producer=producer)
        logger.info(
            "[RUNTIME_SNAPSHOT_WRITE] name=%s path=%s",
            name,
            path,
        )
    return outputs
