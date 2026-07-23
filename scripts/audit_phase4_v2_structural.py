#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PASSED_STATUS = "PASSED"
REJECTED_STATUS = "REJECTED"


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def audit_v2_structure(
    trades: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    blockers: set[str] = set()

    if not candidates:
        blockers.add("CANDIDATE_LEDGER_MISSING_OR_EMPTY")
    else:
        base_required = {
            "signal_time",
            "symbol",
            "setup_type",
            "wick_ratio",
            "or_high",
            "or_low",
            "signal_close",
            "status",
        }
        next_open_required = {
            "entry_eval_time",
            "entry_open",
            "stop_loss",
            "target",
            "planned_target_distance",
            "proxy_option_expected_move",
            "cost_hurdle_margin",
        }
        for candidate in candidates:
            if not base_required.issubset(candidate):
                blockers.add("CANDIDATE_LEDGER_FIELDS_MISSING")
                continue
            status = str(candidate.get("status") or "").upper()
            if status == REJECTED_STATUS:
                if not candidate.get("reject_reason"):
                    blockers.add("REJECTED_CANDIDATE_REASON_MISSING")
            elif status == PASSED_STATUS:
                if not next_open_required.issubset(candidate):
                    blockers.add("PASSED_CANDIDATE_NEXT_OPEN_FIELDS_MISSING")
            else:
                blockers.add("CANDIDATE_STATUS_INVALID")
            if candidate.get("reject_reason") != "WICK_TOO_WEAK" and (
                "htf_regime" not in candidate
            ):
                blockers.add("CANDIDATE_HTF_REGIME_MISSING")

    if not trades:
        blockers.add("V2_LEDGER_MISSING_OR_EMPTY")
    for trade in trades:
        required_trade_fields = {
            "v2_signal_version",
            "setup_type",
            "failed_level",
            "rejection_quality",
            "htf_regime",
            "signal_time",
            "entry_time",
            "entry_delay_bars",
            "next_open_recalculated",
            "planned_target_distance",
            "entry_price",
            "stop_loss",
            "target",
            "cost_hurdle_margin",
            "pnl_model",
        }
        if not required_trade_fields.issubset(trade):
            blockers.add("LEDGER_SCHEMA_REQUIRED_FIELD_MISSING")
            continue
        if trade["v2_signal_version"] != "1.0":
            blockers.add("V2_NOT_STRUCTURAL_REDESIGN_FAILED")
        signal_time = _parse_timestamp(trade["signal_time"])
        entry_time = _parse_timestamp(trade["entry_time"])
        if signal_time is None or entry_time is None or signal_time >= entry_time:
            blockers.add("SAME_CANDLE_ENTRY_RISK")
        if int(trade["entry_delay_bars"]) != 1:
            blockers.add("NEXT_OPEN_ENTRY_DELAY_MISMATCH")
        if not bool(trade["next_open_recalculated"]):
            blockers.add("NEXT_OPEN_COST_HURDLE_NOT_RECALCULATED")
        if float(trade["planned_target_distance"]) <= 0:
            blockers.add("COST_HURDLE_TARGET_MISMATCH")
        entry = float(trade["entry_price"])
        stop = float(trade["stop_loss"])
        target = float(trade["target"])
        if entry == stop:
            blockers.add("ZERO_RISK_DISTANCE")
        else:
            realized_geometry_rr = abs(target - entry) / abs(stop - entry)
            if realized_geometry_rr < 1.4:
                blockers.add("NEXT_OPEN_RR_MISMATCH")
        if float(trade["cost_hurdle_margin"]) <= 0:
            blockers.add("COST_HURDLE_FILTER_FAILED")

    if not summary:
        blockers.add("TRADE_LEDGER_SUMMARY_MISSING")
    else:
        zero_trade_symbol_days = int(
            summary.get("zero_trade_metrics", {}).get(
                "zero_trade_symbol_days", 0
            )
        )
        if zero_trade_symbol_days == 0:
            blockers.add("ZERO_TRADE_SYMBOL_DAY_MISSING")
        cap_saturation = float(summary.get("cap_saturation_ratio", 1.0))
        if cap_saturation > 0.70:
            blockers.add("V2_CAP_SATURATION_FAILED")

    ordered = sorted(blockers)
    return {
        "classification": (
            "V2_STRUCTURAL_AUDIT_FAILED"
            if ordered
            else "V2_STRUCTURAL_AUDIT_PASSED"
        ),
        "blockers": ordered,
        "trade_count": len(trades),
        "candidate_count": len(candidates),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, default="MEAN_REVERSION_EXTENSION")
    args = parser.parse_args()

    base_dir = Path(f"runtime/strategy_validation/{args.strategy}")
    ledger_path = base_dir / "phase_4_trade_ledger.jsonl"
    candidates_path = base_dir / "phase_4_candidates.jsonl"
    summary_path = base_dir / "phase_4_trade_ledger_summary.json"

    def load_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text().splitlines()
            if line.strip()
        ]

    trades = load_jsonl(ledger_path)
    candidates = load_jsonl(candidates_path)
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    report = audit_v2_structure(trades, candidates, summary)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "phase_4_v2_structural_audit.json").write_text(
        json.dumps(report, indent=2)
    )
    print(f"Phase 4 V2 structural audit result: {report['classification']}")


if __name__ == "__main__":
    main()
