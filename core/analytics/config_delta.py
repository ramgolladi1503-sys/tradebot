from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .confidence import should_emit_suggestion


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _norm_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return token.upper() or "UNKNOWN"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write(path, json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True) + "\n")


def _finalize_scope(requested_scope: str, *, window_days: int, sessions: int) -> str:
    scope = _text(requested_scope).upper() or "PAPER_ONLY"
    if scope == "LIVE" and not (window_days >= 5 and sessions >= 5):
        return "LIVE_CANDIDATE"
    if scope in {"PAPER_ONLY", "LIVE_CANDIDATE", "LIVE"}:
        return scope
    return "PAPER_ONLY"


def _base_proposal(
    *,
    proposal_id: str,
    area: str,
    key: str,
    proposed: Any,
    scope: str,
    window_days: int,
    sessions: int,
    sample_size: int,
    effect_size: float,
    baseline_hit_rate: float | None,
    gate_hit_rate: float | None,
    missed_winners: int,
    saved_from_sl: int,
    quality_risk: str,
    drawdown_risk: str,
    failure_modes: Sequence[str],
    notes: Sequence[str],
) -> dict[str, Any]:
    return {
        "id": proposal_id,
        "area": area,
        "change": {
            "key": key,
            "current": None,
            "proposed": proposed,
            "scope": _finalize_scope(scope, window_days=window_days, sessions=sessions),
        },
        "justification": {
            "sample_size": int(sample_size),
            "effect_size": float(effect_size),
            "sessions": int(sessions),
            "baseline_hit_rate": baseline_hit_rate,
            "gate_hit_rate": gate_hit_rate,
            "missed_winners": int(missed_winners),
            "saved_from_sl": int(saved_from_sl),
        },
        "risk": {
            "expected_trade_quality_risk": quality_risk,
            "expected_drawdown_risk": drawdown_risk,
            "failure_modes": list(failure_modes),
        },
        "rollout_plan": [
            "Apply in PAPER for 3 sessions.",
            "Verify hit rate and drawdown do not degrade beyond baseline tolerance.",
            "Only then consider LIVE_CANDIDATE or LIVE promotion via human review.",
        ],
        "rollback_plan": [
            "Revert key to previous value.",
            "Confirm rejection distribution and SL rate return to baseline.",
        ],
        "notes": "NO AUTO-APPLY. HUMAN REVIEW REQUIRED. Current value not found in analytics; confirm manually. "
        + " ".join(_text(item) for item in notes if _text(item)),
    }


