from __future__ import annotations
from core.paths import data_root, logs_dir

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from config import config as cfg
from core.decision_dag import (
    Decision,
    MarketSnapshot,
    NODE_N8_STRATEGY_SELECT,
    REASON_INDICATORS_MISSING,
)
from core.live_indicator_readiness import (
    build_live_indicator_readiness_report,
    write_indicator_missing_runtime_evidence,
    write_live_indicator_readiness_latest,
)
from core.time_utils import now_ist


def _indicator_missing_compat_path() -> Path:
    return data_root() / "logs" / "indicator_missing_runtime_latest.json"


def _blocked_candidates_path() -> Path:
    desk_log_dir = getattr(cfg, "DESK_LOG_DIR", None)
    if desk_log_dir:
        return Path(str(desk_log_dir)) / "blocked_candidates.jsonl"
    desk = getattr(cfg, "DESK_ID", "DEFAULT")
    return logs_dir() / f"desks/{desk}/blocked_candidates.jsonl"


def _is_potentially_eligible(candidate_summary: Mapping[str, Any]) -> bool:
    family = candidate_summary.get("family")
    allowed = candidate_summary.get("allowed")
    return bool(family) or bool(allowed)


def _has_indicator_missing_blocker(decision: Decision) -> bool:
    blockers = {str(item or "").strip().upper() for item in (decision.blockers or ())}
    return REASON_INDICATORS_MISSING in blockers


def _warmup_node_facts(explain: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    for row in explain or ():
        if not isinstance(row, Mapping):
            continue
        if str(row.get("node") or "") != "N3_WARMUP_DONE":
            continue
        facts = row.get("facts") or {}
        return facts if isinstance(facts, Mapping) else {}
    return {}


def _indicator_readiness_snapshot(snapshot: MarketSnapshot, explain: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw = dict(snapshot.raw_data or {}) if isinstance(snapshot.raw_data, Mapping) else {}
    warmup_facts = dict(_warmup_node_facts(explain))
    out = dict(raw)
    out.setdefault("symbol", snapshot.symbol)
    out.setdefault("ohlc_bars_count", snapshot.ohlc_bars_count)
    out.setdefault("warmup_min_bars", warmup_facts.get("min_bars"))
    out.setdefault("indicator_last_update_epoch", snapshot.indicator_last_update_epoch)
    out.setdefault("indicators_age_sec", snapshot.indicators_age_sec)
    out.setdefault("indicators_ok", snapshot.indicators_ok)
    out.setdefault("warmup_reasons", warmup_facts.get("warmup_reasons", raw.get("warmup_reasons", [])))
    out.setdefault("compute_indicators_error", raw.get("compute_indicators_error", ""))
    return out


def _maybe_write_indicator_missing_runtime_evidence(
    *,
    decision: Decision,
    explain: Sequence[Mapping[str, Any]],
    snapshot: MarketSnapshot,
) -> None:
    if not _has_indicator_missing_blocker(decision):
        return
    try:
        payload = _indicator_readiness_snapshot(snapshot, explain)
        warmup_min_bars = payload.get("warmup_min_bars")
        try:
            warmup_min_bars_int = int(warmup_min_bars)
        except (TypeError, ValueError):
            warmup_min_bars_int = int(getattr(cfg, "WARMUP_MIN_BARS", 50))
        report = build_live_indicator_readiness_report(
            [payload],
            now_epoch=float(snapshot.ts_epoch),
            warmup_min_bars=max(0, warmup_min_bars_int),
            source="decision_reject_indicator_readiness_v1",
        )
        # Always write the schema-v2 latest artifact when we have a concrete snapshot.
        write_live_indicator_readiness_latest(report, now_epoch=float(snapshot.ts_epoch))
        # Keep the legacy rejection diagnostic separate from the authoritative
        # readiness artifact.  Both writers previously targeted
        # live_indicator_readiness_latest.json, allowing a stale compatibility
        # label to overwrite current valid readiness truth.
        write_indicator_missing_runtime_evidence(
            report,
            path=_indicator_missing_compat_path(),
            now_epoch=float(snapshot.ts_epoch),
        )
    except Exception:
        return


def handle_post_decision_side_effects(
    decision: Decision,
    explain: Sequence[Mapping[str, Any]],
    snapshot: MarketSnapshot,
) -> None:
    """
    Handle post-decision side effects only from already-computed DAG outputs.
    This function must not recompute gate logic.
    """
    if decision.allowed:
        return

    _maybe_write_indicator_missing_runtime_evidence(
        decision=decision,
        explain=explain,
        snapshot=snapshot,
    )

    n8_row = None
    for row in explain:
        if str(row.get("node") or "") == NODE_N8_STRATEGY_SELECT:
            n8_row = row
            break
    if not isinstance(n8_row, Mapping):
        return

    n8_facts = n8_row.get("facts") or {}
    if not isinstance(n8_facts, Mapping):
        return
    candidate_summary = n8_facts.get("candidate_summary") or {}
    if not isinstance(candidate_summary, Mapping):
        return
    if not _is_potentially_eligible(candidate_summary):
        return

    precondition_failures = n8_facts.get("precondition_failures") or []
    failure_nodes = set()
    if isinstance(precondition_failures, Sequence) and not isinstance(precondition_failures, (str, bytes, bytearray)):
        for node in precondition_failures:
            node_s = str(node or "").strip()
            if node_s:
                failure_nodes.add(node_s)

    explain_snippet = []
    for row in explain:
        if not isinstance(row, Mapping):
            continue
        node = str(row.get("node") or "")
        if failure_nodes and node not in failure_nodes:
            continue
        if (not failure_nodes) and bool(row.get("ok", True)):
            continue
        reasons = row.get("reasons") or []
        if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes, bytearray)):
            reasons = []
        explain_snippet.append(
            {
                "node": node,
                "ok": bool(row.get("ok", False)),
                "reasons": [str(r) for r in reasons if str(r).strip()],
            }
        )

    blockers = [str(x) for x in (decision.blockers or ()) if str(x).strip()]
    primary_blocker = str(decision.primary_blocker or (blockers[0] if blockers else "UNKNOWN_BLOCKER"))
    record = {
        "ts_ist": now_ist().isoformat(),
        "ts_epoch": float(snapshot.ts_epoch),
        "symbol": snapshot.symbol,
        "stage": "decision_dag",
        "reason_code": primary_blocker,
        "reason": primary_blocker,
        "reason_text": "strategy_candidate_blocked_by_preconditions",
        "candidate_summary": dict(candidate_summary),
        "primary_blocker": primary_blocker,
        "blockers": blockers,
        "node_explain_snippet": explain_snippet,
    }

    try:
        path = _blocked_candidates_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        return
