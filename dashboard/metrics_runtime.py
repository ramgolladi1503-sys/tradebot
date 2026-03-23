from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import config as cfg
from core.learning_paths import canonical_rejected_candidates_path, canonical_suggestions_log_path
from core.observability.pipeline import pipeline_funnel_path, trade_lifecycle_path
from core.paths import data_root, desk_logs_dir, logs_dir
from core.runtime_snapshot_store import TOP_OPPORTUNITIES_LATEST_PATH


_SCORE_FIELDS = (
    "opportunity_score",
    "gating_final_confidence",
    "confidence_final",
    "permission_confidence",
    "builder_confidence",
    "confidence",
)
_BLOCKER_FIELDS = (
    "hard_blockers",
    "blockers",
    "soft_penalties",
    "warnings",
    "high_execute_blockers",
)
_NON_EXECUTABLE_STATUSES = {
    "advisory_only",
    "queue_only",
    "blocked",
    "non_executable",
    "missing",
}
_EXECUTABLE_STATUSES = {"ready", "execute", "executable"}


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if number != number:
        return None
    return float(number)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return str(value).strip() in {"", "None", "nan", "NaN"}
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _parse_timestamp(value: Any) -> float | None:
    number = _safe_float(value)
    if number is not None:
        if number > 10_000_000_000:
            return float(number) / 1000.0
        if number > 0:
            return float(number)
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return float(parsed.timestamp())