def build_config_delta_proposal(report: dict) -> dict:
    day = _text((report or {}).get("day")) or "unknown-day"
    summary = dict((report or {}).get("summary") or {})
    metrics = dict((report or {}).get("metrics") or {})
    gates = dict(metrics.get("gates") or {})
    feed = dict(metrics.get("feed") or {})
    outcomes = dict(metrics.get("outcomes") or {})

    window_days = max(1, _safe_int(summary.get("window_days") or 1))
    sessions = max(0, _safe_int(summary.get("sessions_count") or 0))
    baseline_hit_rate = _safe_float(gates.get("baseline_hit_rate"))

    proposals: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []

    top_bad = list(gates.get("top_bad_gates") or [])
    if top_bad:
        gate = dict(top_bad[0] or {})
        gate_name = _text(gate.get("gate_reason")) or "unknown_gate"
        sample_size = _safe_int(gate.get("count"))
        effect_size = abs(_safe_float(gate.get("effect_size_vs_hit_baseline")))
        gate_hit_rate = _safe_float(gate.get("hit_rate"))
        missed_winners = _safe_int(gate.get("hits"))
        saved_from_sl = _safe_int(gate.get("sls"))
        if should_emit_suggestion(sample_size, effect_size, sessions):
            requested_scope = "LIVE" if effect_size >= 0.30 else "LIVE_CANDIDATE"
            proposals.append(
                _base_proposal(
                    proposal_id=f"gate_loosen_{_norm_token(gate_name)}",
                    area="gates",
                    key=f"GATE_{_norm_token(gate_name)}_THRESHOLD",
                    proposed="LOOSEN_10_PERCENT",
                    scope=requested_scope,
                    window_days=window_days,
                    sessions=sessions,
                    sample_size=sample_size,
                    effect_size=effect_size,
                    baseline_hit_rate=baseline_hit_rate,
                    gate_hit_rate=gate_hit_rate,
                    missed_winners=missed_winners,
                    saved_from_sl=saved_from_sl,
                    quality_risk="MEDIUM",
                    drawdown_risk="MEDIUM",
                    failure_modes=[
                        "Higher low-quality trade throughput if gate is too loose.",
                        "Regime drift may invalidate replay-derived edge quickly.",
                    ],
                    notes=[f"Derived from top bad gate {gate_name}."],
                )
            )
        else:
            blocked_reasons.append(
                f"Top bad gate {gate_name} failed confidence gate (sample={sample_size}, effect={effect_size:.3f}, sessions={sessions})."
            )

    top_protective = list(gates.get("top_protective_gates") or [])
    if top_protective:
        gate = dict(top_protective[0] or {})
        gate_name = _text(gate.get("gate_reason")) or "unknown_gate"
        sample_size = _safe_int(gate.get("count"))
        effect_size = abs(_safe_float(gate.get("effect_size_vs_sl_baseline")))
        gate_hit_rate = 1.0 - _safe_float(gate.get("sl_rate"))
        missed_winners = _safe_int(gate.get("hits"))
        saved_from_sl = _safe_int(gate.get("sls"))
        if should_emit_suggestion(sample_size, effect_size, sessions):
            proposals.append(
                _base_proposal(
                    proposal_id=f"gate_keep_or_tighten_{_norm_token(gate_name)}",
                    area="risk",
                    key=f"GATE_{_norm_token(gate_name)}_STRICTNESS",
                    proposed="TIGHTEN_5_PERCENT",
                    scope="PAPER_ONLY",
                    window_days=window_days,
                    sessions=sessions,
                    sample_size=sample_size,
                    effect_size=effect_size,
                    baseline_hit_rate=baseline_hit_rate,
                    gate_hit_rate=gate_hit_rate,
                    missed_winners=missed_winners,
                    saved_from_sl=saved_from_sl,
                    quality_risk="LOW",
                    drawdown_risk="LOW",
                    failure_modes=[
                        "Over-tightening may reduce participation in high-quality setups.",
                        "Protective signal could be non-stationary across regimes.",
                    ],
                    notes=[f"Protective gate signal strongest for {gate_name}; recommendation is conservative."],
                )
            )
        else:
            blocked_reasons.append(
                f"Top protective gate {gate_name} failed confidence gate (sample={sample_size}, effect={effect_size:.3f}, sessions={sessions})."
            )

    missed_feed = _safe_int(feed.get("missed_edge_due_to_feed"))
    missed_other = _safe_int(feed.get("missed_edge_due_to_other"))
    feed_blocks = _safe_int(feed.get("feed_block_rejects"))
    feed_share = _safe_float(feed.get("feed_related_share_of_missed_edge"))
    feed_group_map = dict(feed.get("rejects_by_feed_group") or {})
    top_feed_group = "UNKNOWN"
    if feed_group_map:
        top_feed_group = sorted(feed_group_map.items(), key=lambda item: (-_safe_int(item[1]), str(item[0])))[0][0]

    dominates = (missed_feed > missed_other and missed_feed > 0) or (feed_share >= 0.50 and missed_feed > 0)
    if dominates:
        sample_size = max(feed_blocks, missed_feed)
        effect_size = feed_share
        if should_emit_suggestion(sample_size, effect_size, sessions):
            proposals.append(
                _base_proposal(
                    proposal_id=f"feed_stability_{_norm_token(top_feed_group)}",
                    area="feed",
                    key="DEPTH_REBALANCE_COOLDOWN_SEC",
                    proposed="INCREASE_BY_15_PERCENT",
                    scope="PAPER_ONLY",
                    window_days=window_days,
                    sessions=sessions,
                    sample_size=sample_size,
                    effect_size=effect_size,
                    baseline_hit_rate=baseline_hit_rate,
                    gate_hit_rate=None,
                    missed_winners=missed_feed,
                    saved_from_sl=_safe_int(outcomes.get("saved_count")),
                    quality_risk="LOW",
                    drawdown_risk="MEDIUM",
                    failure_modes=[
                        "Longer cooldown can delay adaptation after genuine regime shifts.",
                        "May reduce breadth of option depth coverage if not paired with budget checks.",
                    ],
                    notes=[f"Feed-related missed winners concentrated in {top_feed_group}."],
                )
            )
        else:
            blocked_reasons.append(
                f"Feed proposal failed confidence gate (sample={sample_size}, effect={effect_size:.3f}, sessions={sessions})."
            )
    else:
        blocked_reasons.append("Feed-related missed edge did not dominate other gates.")

    if not proposals:
        if not blocked_reasons:
            blocked_reasons.append("No eligible candidate gates were available.")
        no_proposal_reason = "NO PROPOSAL: " + " ".join(blocked_reasons)
    else:
        no_proposal_reason = None

    return {
        "day": day,
        "window_days": window_days,
        "proposals": proposals,
        "no_proposal_reason": no_proposal_reason,
    }


