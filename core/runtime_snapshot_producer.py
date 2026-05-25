from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import config as cfg
from core.advisory_schema import AdvisorySchemaError, log_advisory_schema_error, serialize_advisory_row
from core.feed_health_truth import classify_feed_health_truth
from core.learning_paths import canonical_suggestions_log_path
from core.market_snapshot_store import DEFAULT_MARKET_SNAPSHOT_PATH, read_market_snapshot
from core.paths import logs_dir, runtime_dir
from core.time_utils import is_today_local, now_ist
from core.runtime_snapshot_store import (
    ADVISORY_LATEST_PATH,
    FEED_RUNTIME_LATEST_PATH,
    MARKET_SNAPSHOT_PATH,
    TOKEN_RESOLUTION_LATEST_PATH,
    write_snapshot_atomic,
)


logger = logging.getLogger(__name__)

FEED_HEALTH_TRUTH_LATEST_PATH = runtime_dir() / "feed_health_truth_latest.json"
FEED_HEALTH_TRUTH_SNAPSHOT_SCHEMA_VERSION = 1


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


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "None"):
            return default
        out = float(value)
    except Exception:
        return default
    if out != out:
        return default
    return float(out)


def _candidate_decisions_log_path() -> Path:
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT").strip() or "DEFAULT"
    return logs_dir() / "desks" / desk_id / "candidate_decisions.jsonl"


def _row_snapshot_timestamp(row: dict[str, Any]) -> Any:
    if not isinstance(row, dict):
        return None
    for key in (
        "display_ts_epoch",
        "decision_ts_epoch",
        "snapshot_ts_epoch",
        "created_ts_epoch",
        "last_seen_ts_epoch",
        "timestamp_epoch",
        "timestamp",
        "last_seen_ts",
        "last_seen",
    ):
        value = row.get(key)
        if value not in (None, "", "None"):
            return value
    return None


def _row_is_today_local(row: dict[str, Any]) -> bool:
    ts_value = _row_snapshot_timestamp(row)
    if ts_value in (None, "", "None"):
        return False
    try:
        return is_today_local(ts_value, now=now_ist())
    except Exception:
        return False


def _feed_health_symbols(feed_payload: Any) -> tuple[str, ...]:
    if not isinstance(feed_payload, dict):
        return ()
    symbols: set[str] = set()
    for key in (
        "option_feed_block_reason_by_symbol",
        "option_last_tick_age_by_symbol",
        "symbol_feed_ok_by_symbol",
        "feed_ok_by_symbol",
    ):
        values = feed_payload.get(key)
        if not isinstance(values, dict):
            continue
        symbols.update(str(symbol or "").strip().upper() for symbol in values if str(symbol or "").strip())
    return tuple(sorted(symbols))