def _cycle_label(row: dict[str, Any]) -> tuple[str, float]:
    cycle_id = str(row.get("cycle_id") or "").strip()
    ts_epoch = _parse_timestamp(row.get("ts_epoch") or row.get("timestamp") or row.get("ts")) or 0.0
    if cycle_id:
        return cycle_id, ts_epoch
    minute_bucket = int(max(0.0, ts_epoch) // 60) * 60
    if minute_bucket <= 0:
        return "unknown", 0.0
    label = datetime.fromtimestamp(float(minute_bucket), tz=timezone.utc).strftime("%H:%M:%S")
    return label, float(minute_bucket)


def _row_identity(row: dict[str, Any]) -> str:
    for field in ("trade_id", "advisory_id", "candidate_id", "trade_key", "tradingsymbol"):
        text = str(row.get(field) or "").strip()
        if text:
            return text
    ts_epoch = _parse_timestamp(row.get("ts_epoch") or row.get("timestamp")) or 0.0
    symbol = str(row.get("symbol") or "").strip().upper()
    strategy = str(row.get("strategy") or row.get("strategy_id") or "").strip().upper()
    return f"{symbol}|{strategy}|{int(ts_epoch)}"


def _normalize_codes(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    elif _is_missing(value):
        raw_items = []
    else:
        raw_items = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _read_structured_rows(path: Path, *, max_rows: int) -> list[dict[str, Any]]:
    raw = _read_text(path)
    if not raw:
        return []
    rows: list[dict[str, Any]] = []
    if raw.startswith("["):
        try:
            payload = json.loads(raw)
        except Exception:
            return []
        if isinstance(payload, list):
            rows = [row for row in payload if isinstance(row, dict)]
        return rows[-max(1, int(max_rows)) :]
    for line in raw.splitlines()[-max(1, int(max_rows)) :]:
        text = str(line or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_json_object(path: Path) -> dict[str, Any]:
    raw = _read_text(path)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_snapshot_rows(path: Path, *, payload_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    payload = _read_json_object(path)
    if not payload:
        return []
    envelope_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    if not isinstance(envelope_payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in payload_keys:
        value = envelope_payload.get(key)
        if not isinstance(value, list):
            continue
        rows.extend([row for row in value if isinstance(row, dict)])
    return rows


def resolve_runtime_metric_paths(*, desk_id: str | None = None) -> dict[str, Path]:
    resolved_desk = str(desk_id or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    desk_log_dir = desk_logs_dir(resolved_desk)
    return {
        "pipeline_funnel": pipeline_funnel_path(),
        "trade_lifecycle": trade_lifecycle_path(),
        "candidates_stream": desk_log_dir / "candidates.jsonl",
        "decisions_stream": desk_log_dir / "decisions.jsonl",
        "decision_scan_summary": logs_dir() / "decision_scan_summary.jsonl",
        "suggestions": canonical_suggestions_log_path(),
        "rejected_candidates": canonical_rejected_candidates_path(),
        "review_queue": logs_dir() / "review_queue.json",
        "top_opportunities": TOP_OPPORTUNITIES_LATEST_PATH,
        "runtime_root": data_root(),
    }


def _load_candidate_pool_by_cycle(
    candidate_rows: list[dict[str, Any]],
    scan_summary_rows: list[dict[str, Any]],
    *,
    cycle_limit: int,
) -> list[dict[str, Any]]:
    cycle_sets: dict[str, set[str]] = defaultdict(set)
    cycle_ts: dict[str, float] = {}
    for row in candidate_rows:
        cycle, ts_epoch = _cycle_label(row)
        cycle_sets[cycle].add(_row_identity(row))
        cycle_ts[cycle] = min(ts_epoch or cycle_ts.get(cycle, ts_epoch), cycle_ts.get(cycle, ts_epoch) or ts_epoch)
    if cycle_sets:
        rows = [
            {
                "cycle": cycle,
                "candidate_pool_size": len(ids),
                "ts_epoch": float(cycle_ts.get(cycle) or 0.0),
            }
            for cycle, ids in cycle_sets.items()
        ]
        rows.sort(key=lambda row: (float(row.get("ts_epoch") or 0.0), str(row.get("cycle") or "")))
        return rows[-max(1, int(cycle_limit)) :]

    bucket_counts: dict[tuple[int, str], int] = defaultdict(int)
    for row in scan_summary_rows:
        ts_epoch = _parse_timestamp(row.get("ts_epoch") or row.get("timestamp")) or 0.0
        minute_bucket = int(max(0.0, ts_epoch) // 60) * 60
        if minute_bucket <= 0:
            continue
        label = datetime.fromtimestamp(float(minute_bucket), tz=timezone.utc).strftime("%H:%M:%S")
        bucket_counts[(minute_bucket, label)] += _safe_int(row.get("total_candidates"), default=0)
    rows = [
        {
            "cycle": label,
            "candidate_pool_size": int(count),
            "ts_epoch": float(minute_bucket),
        }
        for (minute_bucket, label), count in bucket_counts.items()
    ]
    rows.sort(key=lambda row: (float(row.get("ts_epoch") or 0.0), str(row.get("cycle") or "")))
    return rows[-max(1, int(cycle_limit)) :]


def _count_top_strategy(candidate_rows: list[dict[str, Any]], lifecycle_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    strategy_counts: Counter[str] = Counter()
    for row in candidate_rows:
        strategy = str(row.get("strategy") or row.get("strategy_id") or "").strip()
        if strategy:
            strategy_counts[strategy] += 1
    if not strategy_counts:
        for row in lifecycle_rows:
            if str(row.get("stage") or "").strip().lower() != "candidate_generation":
                continue
            if str(row.get("status") or "").strip().lower() != "created":
                continue
            strategy = str(row.get("strategy") or "").strip()
            if strategy:
                strategy_counts[strategy] += 1
    if not strategy_counts:
        return None
    strategy, count = sorted(strategy_counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return {"strategy": strategy, "count": int(count)}


def _merge_surface_rows(source_rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rows in source_rows:
        for row in rows:
            identity = _row_identity(row)
            current = merged.get(identity)
            if current is None:
                merged[identity] = dict(row)
                continue
            for key, value in row.items():
                if key not in current or _is_missing(current.get(key)):
                    if not _is_missing(value):
                        current[key] = value
    return list(merged.values())


def _score_field_and_value(row: dict[str, Any]) -> tuple[str | None, float | None]:
    for field in _SCORE_FIELDS:
        value = _safe_float(row.get(field))
        if value is None:
            continue
        return field, value
    return None, None


def _score_bucket(score: float) -> str:
    bounded = max(0.0, min(1.0, float(score)))
    lower = min(0.8, float(int(bounded * 5.0)) * 0.2)
    upper = min(1.0, lower + 0.2)
    return f"{lower:.1f}-{upper:.1f}"


def _build_score_distribution(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bucket_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    for row in rows:
        field, value = _score_field_and_value(row)
        if field is None or value is None:
            continue
        bucket_counts[_score_bucket(value)] += 1
        field_counts[field] += 1
    bucket_rows = [{"bucket": bucket, "count": int(count)} for bucket, count in sorted(bucket_counts.items())]
    field_rows = [
        {"field": field, "count": int(count)}
        for field, count in sorted(field_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return bucket_rows, field_rows


def _collect_blockers(row: dict[str, Any]) -> list[str]:
    codes: set[str] = set()
    for field in _BLOCKER_FIELDS:
        for code in _normalize_codes(row.get(field)):
            codes.add(code)
    if not codes:
        for field in ("final_blocker", "entry_block_code"):
            for code in _normalize_codes(row.get(field)):
                codes.add(code)
    return sorted(codes)


def _build_blockers_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        for code in _collect_blockers(row):
            counts[code] += 1
    return [
        {"blocker": blocker, "count": int(count)}
        for blocker, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _build_rejection_reason_distribution(
    rejected_rows: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    if rejected_rows:
        for row in rejected_rows:
            reason = (
                str(
                    row.get("reject_reason")
                    or row.get("reason_code")
                    or row.get("entry_block_code")
                    or row.get("permission_reason")
                    or row.get("reason")
                    or ""
                ).strip()
            )
            if reason:
                counts[reason] += 1
    elif decision_rows:
        for row in decision_rows:
            event_type = str(row.get("event_type") or "").strip().lower()
            if event_type != "decision_blocked":
                continue
            blockers = _normalize_codes(row.get("blockers"))
            if blockers:
                for blocker in blockers:
                    counts[blocker] += 1
    else:
        for row in lifecycle_rows:
            if str(row.get("status") or "").strip().lower() not in {"blocked", "failed", "skipped"}:
                continue
            reason = str(row.get("reason") or "").strip()
            if reason:
                counts[reason] += 1
    return [
        {"reason": reason, "count": int(count)}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _is_executable_row(row: dict[str, Any]) -> bool:
    execution_status = str(row.get("execution_status") or "").strip().lower()
    readiness = str(row.get("readiness") or "").strip().lower()
    final_action = str(row.get("final_action") or "").strip().lower()
    return execution_status == "executable" or readiness == "ready" or final_action == "execute"


def _build_allocation_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = 0
    rejected = 0
    capital_assigned_total = 0.0
    reason_counts: Counter[str] = Counter()
    for row in rows:
        slot_id = row.get("slot_id")
        allocation_reason = str(row.get("allocation_reason") or "").strip()
        selected = bool(row.get("selected_for_execution", False))
        capital_assigned = _safe_float(row.get("capital_assigned"))
        if capital_assigned is not None:
            capital_assigned_total += float(capital_assigned)
        if slot_id not in (None, "", "None") or allocation_reason == "allocated" or selected:
            accepted += 1
            reason_counts[allocation_reason or "allocated"] += 1
            continue
        if allocation_reason:
            rejected += 1
            reason_counts[allocation_reason] += 1
    total = accepted + rejected
    return {
        "accepted_count": int(accepted),
        "rejected_count": int(rejected),
        "acceptance_rate": float(accepted) / float(total) if total > 0 else 0.0,
        "capital_assigned_total": round(capital_assigned_total, 6),
        "reason_distribution": [
            {"reason": reason, "count": int(count)}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _build_advisory_conversion_summary(
    lifecycle_rows: list[dict[str, Any]],
    surfaced_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    histories: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for row in lifecycle_rows:
        trade_id = str(row.get("trade_id") or "").strip()
        if not trade_id or trade_id == "UNKNOWN":
            continue
        stage = str(row.get("stage") or "").strip().lower()
        if stage not in {"readiness_gating", "execution_feasibility", "emission_projection"}:
            continue
        status = str(row.get("status") or "").strip().lower()
        ts_epoch = _parse_timestamp(row.get("timestamp")) or 0.0
        histories[trade_id].append((ts_epoch, status))
    advisory_population = 0
    converted = 0
    for trade_id, events in histories.items():
        del trade_id
        saw_advisory = False
        saw_conversion = False
        for _, status in sorted(events, key=lambda item: (item[0], item[1])):
            if status in _NON_EXECUTABLE_STATUSES:
                saw_advisory = True
                continue
            if saw_advisory and status in _EXECUTABLE_STATUSES:
                saw_conversion = True
        if saw_advisory:
            advisory_population += 1
        if saw_conversion:
            converted += 1
    if advisory_population > 0:
        return {
            "rate": float(converted) / float(advisory_population),
            "converted_count": int(converted),
            "advisory_population": int(advisory_population),
            "method": "lifecycle_transition",
        }
    advisory_rows = 0
    executable_rows = 0
    for row in surfaced_rows:
        if _is_executable_row(row):
            executable_rows += 1
        else:
            advisory_rows += 1
    total = advisory_rows + executable_rows
    return {
        "rate": float(executable_rows) / float(total) if total > 0 else 0.0,
        "converted_count": int(executable_rows),
        "advisory_population": int(total),
        "method": "surfaced_mix",
    }


def load_runtime_metrics(
    *,
    desk_id: str | None = None,
    max_rows: int | None = None,
    cycle_limit: int | None = None,
    paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    resolved_paths = {**resolve_runtime_metric_paths(desk_id=desk_id), **(paths or {})}
    max_rows_val = max(50, int(max_rows or getattr(cfg, "DASHBOARD_RUNTIME_METRICS_MAX_ROWS", 5000) or 5000))
    cycle_limit_val = max(1, int(cycle_limit or getattr(cfg, "DASHBOARD_RUNTIME_METRICS_CYCLE_LIMIT", 20) or 20))

    source_status: dict[str, dict[str, Any]] = {}
    notes: list[str] = []

    def _register(name: str, path: Path, row_count: int | None = None) -> None:
        source_status[name] = {
            "path": str(path),
            "exists": bool(path.exists()),
            "row_count": row_count,
        }
        if not path.exists():
            notes.append(f"missing:{name}")

    candidate_rows = _read_structured_rows(resolved_paths["candidates_stream"], max_rows=max_rows_val)
    _register("candidates_stream", resolved_paths["candidates_stream"], len(candidate_rows))
    decision_rows = _read_structured_rows(resolved_paths["decisions_stream"], max_rows=max_rows_val)
    _register("decisions_stream", resolved_paths["decisions_stream"], len(decision_rows))
    lifecycle_rows = _read_structured_rows(resolved_paths["trade_lifecycle"], max_rows=max_rows_val)
    _register("trade_lifecycle", resolved_paths["trade_lifecycle"], len(lifecycle_rows))
    rejected_rows = _read_structured_rows(resolved_paths["rejected_candidates"], max_rows=max_rows_val)
    _register("rejected_candidates", resolved_paths["rejected_candidates"], len(rejected_rows))
    suggestions_rows = _read_structured_rows(resolved_paths["suggestions"], max_rows=max_rows_val)
    _register("suggestions", resolved_paths["suggestions"], len(suggestions_rows))
    review_queue_rows = _read_structured_rows(resolved_paths["review_queue"], max_rows=max_rows_val)
    _register("review_queue", resolved_paths["review_queue"], len(review_queue_rows))
    scan_summary_rows = _read_structured_rows(resolved_paths["decision_scan_summary"], max_rows=max_rows_val)
    _register("decision_scan_summary", resolved_paths["decision_scan_summary"], len(scan_summary_rows))
    top_opportunity_rows = _read_snapshot_rows(
        resolved_paths["top_opportunities"],
        payload_keys=("top_executable_opportunities", "top_advisory_opportunities"),
    )
    _register("top_opportunities", resolved_paths["top_opportunities"], len(top_opportunity_rows))
    pipeline_funnel = _read_json_object(resolved_paths["pipeline_funnel"])
    _register("pipeline_funnel", resolved_paths["pipeline_funnel"], 1 if pipeline_funnel else 0)

    candidate_pool_by_cycle = _load_candidate_pool_by_cycle(
        candidate_rows,
        scan_summary_rows,
        cycle_limit=cycle_limit_val,
    )
    latest_candidate_pool = (
        int(candidate_pool_by_cycle[-1].get("candidate_pool_size") or 0) if candidate_pool_by_cycle else int(pipeline_funnel.get("candidates") or 0)
    )
    top_strategy = _count_top_strategy(candidate_rows, lifecycle_rows)
    ranked_candidate_count = len(
        {
            str(row.get("trade_id") or "").strip()
            for row in lifecycle_rows
            if str(row.get("stage") or "").strip().lower() == "scoring_ranking"
            and str(row.get("trade_id") or "").strip()
            and str(row.get("trade_id") or "").strip() != "UNKNOWN"
        }
    )
    surfaced_rows = _merge_surface_rows(
        [
            suggestions_rows,
            review_queue_rows,
            rejected_rows,
            top_opportunity_rows,
        ]
    )
    score_distribution, score_field_usage = _build_score_distribution(surfaced_rows)
    blockers_distribution = _build_blockers_distribution(surfaced_rows)
    rejection_reason_distribution = _build_rejection_reason_distribution(rejected_rows, decision_rows, lifecycle_rows)
    allocation_summary = _build_allocation_summary(surfaced_rows)
    conversion_summary = _build_advisory_conversion_summary(lifecycle_rows, surfaced_rows)

    if not surfaced_rows:
        notes.append("no_surface_rows")
    if not candidate_pool_by_cycle and not pipeline_funnel:
        notes.append("no_candidate_pool_history")

    summary = {
        "candidate_pool_latest": int(latest_candidate_pool),
        "ranked_candidate_count": int(ranked_candidate_count or pipeline_funnel.get("scored") or 0),
        "top_strategy_by_candidate_volume": top_strategy,
        "advisory_to_execution_conversion_rate": float(conversion_summary["rate"]),
        "advisory_conversion_numerator": int(conversion_summary["converted_count"]),
        "advisory_conversion_denominator": int(conversion_summary["advisory_population"]),
        "advisory_conversion_method": str(conversion_summary["method"]),
        "latest_pipeline_funnel": pipeline_funnel,
    }

    return {
        "summary": summary,
        "candidate_pool_by_cycle": candidate_pool_by_cycle,
        "rejection_reason_distribution": rejection_reason_distribution,
        "score_distribution": score_distribution,
        "score_field_usage": score_field_usage,
        "blockers_distribution": blockers_distribution,
        "allocation_summary": allocation_summary,
        "source_status": source_status,
        "notes": sorted(set(notes)),
    }
