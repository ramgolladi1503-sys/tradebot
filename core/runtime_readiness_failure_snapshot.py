from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from core.events import write_json_atomic
from core.offline_family_learning import family_outcome_records_path
from core.paths import ensure_dir, logs_dir, reports_dir

SNAPSHOT_VERSION = 1
_BLOCKER_PATTERNS: tuple[str, ...] = (
    "latency_guard_halt_all",
    "latency_breach",
    "AUTH_REQUIRED",
    "feed_ok=false",
    "PHASE2: No input candidates",
    "PHASE2: No valid candidates",
    "PRICE_MISMATCH",
    "risk_budget_missing_stop_distance",
    "risk_budget_stop_distance_too_wide_pct",
    "far_from_invalidation",
    "SYNTHETIC_SKIPPED_FROM_EXECUTION",
)


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"_unreadable": True, "path": str(target)}
    return payload if isinstance(payload, dict) else {"_non_object_json": True, "value": payload}


def _read_lines(path: str | Path | None, *, max_lines: int = 500) -> list[str]:
    if path is None:
        return []
    target = Path(path).expanduser()
    if not target.exists():
        return []
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    return lines[-max_lines:]


def _latest_paper_log(base_logs_dir: str | Path | None = None) -> Path | None:
    base = Path(base_logs_dir).expanduser() if base_logs_dir is not None else logs_dir()
    try:
        candidates = sorted(base.glob("paper_market_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return None
    return candidates[0] if candidates else None


def _family_outcome_line_count(path: str | Path | None) -> int:
    target = Path(path).expanduser() if path is not None else family_outcome_records_path()
    if not target.exists():
        return 0
    try:
        return sum(1 for line in target.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
    except Exception:
        return 0


def _pattern_counts(lines: Iterable[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in lines:
        for pattern in _BLOCKER_PATTERNS:
            if pattern in line:
                counts[pattern] += 1
    return dict(sorted(counts.items()))


def _json_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _primary_blocker(
    *,
    engine_status: dict[str, Any],
    runtime_health: dict[str, Any],
    feed_runtime: dict[str, Any],
    blocker_counts: dict[str, int],
    family_outcome_count: int,
) -> str:
    if family_outcome_count > 0:
        return "paper_outcomes_available"
    auth_state = str(_json_value(engine_status, "auth_state") or _json_value(runtime_health, "auth_state") or "")
    if auth_state.upper() == "AUTH_REQUIRED":
        return "auth_required"
    feed_ok = _json_value(engine_status, "feed_ok")
    if feed_ok is False:
        return "feed_not_ok"
    if blocker_counts.get("latency_guard_halt_all", 0) > 0:
        return "latency_guard_halt_all"
    if blocker_counts.get("latency_breach", 0) > 0:
        return "latency_breach"
    if blocker_counts.get("PHASE2: No input candidates", 0) > 0:
        return "no_phase2_input_candidates"
    if blocker_counts.get("PHASE2: No valid candidates", 0) > 0:
        return "no_valid_candidates_after_filtering"
    feed_connected = _json_value(feed_runtime, "ws_connected", "feed_ok")
    if feed_connected is False:
        return "feed_disconnected"
    return str(_json_value(engine_status, "primary_blocker") or "unknown")


def build_runtime_readiness_failure_snapshot(
    *,
    runtime_health_path: str | Path | None = None,
    feed_runtime_path: str | Path | None = None,
    engine_status_path: str | Path | None = None,
    family_outcomes_path: str | Path | None = None,
    paper_log_path: str | Path | None = None,
    base_logs_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a read-only explanation for a PAPER session with no edge evidence."""

    runtime_health_target = Path(runtime_health_path).expanduser() if runtime_health_path is not None else logs_dir() / "runtime_health_latest.json"
    feed_runtime_target = Path(feed_runtime_path).expanduser() if feed_runtime_path is not None else logs_dir() / "feed_runtime_latest.json"
    engine_status_target = Path(engine_status_path).expanduser() if engine_status_path is not None else logs_dir() / "engine_cycle_status.json"
    family_target = Path(family_outcomes_path).expanduser() if family_outcomes_path is not None else family_outcome_records_path()
    log_target = Path(paper_log_path).expanduser() if paper_log_path is not None else _latest_paper_log(base_logs_dir)

    runtime_health = _read_json(runtime_health_target)
    feed_runtime = _read_json(feed_runtime_target)
    engine_status = _read_json(engine_status_target)
    log_lines = _read_lines(log_target)
    blocker_counts = _pattern_counts(log_lines)
    family_count = _family_outcome_line_count(family_target)
    primary = _primary_blocker(
        engine_status=engine_status,
        runtime_health=runtime_health,
        feed_runtime=feed_runtime,
        blocker_counts=blocker_counts,
        family_outcome_count=family_count,
    )

    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": str(_json_value(engine_status, "mode") or _json_value(runtime_health, "mode") or "unknown"),
        "read_only": True,
        "source": {
            "runtime_health_path": str(runtime_health_target),
            "feed_runtime_path": str(feed_runtime_target),
            "engine_status_path": str(engine_status_target),
            "family_outcomes_path": str(family_target),
            "paper_log_path": str(log_target) if log_target is not None else None,
        },
        "evidence_status": {
            "family_outcomes_exists": family_target.exists(),
            "family_outcome_records": family_count,
            "edge_evidence_available": family_count > 0,
            "paper_log_available": log_target is not None and log_target.exists(),
        },
        "runtime_status": {
            "auth_ok": _json_value(engine_status, "auth_ok") if "auth_ok" in engine_status else _json_value(runtime_health, "auth_ok"),
            "auth_state": _json_value(engine_status, "auth_state") or _json_value(runtime_health, "auth_state"),
            "feed_ok": _json_value(engine_status, "feed_ok") if "feed_ok" in engine_status else _json_value(feed_runtime, "feed_ok"),
            "market_open": _json_value(engine_status, "market_open") if "market_open" in engine_status else _json_value(runtime_health, "market_open"),
            "primary_blocker": primary,
            "engine_primary_blocker": _json_value(engine_status, "primary_blocker"),
            "visible_executable_count": _json_value(engine_status, "visible_executable_count"),
            "visible_queue_only_count": _json_value(engine_status, "visible_queue_only_count"),
            "visible_advisory_count": _json_value(engine_status, "visible_advisory_count"),
            "subscribed_option_tokens_count": _json_value(feed_runtime, "subscribed_option_tokens_count", "subscribed_tokens_count"),
            "ws_connected": _json_value(feed_runtime, "ws_connected"),
        },
        "blocker_counts": blocker_counts,
        "latest_log_excerpt": log_lines[-80:],
        "decision": {
            "safe_to_claim_edge": family_count > 0,
            "should_restart_without_fix": False if primary in {"latency_guard_halt_all", "latency_breach", "feed_not_ok", "auth_required"} else None,
            "recommended_next_action": _recommended_next_action(primary, family_count),
        },
    }


def _recommended_next_action(primary_blocker: str, family_outcome_count: int) -> str:
    if family_outcome_count > 0:
        return "run_edge_baseline_audit"
    if primary_blocker in {"latency_guard_halt_all", "latency_breach"}:
        return "capture_latency_feed_diagnostics_before_next_paper_run"
    if primary_blocker == "auth_required":
        return "refresh_and_validate_auth_before_restart"
    if primary_blocker in {"feed_not_ok", "feed_disconnected"}:
        return "fix_feed_connection_before_restart"
    if primary_blocker in {"no_phase2_input_candidates", "no_valid_candidates_after_filtering"}:
        return "inspect_candidate_generation_and_gate_rejections_without_lowering_thresholds"
    return "inspect_runtime_health_and_latest_paper_log"


def runtime_readiness_failure_report_path() -> Path:
    return ensure_dir(reports_dir()) / "runtime_readiness_failure_snapshot.json"


def save_runtime_readiness_failure_snapshot(report: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path is not None else runtime_readiness_failure_report_path()
    return write_json_atomic(target, json.loads(json.dumps(dict(report or {}), ensure_ascii=True, default=str)))