def _build_feed_health_truth_latest_payload(feed_payload: Any) -> dict[str, Any]:
    source_payload = feed_payload if isinstance(feed_payload, dict) else None
    decision = classify_feed_health_truth(
        source_payload,
        symbols=_feed_health_symbols(source_payload),
        max_option_tick_age_sec=float(getattr(cfg, "FEED_HEALTH_MAX_OPTION_TICK_AGE_SEC", 3.0)),
        max_ltp_age_sec=float(getattr(cfg, "FEED_HEALTH_MAX_LTP_AGE_SEC", 2.5)),
        max_depth_age_sec=float(getattr(cfg, "FEED_HEALTH_MAX_DEPTH_AGE_SEC", 6.0)),
    )
    return {
        "schema_version": FEED_HEALTH_TRUTH_SNAPSHOT_SCHEMA_VERSION,
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "source_snapshot": "feed_runtime_latest",
        "source_payload_present": isinstance(feed_payload, dict) and not bool(feed_payload.get("missing")),
        "feed_health_truth": decision.to_payload(),
        "feed_ok": bool(decision.feed_ok),
        "blockers": list(decision.reasons if not decision.feed_ok else ()),
        "metadata": {
            "producer": "runtime_snapshot_producer",
            "derived_from": "feed_runtime_latest",
            "symbols_evaluated": list(_feed_health_symbols(source_payload)),
        },
    }


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
            row = serialize_advisory_row(payload, allow_legacy=True)
            if bool(getattr(cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True)) and not _row_is_today_local(row):
                notes.append(
                    f"stale_row_dropped:{str(row.get('trade_id') or row.get('advisory_id') or 'unknown')}"
                )
                logger.info(
                    "[RUNTIME_SNAPSHOT_ROW_DROP] source=advisory_latest reason=stale_row trade_id=%s symbol=%s display_ts_epoch=%s",
                    row.get("trade_id"),
                    row.get("symbol"),
                    row.get("display_ts_epoch"),
                )
                continue
            rows.append(row)
        except AdvisorySchemaError as exc:
            log_advisory_schema_error("runtime_snapshot_producer", payload, exc)
            notes.append(f"schema_error:{exc}")
    if rows:
        return {
            "rows": rows,
            "row_count": int(len(rows)),
            "source_path": str(path),
            "notes": notes,
        }
    if not bool(getattr(cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", True)):
        return {
            "rows": rows,
            "row_count": int(len(rows)),
            "source_path": str(path),
            "notes": notes,
        }

    fallback_path = _candidate_decisions_log_path()
    fallback_rows: list[dict[str, Any]] = []
    fallback_notes: list[str] = []
    for raw_line in _tail_jsonl_rows(fallback_path, limit=max(1, int(getattr(cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_LIMIT", limit)))):
        try:
            payload = json.loads(raw_line)
        except Exception as exc:
            fallback_notes.append(f"fallback_parse_error:{type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            fallback_notes.append("fallback_row_not_object")
            continue
        try:
            row = _candidate_decision_to_advisory_row(payload)
            if row is None:
                fallback_notes.append(
                    f"fallback_row_dropped:{str(payload.get('candidate_id') or payload.get('trade_id') or 'unknown')}"
                )
                continue
            if bool(getattr(cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True)) and not _row_is_today_local(row):
                fallback_notes.append(
                    f"fallback_stale_row_dropped:{str(row.get('trade_id') or row.get('advisory_id') or 'unknown')}"
                )
                logger.info(
                    "[RUNTIME_SNAPSHOT_ROW_DROP] source=advisory_latest reason=fallback_stale_row trade_id=%s symbol=%s display_ts_epoch=%s",
                    row.get("trade_id"),
                    row.get("symbol"),
                    row.get("display_ts_epoch"),
                )
                continue
            fallback_rows.append(row)
        except AdvisorySchemaError as exc:
            log_advisory_schema_error("runtime_snapshot_producer.candidate_decisions", payload, exc)
            fallback_notes.append(f"fallback_schema_error:{exc}")
    notes.append(f"fallback_source:{fallback_path}")
    notes.extend(fallback_notes)
    return {
        "rows": fallback_rows,
        "row_count": int(len(fallback_rows)),
        "source_path": str(fallback_path),
        "notes": notes,
    }


def _candidate_decision_to_advisory_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    candidate_id = str(payload.get("candidate_id") or payload.get("trade_id") or "").strip()
    symbol = str(payload.get("symbol") or "").strip().upper()
    ts_epoch = _row_snapshot_timestamp(payload)
    entry = _safe_float(payload.get("entry"))
    if not candidate_id or not symbol or entry is None:
        return None
    source_flags = payload.get("source_flags") if isinstance(payload.get("source_flags"), dict) else {}
    candidate_origin = source_flags.get("candidate_origin") if isinstance(source_flags, dict) and isinstance(source_flags.get("candidate_origin"), dict) else {}
    strategy_id = (
        str(candidate_origin.get("setup_family") or candidate_origin.get("strategy") or payload.get("strategy_id") or "LIVE_CANDIDATE")
        .strip()
        or "LIVE_CANDIDATE"
    )
    strategy_name = (
        str(payload.get("strategy_name") or candidate_origin.get("setup_family") or payload.get("strategy_id") or "LIVE_CANDIDATE")
        .strip()
        or "LIVE_CANDIDATE"
    )
    execution_allowed = bool(payload.get("execution_allowed"))
    permission = str(payload.get("permission") or ("EXECUTE" if execution_allowed else "ADVISORY_ONLY")).strip().upper() or "ADVISORY_ONLY"
    final_action = str(payload.get("final_action") or ("EXECUTE" if execution_allowed else "QUEUE_ONLY")).strip().upper() or "QUEUE_ONLY"
    if execution_allowed:
        execution_entry = entry
        execution_entry_source = "last"
        execution_entry_status = "executable"
        readiness = "READY"
        execution_status = "executable"
    else:
        execution_entry = None
        execution_entry_source = "none"
        execution_entry_status = "non_executable"
        readiness = "QUEUE_ONLY" if permission != "ADVISORY_ONLY" else "ADVISORY_ONLY"
        execution_status = final_action.lower()
        if execution_status not in {"blocked", "advisory_only", "queue_only", "executable", "scored"}:
            execution_status = "queue_only"
    advisory_payload = dict(payload)
    advisory_payload.update(
        {
            "trade_id": candidate_id,
            "advisory_id": candidate_id,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "timestamp": payload.get("ts_ist") or payload.get("timestamp") or payload.get("ts_epoch") or "",
            "instrument_type": "OPT",
            "entry": entry,
            "entry_source": "last",
            "execution_entry": execution_entry,
            "execution_entry_source": execution_entry_source,
            "execution_entry_status": execution_entry_status,
            "display_entry": entry,
            "display_entry_source": "last",
            "display_entry_status": "displayable",
            "entry_reason": str(payload.get("permission_reason") or payload.get("entry_block_reason") or payload.get("first_blocking_gate") or payload.get("final_action") or "candidate_decision"),
            "entry_clear_reason": str(payload.get("entry_block_reason") or payload.get("quote_validation_status") or payload.get("first_blocking_gate") or "candidate_decision"),
            "entry_status": "displayable",
            "readiness": readiness,
            "blockers": list(payload.get("gates_failed") or ([] if execution_allowed else [payload.get("first_blocking_gate") or payload.get("permission_reason") or "candidate_decision"])),
            "hard_blockers": list(payload.get("gates_failed") or []),
            "soft_penalties": list(payload.get("soft_vetos") or []),
            "warnings": list(payload.get("gates_failed") or []),
            "quote_source": str(source_flags.get("ltp_source") or "live"),
            "quote_age_sec": _safe_float(source_flags.get("quote_age_sec")),
            "decision_explain": [
                str(value)
                for value in (
                    payload.get("first_blocking_gate"),
                    payload.get("permission_reason"),
                    payload.get("quote_validation_status"),
                    payload.get("final_action"),
                )
                if str(value or "").strip()
            ],
            "market_open": bool(source_flags.get("market_open", True)),
            "execution_status": execution_status,
            "permission": permission,
            "final_action": final_action,
        }
    )
    advisory_payload.setdefault("display_ts_epoch", ts_epoch)
    advisory_payload.setdefault("display_ts_ist", payload.get("ts_ist"))
    advisory_payload.setdefault("last_seen_ts", payload.get("ts_ist") or payload.get("timestamp"))
    advisory_payload.setdefault("last_seen", payload.get("ts_ist") or payload.get("timestamp"))
    advisory_payload.setdefault("trade_key", payload.get("candidate_id"))
    advisory_payload.setdefault("instrument", "OPT")
    advisory_payload.setdefault("status", "ADVISORY_ONLY" if not execution_allowed else "READY")
    advisory_payload.setdefault("candidate_status", payload.get("candidate_status") or "LIVE_CANDIDATE")
    advisory_payload.setdefault("candidate_type", payload.get("candidate_type") or "options")
    advisory_payload.setdefault("strategy", strategy_name)
    advisory_payload.setdefault("source_bucket", "candidate_decisions")
    advisory_payload.setdefault("row_kind", "canonical_suggestion")
    advisory_payload.setdefault("non_canonical_levels", False)
    return serialize_advisory_row(advisory_payload, allow_legacy=True)


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
    outputs["feed_health_truth_latest"] = _build_feed_health_truth_latest_payload(feed_payload)

    token_payload, _token_notes = _read_json_payload(logs_dir() / "token_resolution.json")
    outputs["token_resolution_latest"] = token_payload

    paths = {
        "market_snapshot": MARKET_SNAPSHOT_PATH,
        "advisory_latest": ADVISORY_LATEST_PATH,
        "feed_runtime_latest": FEED_RUNTIME_LATEST_PATH,
        "feed_health_truth_latest": FEED_HEALTH_TRUTH_LATEST_PATH,
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
