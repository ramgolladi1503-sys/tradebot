from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

_FIELD_SOURCES: dict[str, tuple[str, ...]] = {
    "snapshot_ts_utc": ("snapshot_ts_utc", "snapshot_ts_iso", "snapshot_ts", "snapshot_ts_epoch"),
    "feature_cutoff_ts": ("feature_cutoff_ts", "snapshot_ts_utc", "snapshot_ts_iso", "snapshot_ts", "snapshot_ts_epoch"),
    "signal_ts": ("signal_ts", "decision_ts_utc", "decision_ts_iso", "created_ts_utc", "created_at", "generated_epoch"),
    "earliest_entry_ts": ("earliest_entry_ts", "entry_ts", "execution_ts", "entry_timestamp", "entry_time"),
    "is_oos": ("is_oos",),
    "oos_label": ("oos_label",),
    "oos_source": ("oos_source",),
    "partition_id": ("partition_id",),
    "split_name": ("split_name",),
    "feed_truth_state": ("feed_truth_state", "feed_health_state"),
    "feed_truth_reason_code": ("feed_truth_reason_code", "feed_health_reason_code"),
    "regime": ("regime", "regime_hint", "primary_regime"),
    "regime_source": ("regime_source",),
    "global_cue_state": ("global_cue_state", "market_context", "confluence_input"),
    "option_type": ("option_type", "type"),
    "strike": ("strike",),
    "expiry": ("expiry", "expiry_date"),
    "bid": ("bid", "best_bid"),
    "ask": ("ask", "best_ask"),
    "quote_source": ("quote_source",),
    "quote_age_sec": ("quote_age_sec",),
    "trade_builder_raw_count": ("trade_builder_raw_count",),
    "top_opportunities_source_candidate_count": ("top_opportunities_source_candidate_count", "source_candidate_count"),
    "top_opportunities_executable_count": ("top_opportunities_executable_count", "top_executable_count"),
    "ranked_total_count": ("ranked_total_count",),
    "ranked_executable_count": ("ranked_executable_count",),
    "phase2_input_count": ("phase2_input_count",),
}

_TIMING_FIELDS = {"feature_cutoff_ts", "signal_ts", "earliest_entry_ts"}
_OOS_FIELDS = {"is_oos", "oos_label"}
_CONTEXT_FIELDS = {
    "feed_truth_state",
    "feed_truth_reason_code",
    "regime",
    "option_type",
    "strike",
    "expiry",
    "bid",
    "ask",
    "quote_source",
    "quote_age_sec",
}
_HANDOFF_COUNT_FIELDS = {
    "trade_builder_raw_count",
    "top_opportunities_source_candidate_count",
    "top_opportunities_executable_count",
    "ranked_total_count",
    "ranked_executable_count",
    "phase2_input_count",
}


def build_replay_context_record(
    payload: Mapping[str, Any] | None,
    *,
    source: str,
    require_candidate_pool_inputs: bool = False,
) -> dict[str, Any]:
    row = dict(payload or {})
    extracted: dict[str, Any] = {}
    field_sources: dict[str, str] = {}
    blockers: list[str] = []

    for field, source_keys in _FIELD_SOURCES.items():
        value, value_source = _extract_field(row, field, source_keys)
        extracted[field] = value
        field_sources[f"{field}_source"] = value_source

    required_fields = set(_TIMING_FIELDS) | set(_OOS_FIELDS) | set(_CONTEXT_FIELDS)
    if require_candidate_pool_inputs:
        required_fields |= set(_HANDOFF_COUNT_FIELDS)

    for field in sorted(required_fields):
        if extracted.get(field) in (None, "", "None"):
            blockers.append(f"missing_{field}")

    replay_context = {
        **extracted,
        "candidate_pool_inputs": _candidate_pool_inputs(row),
        "strategy_input_provenance": _strategy_input_provenance(row, source=source),
        "field_sources": field_sources,
    }
    replay_context_ready = not blockers
    return {
        "replay_context_ready": replay_context_ready,
        "replay_context_blockers": blockers,
        "replay_context_source": source,
        "replay_context": replay_context,
        **field_sources,
    }


def _extract_field(row: Mapping[str, Any], field: str, source_keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in source_keys:
        value = _lookup_value(row, key)
        if value in (None, "", "None"):
            continue
        if field in {"snapshot_ts_utc", "feature_cutoff_ts", "signal_ts", "earliest_entry_ts"} and key.endswith("_epoch"):
            return _iso_utc_from_epoch(value), f"derived:{key}"
        if field == "is_oos":
            return _bool(value), f"preserved:{key}"
        if field == "strike":
            return _number(value), f"preserved:{key}"
        if field == "quote_age_sec":
            return _number(value), f"preserved:{key}"
        if field in {"bid", "ask"}:
            return _number(value), f"preserved:{key}"
        if field in {"option_type", "oos_label", "oos_source", "partition_id", "split_name", "quote_source", "feed_truth_state", "feed_truth_reason_code", "regime", "regime_source"}:
            return _text(value), f"preserved:{key}"
        if field == "global_cue_state":
            return _global_cue_state(value), f"preserved:{key}"
        return value, f"preserved:{key}"
    return None, "missing"


def _lookup_value(row: Mapping[str, Any], key: str) -> Any:
    value = row.get(key)
    if value not in (None, "", "None"):
        return value
    for nested_key in ("top_reportable_executable_snapshot", "top_reportable_executable", "replay_context"):
        nested = row.get(nested_key)
        if isinstance(nested, Mapping):
            nested_value = nested.get(key)
            if nested_value not in (None, "", "None"):
                return nested_value
    return None


def _candidate_pool_inputs(row: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in _HANDOFF_COUNT_FIELDS:
        value = _lookup_value(row, key)
        if value in (None, "", "None"):
            continue
        payload[key] = _number(value)
    return payload


def _strategy_input_provenance(row: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    provenance = {
        "source": source,
        "source_path": _text(row.get("source_path")),
        "journal_event": _text(row.get("journal_event")),
        "candidate_origin": _text(row.get("candidate_origin")),
        "candidate_class": _text(row.get("candidate_class")),
        "quote_source": _text(row.get("quote_source")),
        "feed_truth_state": _text(row.get("feed_truth_state")),
        "regime": _text(row.get("regime")),
        "metadata_source": _text(metadata.get("source") if isinstance(metadata, Mapping) else None),
    }
    return {key: value for key, value in provenance.items() if value not in (None, "", "None")}


def _global_cue_state(value: Any) -> dict[str, Any] | str:
    if isinstance(value, Mapping):
        return dict(value)
    return _text(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return bool(value)


def _number(value: Any) -> int | float | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    return int(number) if number.is_integer() else number


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
