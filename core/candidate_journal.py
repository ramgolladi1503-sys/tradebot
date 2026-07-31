from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.log_writer import get_jsonl_writer
from core.paths import runtime_dir
from core.replay_context_recorder import build_replay_context_record

logger = logging.getLogger(__name__)

JOURNAL_SCHEMA_VERSION = 1
_DEFAULT_JOURNAL_SUBDIR = "candidates"
_DEFAULT_JOURNAL_FILENAME = "candidate_journal.jsonl"
_FALSE_FIELDS = {
    "is_order_action",
    "broker_api_called",
    "live_order_allowed",
    "live_order_action",
    "broker_order_action",
    "allowed_for_live_execution",
    "live_execution_changed",
    "behavior_changed",
    "runtime_behavior_changed",
    "order_behavior_changed",
    "execution_behavior_changed",
}
_LIST_FIELDS = {
    "execution_truth_blockers",
    "blockers",
    "hard_blockers",
    "soft_penalties",
    "warnings",
}


def candidate_journal_path() -> Path:
    try:
        from config import config as cfg

        raw = str(getattr(cfg, "CANDIDATE_JOURNAL_PATH", "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        return Path(raw).expanduser()
    return runtime_dir() / _DEFAULT_JOURNAL_SUBDIR / _DEFAULT_JOURNAL_FILENAME


def _iso_utc(value: Any = None) -> str:
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if value is None:
        dt = datetime.now(timezone.utc)
    else:
        try:
            raw = float(value)
        except Exception:
            dt = datetime.now(timezone.utc)
        else:
            if raw > 1_000_000_000_000:
                raw = raw / 1000.0
            dt = datetime.fromtimestamp(raw, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper_text(value: Any) -> str:
    return _text(value).upper()


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return bool(default)


def _number(value: Any) -> int | float | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    return int(number) if number.is_integer() else number


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if value in (None, "", "None"):
        return []
    return [value]


def _iso_utc_from_epoch(value: Any) -> str | None:
    if value in (None, "", "None"):
        return None
    try:
        raw = float(value)
    except Exception:
        return None
    if raw > 1_000_000_000_000:
        raw = raw / 1000.0
    return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _normalise_oos_label(value: Any) -> str | None:
    text = _text(value).upper()
    if text in {"OOS", "OUT_OF_SAMPLE"}:
        return "OOS"
    if text in {"IS", "IN_SAMPLE"}:
        return "IS"
    return None


def _derive_signal_ts(row: Mapping[str, Any], created_at_text: str) -> tuple[str | None, str]:
    for key in ("signal_ts", "decision_ts_utc", "decision_ts_iso", "created_ts_utc", "created_at"):
        value = row.get(key)
        if value not in (None, "", "None"):
            return _text(value), f"preserved:{key}"
    generated_epoch = row.get("generated_epoch")
    if generated_epoch not in (None, "", "None"):
        return _iso_utc_from_epoch(generated_epoch), "derived:generated_epoch"
    if created_at_text:
        return created_at_text, "derived:created_at"
    return None, "missing"


def _derive_feature_cutoff_ts(row: Mapping[str, Any]) -> tuple[str | None, str]:
    for key in ("feature_cutoff_ts", "snapshot_ts_utc", "snapshot_ts_iso", "snapshot_ts"):
        value = row.get(key)
        if value not in (None, "", "None"):
            return _text(value), f"preserved:{key}"
    for key in ("snapshot_ts_epoch", "snapshot_epoch"):
        value = row.get(key)
        if value not in (None, "", "None"):
            return _iso_utc_from_epoch(value), f"derived:{key}"
    return None, "missing"


def _derive_earliest_entry_ts(row: Mapping[str, Any]) -> tuple[str | None, str]:
    for key in ("earliest_entry_ts", "entry_ts", "execution_ts", "entry_timestamp", "entry_time"):
        value = row.get(key)
        if value not in (None, "", "None"):
            return _text(value), f"preserved:{key}"
    return None, "missing"


def _first_present(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", "None"):
            return value
    return None


def _fallback_used(payload: Mapping[str, Any]) -> bool:
    row_kind = _text(payload.get("row_kind")).lower()
    candidate_class = _text(payload.get("candidate_class")).lower()
    candidate_type = _text(payload.get("candidate_type")).lower()
    candidate_origin = _text(payload.get("candidate_origin")).lower()
    quote_source = _text(payload.get("quote_source")).lower()
    trade_id = _text(payload.get("trade_id")).lower()
    source_flags = payload.get("source_flags")
    flags = source_flags if isinstance(source_flags, Mapping) else {}
    flag_values = (
        _bool(flags.get("fallback_used")),
        _bool(flags.get("recovered_fallback")),
        _bool(flags.get("softened")),
        _bool(flags.get("soft_reject_fallback")),
    )
    if any(flag_values):
        return True
    if row_kind in {"recovered_fallback", "fallback"}:
        return True
    if candidate_class == "fallback":
        return True
    if "fallback" in candidate_type:
        return True
    if "fallback" in candidate_origin:
        return True
    if quote_source in {"rest_fallback", "synthetic_offhours", "subscription_failed"}:
        return True
    if trade_id.startswith("softrej_"):
        return True
    return False


def _candidate_id(payload: Mapping[str, Any], created_at: str) -> str:
    candidate_id = _text(payload.get("candidate_id"))
    if candidate_id:
        return candidate_id
    trade_id = _text(payload.get("trade_id"))
    if trade_id:
        return trade_id
    fingerprint = {
        "symbol": _text(payload.get("symbol")),
        "strategy_family": _text(payload.get("strategy_family")),
        "side": _text(payload.get("side")),
        "direction": _text(payload.get("direction")),
        "strike": payload.get("strike"),
        "expiry": _text(_first_present(payload, "expiry", "expiry_date")),
        "entry": payload.get("entry"),
        "created_at_bucket": created_at[:16],
    }
    digest = hashlib.sha1(json.dumps(fingerprint, sort_keys=True, default=str).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return f"cand_{digest}"


def _journal_row(payload: Mapping[str, Any], *, journal_event: str, created_at: str) -> dict[str, Any]:
    row = dict(payload or {})
    created_at_text = _text(row.get("created_at")) or created_at
    row["schema_version"] = JOURNAL_SCHEMA_VERSION
    row["journal_event"] = _text(journal_event) or "candidate_journal"
    row["created_at"] = created_at_text
    row["candidate_id"] = _candidate_id(row, created_at_text)
    row["trade_id"] = _text(_first_present(row, "trade_id", "candidate_id")) or row["candidate_id"]
    row["symbol"] = _text(row.get("symbol"))
    row["index"] = _text(_first_present(row, "index", "underlying_index", "symbol"))
    row["strike"] = row.get("strike")
    row["expiry"] = _first_present(row, "expiry", "expiry_date")
    row["option_type"] = _text(_first_present(row, "option_type", "type")).upper() or _text(_first_present(row, "option_type", "type"))
    row["strategy_family"] = _text(row.get("strategy_family"))
    row["strategy_id"] = _text(row.get("strategy_id"))
    row["regime"] = _text(row.get("regime"))
    row["side"] = _text(row.get("side")).upper() or _text(row.get("side"))
    row["direction"] = _text(row.get("direction")).upper() or _text(row.get("direction"))

    for field in (
        "entry",
        "entry_price",
        "execution_entry",
        "execution_entry_status",
        "display_entry",
        "display_entry_status",
        "stop_loss",
        "target",
        "target_price",
    ):
        row[field] = row.get(field)

    for field in (
        "rank_score",
        "raw_rank_score",
        "confidence",
        "confidence_raw",
        "confidence_final",
        "opportunity_score",
        "quote_age_sec",
        "spread_pct",
        "bid",
        "ask",
        "best_bid",
        "best_ask",
        "ltp",
        "current_ltp",
    ):
        row[field] = _number(row.get(field))

    row["quote_source"] = _text(row.get("quote_source"))
    row["oos_source"] = _text(row.get("oos_source"))
    row["quote_validation_status"] = _text(row.get("quote_validation_status"))
    row["feed_truth_state"] = _text(row.get("feed_truth_state"))
    row["feed_truth_reason_code"] = _text(row.get("feed_truth_reason_code"))
    row["feed_truth_source"] = _text(row.get("feed_truth_source"))
    row["execution_truth_state"] = _text(row.get("execution_truth_state"))
    row["execution_truth_blocked"] = _bool(row.get("execution_truth_blocked"))
    row["execution_truth_advisory"] = _bool(row.get("execution_truth_advisory"))
    row["execution_truth_blockers"] = _list(row.get("execution_truth_blockers"))
    row["fallback_used"] = _bool(row.get("fallback_used")) or _fallback_used(row)
    row["row_kind"] = _text(row.get("row_kind"))
    row["candidate_origin"] = _text(row.get("candidate_origin"))
    row["candidate_class"] = _text(row.get("candidate_class"))

    feature_cutoff_ts, feature_cutoff_source = _derive_feature_cutoff_ts(row)
    signal_ts, signal_ts_source = _derive_signal_ts(row, created_at_text)
    earliest_entry_ts, earliest_entry_source = _derive_earliest_entry_ts(row)
    row["feature_cutoff_ts"] = feature_cutoff_ts
    row["signal_ts"] = signal_ts
    row["earliest_entry_ts"] = earliest_entry_ts
    row["feature_cutoff_ts_source"] = feature_cutoff_source
    row["signal_ts_source"] = signal_ts_source
    row["earliest_entry_ts_source"] = earliest_entry_source

    is_oos_value = row.get("is_oos")
    oos_label_value = row.get("oos_label")
    if is_oos_value in (None, "", "None"):
        row["is_oos"] = None
        if _normalise_oos_label(oos_label_value) is None:
            row["oos_label"] = None
            row["oos_source"] = _text(row.get("oos_source")) or "unknown_runtime_context"
        else:
            row["oos_label"] = _normalise_oos_label(oos_label_value)
            row["oos_source"] = _text(row.get("oos_source")) or "preserved:oos_label"
    else:
        row["is_oos"] = _bool(is_oos_value)
        derived_oos_label = _normalise_oos_label(oos_label_value)
        if derived_oos_label is None:
            row["oos_label"] = "OOS" if row["is_oos"] else "IS"
            row["oos_source"] = _text(row.get("oos_source")) or "derived:is_oos"
        else:
            row["oos_label"] = derived_oos_label
            row["oos_source"] = _text(row.get("oos_source")) or "preserved:oos_label"

    row["reportable_executable"] = _bool(row.get("reportable_executable"))
    row["execution_allowed"] = _bool(row.get("execution_allowed"))
    row["eligible_for_execution"] = _bool(row.get("eligible_for_execution"))
    row["permission"] = _text(row.get("permission")).upper() or _text(row.get("permission"))
    row["final_action"] = _text(row.get("final_action")).upper() or _text(row.get("final_action"))
    row["execution_status"] = _text(row.get("execution_status")).lower() or _text(row.get("execution_status"))
    row["readiness"] = _text(row.get("readiness")).upper() or _text(row.get("readiness"))
    row["candidate_status"] = _text(row.get("candidate_status")).lower() or _text(row.get("candidate_status"))
    row["visibility_bucket"] = _text(row.get("visibility_bucket")).lower() or _text(row.get("visibility_bucket"))

    row["blockers"] = _list(row.get("blockers"))
    row["hard_blockers"] = _list(row.get("hard_blockers"))
    row["soft_penalties"] = _list(row.get("soft_penalties"))
    row["warnings"] = _list(row.get("warnings"))
    row["final_emit_block_reason"] = row.get("final_emit_block_reason")
    row["reject_reason"] = row.get("reject_reason")
    row["reason"] = row.get("reason")

    strict_replay_blockers = []
    if feature_cutoff_ts is None:
        strict_replay_blockers.append("missing_feature_cutoff_ts")
    if signal_ts is None:
        strict_replay_blockers.append("missing_signal_ts")
    if earliest_entry_ts is None:
        strict_replay_blockers.append("missing_earliest_entry_ts")
    if row.get("is_oos") is None:
        strict_replay_blockers.append("missing_is_oos")
    if row.get("oos_label") is None:
        strict_replay_blockers.append("missing_oos_label")
    row["strict_replay_export_ready"] = not strict_replay_blockers
    row["strict_replay_export_blockers"] = strict_replay_blockers
    replay_context = build_replay_context_record(row, source="candidate_journal", require_candidate_pool_inputs=False)
    row.update(replay_context)

    from core.expectancy.setup_fingerprint import attach_setup_fingerprint

    row = attach_setup_fingerprint(row)

    row["read_only"] = True
    row["append"] = True
    for field in _FALSE_FIELDS:
        row[field] = False
    return row


def build_candidate_journal_row(
    payload: Mapping[str, Any],
    *,
    journal_event: str = "candidate_journal",
    created_at: str | None = None,
) -> dict[str, Any]:
    return _journal_row(payload, journal_event=journal_event, created_at=created_at or _iso_utc())


def write_candidate_journal_row(
    payload: Mapping[str, Any],
    *,
    journal_event: str = "candidate_journal",
    created_at: str | None = None,
    path: str | Path | None = None,
) -> tuple[dict[str, Any], bool]:
    row = build_candidate_journal_row(payload, journal_event=journal_event, created_at=created_at)
    target = Path(path).expanduser() if path is not None else candidate_journal_path()
    try:
        writer = get_jsonl_writer(target)
        success = bool(writer.write(row))
        if not success:
            logger.warning("candidate_journal_write_failed path=%s err=write_returned_false", target)
        return row, success
    except Exception as exc:
        logger.warning("candidate_journal_write_failed path=%s err=%s", target, exc)
        return row, False
