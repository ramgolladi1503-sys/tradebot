#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.candidate_finalization import mirror_candidate_truth
from core.candidate_pool import build_candidate_pool
from core.capital_allocator import allocate_capital_slots
from core.fallback_lineage import stamp_fallback_lineage
from core.guarded_review import enforce_review_data_truth
from core.guarded_risk_engine import evaluate_candidate_risk_guarded


DEFAULT_INPUTS = [
    "tests/fixtures/candidates_truth_sample.json",
    "logs/review_queue.json",
    "logs/quick_review_queue.json",
    "logs/approved_trades.json",
    "runtime/review_queue.json",
    "runtime/quick_review_queue.json",
]


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _extract_candidates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in (
            "candidates",
            "trades",
            "items",
            "rows",
            "review_queue",
            "approved_trades",
            "top_executable_candidates",
            "near_executable_candidates",
            "advisory_candidates",
            "rejected_candidates",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        if any(key in payload for key in ("trade_id", "symbol", "candidate_id", "tradingsymbol")):
            return [dict(payload)]
    return []


def _candidate_ref(candidate: dict[str, Any], index: int) -> str:
    return str(
        candidate.get("trade_id")
        or candidate.get("candidate_id")
        or candidate.get("trade_key")
        or candidate.get("instrument_id")
        or candidate.get("tradingsymbol")
        or candidate.get("symbol")
        or f"candidate-{index}"
    )


def _default_portfolio() -> dict[str, Any]:
    return {
        "capital": 100000.0,
        "risk_per_trade_pct": 0.004,
        "open_risk_pct": 0.0,
        "directional_heat": {},
        "family_exposure": {},
        "daily_kill_switch_active": False,
    }


def _prepare_for_risk(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    entry = out.get("execution_entry") or out.get("entry_price") or out.get("display_entry") or out.get("opt_ltp") or out.get("current_ltp")
    try:
        entry_float = float(entry)
    except Exception:
        entry_float = 100.0
    out.setdefault("execution_entry", entry_float)
    out.setdefault("entry_price", entry_float)
    out.setdefault("stop_loss", max(0.05, entry_float * 0.90))
    out.setdefault("target", entry_float * 1.20)
    out.setdefault("strategy_family", out.get("strategy") or "offline_fixture")
    out.setdefault("direction_family", "bullish")
    out.setdefault("symbol", out.get("underlying") or "UNKNOWN")
    return out


def run_offline_pipeline(candidates: list[dict[str, Any]], *, portfolio_state: dict[str, Any] | None = None) -> dict[str, Any]:
    portfolio = dict(portfolio_state or _default_portfolio())
    stages: list[dict[str, Any]] = []
    processed: list[dict[str, Any]] = []

    for index, raw in enumerate(candidates):
        ref = _candidate_ref(raw, index)
        lineage = stamp_fallback_lineage(raw)
        pooled = build_candidate_pool([lineage]).candidates[0]
        reviewed = enforce_review_data_truth(pooled)
        finalized = mirror_candidate_truth(reviewed)
        risk_input = _prepare_for_risk(finalized)
        risk = evaluate_candidate_risk_guarded(risk_input, portfolio_state=portfolio)
        risk_dict = risk.to_dict()
        candidate_for_allocation = dict(risk_input)
        candidate_for_allocation.update(
            {
                "risk_budget_ok": risk.risk_budget_ok,
                "risk_budget_reason": risk.risk_budget_reason,
                "selected_for_execution": bool(
                    risk.risk_budget_ok
                    and candidate_for_allocation.get("execution_truth_allowed")
                    and candidate_for_allocation.get("selected_for_execution", False)
                ),
                "capital_at_risk": candidate_for_allocation.get("capital_at_risk") or candidate_for_allocation.get("execution_entry") or 0.0,
                "tradable": bool(risk.risk_budget_ok and candidate_for_allocation.get("execution_truth_allowed")),
            }
        )
        allocated = allocate_capital_slots(
            [candidate_for_allocation],
            max_slots=1,
            per_symbol_cap=1,
            per_theme_cap=1,
            capital_budget_cap=100000.0,
            minimum_quality_threshold=0.0,
            replacement_enabled=False,
            replacement_min_delta=0.0,
        )[0]
        stage = {
            "ref": ref,
            "symbol": allocated.get("symbol"),
            "candidate_pool_lifecycle": pooled.get("candidate_lifecycle"),
            "review_permission": reviewed.get("permission"),
            "review_final_action": reviewed.get("final_action"),
            "finalized_candidate_status": finalized.get("candidate_status"),
            "data_quality_grade": finalized.get("data_quality_grade"),
            "execution_truth_allowed": finalized.get("execution_truth_allowed"),
            "execution_truth_blockers": finalized.get("execution_truth_blockers") or [],
            "fallback_fields": finalized.get("fallback_fields") or [],
            "risk_budget_ok": risk.risk_budget_ok,
            "risk_budget_reason": risk.risk_budget_reason,
            "risk_rejection_bucket": risk.rejection_bucket,
            "allocation_reason": allocated.get("allocation_reason"),
            "capital_assigned": allocated.get("capital_assigned"),
            "selected_for_execution_final": allocated.get("selected_for_execution"),
            "pipeline_passed": bool(
                allocated.get("execution_truth_allowed")
                and risk.risk_budget_ok
                and allocated.get("capital_assigned", 0) > 0
                and allocated.get("selected_for_execution")
            ),
            "risk": risk_dict,
        }
        stages.append(stage)
        processed.append(allocated)

    summary = {
        "mode": "OFFLINE_ELITE_PIPELINE_VALIDATION",
        "behavior_changed_live": False,
        "total_candidates": len(candidates),
        "pipeline_passed": sum(1 for row in stages if row["pipeline_passed"]),
        "data_truth_blocked": sum(1 for row in stages if not row["execution_truth_allowed"]),
        "risk_blocked": sum(1 for row in stages if not row["risk_budget_ok"]),
        "capital_allocated": sum(1 for row in stages if float(row.get("capital_assigned") or 0.0) > 0.0),
        "dirty_capital_violations": sum(
            1
            for row in stages
            if (not row["execution_truth_allowed"]) and float(row.get("capital_assigned") or 0.0) > 0.0
        ),
    }
    return {"summary": summary, "stages": stages, "processed_candidates": processed}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Offline Elite Pipeline Validation Report")
    lines.append("")
    lines.append("This is offline-only. It does not connect to broker, place orders, modify queues, or change live runtime state.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for key, value in payload["summary"].items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## Candidate Stages")
    lines.append("")
    for row in payload["stages"]:
        blockers = ", ".join(row.get("execution_truth_blockers") or []) or "none"
        lines.append(
            f"- `{row['ref']}` symbol={row.get('symbol')} grade={row.get('data_quality_grade')} "
            f"pool={row.get('candidate_pool_lifecycle')} review={row.get('review_final_action')} "
            f"risk={row.get('risk_budget_reason')} allocation={row.get('allocation_reason')} "
            f"capital={row.get('capital_assigned')} blockers={blockers}"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_inputs(args: argparse.Namespace) -> list[Path]:
    raw_inputs = args.inputs if args.inputs else DEFAULT_INPUTS
    return [Path(item) for item in raw_inputs]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline elite end-to-end pipeline validator")
    parser.add_argument("--inputs", nargs="*", default=None, help="Input candidate JSON files")
    parser.add_argument("--out-json", default="logs/offline_elite_pipeline_report.json")
    parser.add_argument("--out-md", default="logs/offline_elite_pipeline_report.md")
    parser.add_argument("--fail-on-dirty-capital", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidates: list[dict[str, Any]] = []
    loaded_sources: list[dict[str, Any]] = []
    for path in _resolve_inputs(args):
        if not path.exists():
            loaded_sources.append({"path": str(path), "exists": False, "candidate_count": 0})
            continue
        extracted = _extract_candidates(_load_json(path))
        loaded_sources.append({"path": str(path), "exists": True, "candidate_count": len(extracted)})
        candidates.extend(extracted)
    payload = run_offline_pipeline(candidates)
    payload["loaded_sources"] = loaded_sources
    _write_json(Path(args.out_json), payload)
    _write_markdown(Path(args.out_md), payload)
    if args.print_summary:
        print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    dirty_capital = int(payload["summary"].get("dirty_capital_violations", 0) or 0)
    return 1 if args.fail_on_dirty_capital and dirty_capital > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
