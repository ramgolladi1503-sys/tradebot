#!/usr/bin/env python3
"""Predeclared friction sensitivity for the audited five-minute CE rebound edge.

Consumes only the independently reconstructed horizon ledger. No signal or
outcome selection is changed. The cost grid is a descriptive robustness audit
because the holdout was already opened by V3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

LEDGER_REL = Path(
    "runtime/research/late_day_ce_inventory_rebound_v4_horizon_audit/"
    "horizon_trade_ledger.csv"
)
HORIZON_AUDIT_REL = Path(
    "runtime/research/late_day_ce_inventory_rebound_v4_horizon_audit/"
    "independent_horizon_audit.json"
)
SIGNAL_ORACLE_REL = Path(
    "runtime/research/late_day_ce_inventory_rebound_v5_signal_oracle/"
    "signal_membership_oracle.json"
)
OUT_REL = Path(
    "runtime/research/late_day_ce_inventory_rebound_v7_friction_audit"
)
RESEARCH_REL = Path(
    "research/late_day_ce_inventory_rebound_v7_friction_audit"
)
COST_GRID_PCT = (0.10, 0.50, 1.00, 1.50, 2.00, 2.50, 3.00, 5.00)
REQUIRED_COST_PCT = 2.00


@dataclass(frozen=True)
class Metrics:
    trades: int
    profit_factor: float | None
    mean_return_pct: float | None
    median_return_pct: float | None
    win_rate: float | None
    net_return_pct_sum: float
    remove_top_two_profit_factor: float | None
    positive_folds: int
    total_folds: int
    largest_winner_share: float | None


def finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )


def profit_factor(values: Iterable[float]) -> float | None:
    clean = np.asarray(
        [float(value) for value in values if math.isfinite(float(value))],
        dtype=float,
    )
    if not len(clean):
        return None
    gross_profit = float(clean[clean > 0].sum())
    gross_loss = float(-clean[clean < 0].sum())
    if gross_loss > 0:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else None


def calculate_metrics(frame: pd.DataFrame, cost_pct: float) -> Metrics:
    if frame.empty:
        return Metrics(0, None, None, None, None, 0.0, None, 0, 0, None)
    values = finite(frame["gross_5m_pct"]).dropna().to_numpy(dtype=float)
    net = values - float(cost_pct)
    if not len(net):
        return Metrics(0, None, None, None, None, 0.0, None, 0, 0, None)
    ordered = np.sort(net)[::-1]
    trimmed = ordered[2:] if len(ordered) > 2 else np.asarray([], dtype=float)
    working = frame.loc[finite(frame["gross_5m_pct"]).notna()].copy()
    working["audited_net_return_pct"] = net
    fold_means = (
        working.groupby("fold_id", observed=True)["audited_net_return_pct"].mean()
        if "fold_id" in working.columns
        else pd.Series(dtype=float)
    )
    positive_total = float(ordered[ordered > 0].sum())
    largest_share = (
        float(max(ordered[0], 0.0) / positive_total)
        if positive_total > 0
        else None
    )
    return Metrics(
        trades=int(len(net)),
        profit_factor=profit_factor(net),
        mean_return_pct=float(net.mean()),
        median_return_pct=float(np.median(net)),
        win_rate=float(np.mean(net > 0)),
        net_return_pct_sum=float(net.sum()),
        remove_top_two_profit_factor=(
            profit_factor(trimmed) if len(trimmed) else None
        ),
        positive_folds=int((fold_means > 0).sum()),
        total_folds=int(len(fold_means)),
        largest_winner_share=largest_share,
    )


def oof_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 30
        and (metric.profit_factor or 0) >= 1.15
        and (metric.mean_return_pct or 0) > 0
        and (metric.median_return_pct or 0) > 0
        and (metric.remove_top_two_profit_factor or 0) >= 1.00
        and metric.total_folds == 4
        and metric.positive_folds >= 3
        and (
            metric.largest_winner_share is None
            or metric.largest_winner_share <= 0.30
        )
    )


def holdout_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 10
        and (metric.profit_factor or 0) >= 1.10
        and (metric.mean_return_pct or 0) > 0
        and (metric.median_return_pct or 0) > 0
        and (metric.remove_top_two_profit_factor or 0) >= 1.00
        and (
            metric.largest_winner_share is None
            or metric.largest_winner_share <= 0.40
        )
    )


def control_gate(
    primary: Metrics,
    mirror: Metrics,
    delayed: Metrics,
) -> bool:
    return bool(
        mirror.trades >= 10
        and (mirror.profit_factor or 0) < 1.00
        and (mirror.mean_return_pct or math.inf) < 0
        and (primary.mean_return_pct or -math.inf)
        > (mirror.mean_return_pct or math.inf)
        and delayed.trades >= 10
        and (delayed.profit_factor or 0) >= 1.00
        and (delayed.mean_return_pct or -math.inf) > 0
    )


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    ledger_path = root / LEDGER_REL
    horizon_path = root / HORIZON_AUDIT_REL
    oracle_path = root / SIGNAL_ORACLE_REL
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    ledger = pd.read_csv(ledger_path)
    horizon = json.loads(horizon_path.read_text(encoding="utf-8"))
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    if horizon.get("structural_edge_found_5m_candle_proxy") is not True:
        raise ValueError("V4 five-minute edge prerequisite did not pass")
    if oracle.get("exact_membership_match") is not True:
        raise ValueError("V5 signal membership prerequisite did not pass")

    roles = {
        "oof": ledger.loc[
            ledger["ledger_role"].eq("research_oof_primary")
        ].copy(),
        "holdout_primary": ledger.loc[
            ledger["ledger_role"].eq("holdout_primary")
        ].copy(),
        "holdout_mirror": ledger.loc[
            ledger["ledger_role"].eq("holdout_mirror_control")
        ].copy(),
        "holdout_delayed": ledger.loc[
            ledger["ledger_role"].eq("holdout_delayed_control")
        ].copy(),
    }
    scenarios: list[dict[str, Any]] = []
    for cost in COST_GRID_PCT:
        oof = calculate_metrics(roles["oof"], cost)
        primary = calculate_metrics(roles["holdout_primary"], cost)
        mirror = calculate_metrics(roles["holdout_mirror"], cost)
        delayed = calculate_metrics(roles["holdout_delayed"], cost)
        oof_pass = oof_gate(oof)
        holdout_pass = holdout_gate(primary)
        controls_pass = control_gate(primary, mirror, delayed)
        scenarios.append(
            {
                "total_friction_pct": cost,
                "oof": asdict(oof),
                "holdout_primary": asdict(primary),
                "holdout_mirror": asdict(mirror),
                "holdout_delayed": asdict(delayed),
                "oof_gate": oof_pass,
                "holdout_gate": holdout_pass,
                "control_gate": controls_pass,
                "combined_gate": bool(
                    oof_pass and holdout_pass and controls_pass
                ),
            }
        )

    required = next(
        item
        for item in scenarios
        if item["total_friction_pct"] == REQUIRED_COST_PCT
    )
    passing_costs = [
        float(item["total_friction_pct"])
        for item in scenarios
        if item["combined_gate"]
    ]
    maximum_tested_passing_cost = max(passing_costs) if passing_costs else None
    next_failed_cost = next(
        (
            float(item["total_friction_pct"])
            for item in scenarios
            if maximum_tested_passing_cost is not None
            and item["total_friction_pct"] > maximum_tested_passing_cost
            and not item["combined_gate"]
        ),
        None,
    )
    required_pass = bool(required["combined_gate"])
    verdict = (
        "PASS_LATE_DAY_CE_REBOUND_TWO_PERCENT_TOTAL_FRICTION_GATE"
        if required_pass
        else "FAIL_LATE_DAY_CE_REBOUND_TWO_PERCENT_TOTAL_FRICTION_GATE"
    )
    payload = {
        "principal_verdict": verdict,
        "required_total_friction_pct": REQUIRED_COST_PCT,
        "required_gate_pass": required_pass,
        "maximum_tested_passing_total_friction_pct": maximum_tested_passing_cost,
        "next_tested_failing_total_friction_pct": next_failed_cost,
        "scenarios": scenarios,
        "ledger_sha256": file_sha256(ledger_path),
        "horizon_audit_sha256": file_sha256(horizon_path),
        "signal_oracle_sha256": file_sha256(oracle_path),
        "holdout_status": "ALREADY_OPENED_DESCRIPTIVE_FRICTION_SENSITIVITY",
        "friction_interpretation": (
            "total_percentage_points_deducted_from_same_contract_premium_return"
        ),
        "authoritative_spread_or_slippage_model": False,
        "execution_certification": (
            "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING"
        ),
        "paper_or_live_authorized": False,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    payload["semantic_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    stable_json(out / "friction_sensitivity.json", payload)
    pd.DataFrame(
        [
            {
                "total_friction_pct": item["total_friction_pct"],
                "combined_gate": item["combined_gate"],
                "oof_pf": item["oof"]["profit_factor"],
                "oof_mean_pct": item["oof"]["mean_return_pct"],
                "oof_remove_top_two_pf": item["oof"][
                    "remove_top_two_profit_factor"
                ],
                "oof_positive_folds": item["oof"]["positive_folds"],
                "holdout_pf": item["holdout_primary"]["profit_factor"],
                "holdout_mean_pct": item["holdout_primary"][
                    "mean_return_pct"
                ],
                "holdout_remove_top_two_pf": item["holdout_primary"][
                    "remove_top_two_profit_factor"
                ],
                "mirror_pf": item["holdout_mirror"]["profit_factor"],
                "mirror_mean_pct": item["holdout_mirror"][
                    "mean_return_pct"
                ],
                "delayed_pf": item["holdout_delayed"]["profit_factor"],
                "delayed_mean_pct": item["holdout_delayed"][
                    "mean_return_pct"
                ],
            }
            for item in scenarios
        ]
    ).to_csv(out / "friction_matrix.csv", index=False)
    (research / "RESULT.md").write_text(
        "# Late-Day CE Inventory Rebound V7 Friction Audit\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"Required total friction: `{REQUIRED_COST_PCT}%` of premium return.\n\n"
        f"Maximum tested passing friction: "
        f"`{maximum_tested_passing_cost}%`.\n\n"
        f"Next tested failing friction: `{next_failed_cost}%`.\n\n"
        f"Required scenario: `{json.dumps(required, sort_keys=True)}`\n\n"
        "This is a descriptive sensitivity deduction, not an observed bid/ask "
        "or slippage model. No paper or live trading is authorized.\n",
        encoding="utf-8",
    )
    return 0 if required_pass else 7


if __name__ == "__main__":
    raise SystemExit(main())
