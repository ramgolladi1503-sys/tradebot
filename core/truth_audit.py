from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from core.truth_quality import derive_truth_quality, TRUTH_REAL, TRUTH_DEGRADED, TRUTH_FALLBACK, TRUTH_SYNTHETIC


def _get(candidate: Any, key: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _score(candidate: Any) -> float:
    for key in ("final_rank_score", "final_score", "rank_score", "confidence_final", "confidence"):
        try:
            value = _get(candidate, key)
            if value not in (None, "", "None"):
                return float(value)
        except Exception:
            continue
    return 0.0


def _blocker(candidate: Any) -> str:
    for key in ("truth_block_reason", "primary_blocker", "final_blocker", "permission_reason", "execution_block_reason", "reason"):
        text = str(_get(candidate, key, "") or "").strip()
        if text:
            return text
    for key in ("hard_blockers", "blockers", "gate_reasons", "warnings"):
        values = list(_get(candidate, key, []) or [])
        if values:
            return str(values[0])
    return "none"


def audit_candidates(candidates: Iterable[Any], *, top_n: int = 10) -> dict[str, Any]:
    rows = list(candidates or [])
    truth_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    scored_rows: list[dict[str, Any]] = []

    for candidate in rows:
        truth_quality = derive_truth_quality(candidate)
        truth_counts[truth_quality] += 1
        action = str(_get(candidate, "final_action", _get(candidate, "permission", "UNKNOWN")) or "UNKNOWN").strip().upper()
        status = str(_get(candidate, "execution_status", "") or "").strip().lower()
        action_counts[action or status or "UNKNOWN"] += 1
        blocker = _blocker(candidate)
        if blocker and blocker != "none":
            blocker_counts[blocker] += 1
        scored_rows.append({
            "trade_id": _get(candidate, "trade_id"),
            "symbol": _get(candidate, "symbol"),
            "score": round(_score(candidate), 6),
            "truth_quality": truth_quality,
            "final_action": action,
            "execution_status": status,
            "blocker": blocker,
        })

    scored_rows.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    executable_count = sum(1 for row in scored_rows if row.get("final_action") == "EXECUTE" or row.get("execution_status") == "executable")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_candidates": len(rows),
        "real": int(truth_counts[TRUTH_REAL]),
        "degraded": int(truth_counts[TRUTH_DEGRADED]),
        "fallback": int(truth_counts[TRUTH_FALLBACK]),
        "synthetic": int(truth_counts[TRUTH_SYNTHETIC]),
        "unknown_truth": int(sum(v for k, v in truth_counts.items() if k not in {TRUTH_REAL, TRUTH_DEGRADED, TRUTH_FALLBACK, TRUTH_SYNTHETIC})),
        "executable": int(executable_count),
        "blocked_or_advisory": int(max(0, len(rows) - executable_count)),
        "action_counts": dict(action_counts),
        "top_blockers": dict(blocker_counts.most_common(10)),
        "top_ranked_candidates": scored_rows[: max(0, int(top_n))],
    }


def write_truth_audit(candidates: Iterable[Any], path: str | Path, *, top_n: int = 10) -> dict[str, Any]:
    report = audit_candidates(candidates, top_n=top_n)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