def render_config_delta_md(proposal: dict) -> str:
    day = _text((proposal or {}).get("day")) or "unknown-day"
    window_days = _safe_int((proposal or {}).get("window_days") or 1)
    rows = list((proposal or {}).get("proposals") or [])
    no_proposal_reason = _text((proposal or {}).get("no_proposal_reason"))

    lines: list[str] = []
    lines.append(f"# Config Delta Proposal - {day}")
    lines.append("")
    lines.append(f"- Window days: {window_days}")
    lines.append("- Informational only: NO AUTO-APPLY. HUMAN REVIEW REQUIRED.")
    lines.append("")

    if not rows:
        lines.append("## Proposals")
        lines.append("- NO PROPOSAL")
        if no_proposal_reason:
            lines.append(f"- Reason: {no_proposal_reason}")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Proposals")
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            continue
        change = dict(row.get("change") or {})
        just = dict(row.get("justification") or {})
        risk = dict(row.get("risk") or {})
        lines.append(f"{idx}. **{_text(row.get('id'))}** ({_text(row.get('area'))})")
        lines.append(f"   - key: {_text(change.get('key'))}")
        lines.append(f"   - current: {_text(change.get('current')) or 'null'}")
        lines.append(f"   - proposed: {_text(change.get('proposed'))}")
        lines.append(f"   - scope: {_text(change.get('scope'))}")
        lines.append(
            "   - evidence: "
            f"sample_size={_safe_int(just.get('sample_size'))}, "
            f"effect_size={_safe_float(just.get('effect_size')):.3f}, "
            f"sessions={_safe_int(just.get('sessions'))}, "
            f"baseline_hit_rate={_safe_float(just.get('baseline_hit_rate')):.3f}, "
            f"gate_hit_rate={_safe_float(just.get('gate_hit_rate')):.3f}, "
            f"missed_winners={_safe_int(just.get('missed_winners'))}, "
            f"saved_from_sl={_safe_int(just.get('saved_from_sl'))}"
        )
        lines.append(
            "   - risk: "
            f"trade_quality={_text(risk.get('expected_trade_quality_risk'))}, "
            f"drawdown={_text(risk.get('expected_drawdown_risk'))}"
        )
        failure_modes = list(risk.get("failure_modes") or [])
        if failure_modes:
            lines.append(f"   - failure_modes: {failure_modes}")
        lines.append(f"   - rollout_plan: {list(row.get('rollout_plan') or [])}")
        lines.append(f"   - rollback_plan: {list(row.get('rollback_plan') or [])}")
        lines.append(f"   - notes: {_text(row.get('notes'))}")
    lines.append("")
    return "\n".join(lines)


def write_config_delta(proposal: dict, out_dir: Path) -> tuple[Path, Path]:
    day = _text((proposal or {}).get("day"))
    if not day:
        raise ValueError("proposal.day is required")
    base = Path(out_dir) / day
    md_path = base / "config_delta_proposal.md"
    json_path = base / "config_delta_proposal.json"
    _atomic_write(md_path, render_config_delta_md(proposal))
    _atomic_write_json(json_path, proposal)
    return md_path, json_path
