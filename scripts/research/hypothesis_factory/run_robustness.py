#!/usr/bin/env python3
"""Run robustness gates for a Strategy Certification Kernel candidate.

This script requires a per-trade ledger. If no per-trade evidence is supplied it
blocks certification rather than inventing robustness from aggregate leaderboard
statistics.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import strategy_certification_artifacts as sca  # noqa: E402


def load_trade_rows(path: Path, candidate_id: str, candidate_shape_key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            if candidate_id and raw.get("hypothesis_id") not in ("", None, candidate_id):
                continue
            if candidate_shape_key and raw.get("candidate_shape_key") not in ("", None, candidate_shape_key):
                continue
            pnl = sca.to_float(raw.get("pnl_bps"), default=math.nan)
            if math.isnan(pnl):
                continue
            row = dict(raw)
            row["pnl_bps"] = pnl
            row["is_fallback"] = sca.to_bool(raw.get("is_fallback"))
            rows.append(row)
    return sorted(rows, key=lambda r: str(r.get("timestamp") or r.get("session") or ""))


def profit_factor(values: list[float]) -> float:
    gains = sum(v for v in values if v > 0)
    losses = abs(sum(v for v in values if v < 0))
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def metrics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "trades": 0,
            "mean_pnl_bps": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_bps": 0.0,
        }
    wins = sum(1 for value in values if value > 0)
    pf = profit_factor(values)
    return {
        "trades": len(values),
        "mean_pnl_bps": round(sum(values) / len(values), 6),
        "win_rate": round(wins / len(values), 6),
        "profit_factor": round(pf, 6) if math.isfinite(pf) else "INF",
        "max_drawdown_bps": round(max_drawdown(values), 6),
    }


def split_chunks(values: list[float], chunks: int) -> list[list[float]]:
    if chunks <= 0:
        return [values]
    out: list[list[float]] = []
    size = max(1, math.ceil(len(values) / chunks))
    for start in range(0, len(values), size):
        out.append(values[start:start + size])
    return out


def session_concentration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        session = str(row.get("session") or str(row.get("timestamp", ""))[:10] or f"row-{index}")
        counts[session] = counts.get(session, 0) + 1
    total = max(1, len(rows))
    max_session = max(counts.values()) if counts else 0
    return {
        "sessions": len(counts),
        "max_session_trades": max_session,
        "max_session_fraction": round(max_session / total, 6),
    }


def sign_flip_negative_control(values: list[float], iterations: int, seed: int) -> dict[str, Any]:
    if not values:
        return {"iterations": iterations, "observed_mean": 0.0, "p95_random_mean": 0.0, "passed": False}
    rng = random.Random(seed)
    observed = sum(values) / len(values)
    random_means: list[float] = []
    absolute = [abs(value) for value in values]
    for _ in range(iterations):
        randomized = [value if rng.random() >= 0.5 else -value for value in absolute]
        random_means.append(sum(randomized) / len(randomized))
    random_means.sort()
    index = min(len(random_means) - 1, int(0.95 * len(random_means)))
    p95 = random_means[index]
    return {
        "iterations": iterations,
        "observed_mean": round(observed, 6),
        "p95_random_mean": round(p95, 6),
        "passed": observed > p95,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    screen_run_dir = Path(args.screen_run_dir)
    out_dir = Path(args.output_dir) / (args.run_id or datetime.now(timezone.utc).strftime("ROBUST-%Y%m%dT%H%M%SZ"))
    out_dir.mkdir(parents=True, exist_ok=True)

    screen_manifest_path = screen_run_dir / "run_manifest.json"
    leaderboard_path = screen_run_dir / "leaderboard.csv"
    candidate_filter_path = Path(args.candidate_filter_report) if args.candidate_filter_report else screen_run_dir / "candidate_filter_report.json"
    trade_path = Path(args.trades_csv) if args.trades_csv else screen_run_dir / "candidate_trades.csv"

    blocking_reasons: list[str] = []
    if not screen_manifest_path.exists():
        blocking_reasons.append("missing_screen_manifest")
    if not leaderboard_path.exists():
        blocking_reasons.append("missing_leaderboard")
    if not candidate_filter_path.exists():
        blocking_reasons.append("missing_candidate_filter_report")
    if not trade_path.exists():
        blocking_reasons.append("missing_trade_ledger")

    if blocking_reasons:
        result = {
            "schema_version": "tradebot-robustness-result-v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "ROBUSTNESS_BLOCKED",
            "robustness_passed": False,
            "blocking_reasons": blocking_reasons,
            "candidate_hypothesis_id": args.candidate_hypothesis_id,
            "candidate_shape_key": args.candidate_shape_key,
            "runtime_authority": sca.SAFE_RUNTIME_AUTHORITY,
            "broker_actions_allowed": sca.SAFE_BROKER_ACTIONS_ALLOWED,
        }
        sca.write_json(out_dir / "robustness_results.json", result)
        sca.write_json(out_dir / "robustness_manifest.json", {**result, "screen_run_dir": str(screen_run_dir), "trades_csv": str(trade_path)})
        sca.write_markdown_report(out_dir / "robustness_report.md", "Strategy Robustness Report", [
            "- Verdict: `ROBUSTNESS_BLOCKED`",
            f"- Blocking reasons: `{', '.join(blocking_reasons)}`",
            "- Certification remains blocked.",
        ])
        return result

    trades = load_trade_rows(trade_path, args.candidate_hypothesis_id, args.candidate_shape_key)
    fallback_rows = [row for row in trades if row.get("is_fallback")]
    clean_trades = [row for row in trades if not row.get("is_fallback")]
    values = [float(row["pnl_bps"]) for row in clean_trades]

    all_metrics = metrics(values)
    split = max(0, min(len(values), int(len(values) * (1.0 - args.oos_fraction))))
    train_values = values[:split]
    oos_values = values[split:]
    train_metrics = metrics(train_values)
    oos_metrics = metrics(oos_values)
    chunks = split_chunks(values, args.walk_forward_chunks)
    chunk_metrics = [metrics(chunk) for chunk in chunks]
    stress_values = args.cost_stress_bps if args.cost_stress_bps else [0.0, 2.0, 5.0, 10.0]
    cost_stress = []
    for stress in stress_values:
        adjusted = [value - stress for value in values]
        item = metrics(adjusted)
        item["stress_bps"] = stress
        item["passed"] = item["trades"] >= args.min_trades and sca.to_float(item["mean_pnl_bps"]) > 0
        cost_stress.append(item)

    concentration = session_concentration(clean_trades)
    negative_control = sign_flip_negative_control(values, args.negative_control_iterations, args.random_seed)

    gate_results = {
        "min_trades": all_metrics["trades"] >= args.min_trades,
        "positive_train": sca.to_float(train_metrics["mean_pnl_bps"]) > 0,
        "positive_oos": sca.to_float(oos_metrics["mean_pnl_bps"]) > 0 and oos_metrics["trades"] > 0,
        "walk_forward_positive": bool(chunk_metrics) and all(sca.to_float(chunk["mean_pnl_bps"]) > 0 for chunk in chunk_metrics),
        "cost_slippage_survival": bool(cost_stress) and all(item["passed"] for item in cost_stress),
        "session_concentration_ok": concentration["max_session_fraction"] <= args.max_session_fraction,
        "negative_control_passed": bool(negative_control["passed"]),
        "fallback_excluded": len(fallback_rows) == 0,
    }
    failed_gates = [key for key, passed in gate_results.items() if not passed]
    passed = not failed_gates

    result = {
        "schema_version": "tradebot-robustness-result-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ROBUSTNESS_PASSED" if passed else "ROBUSTNESS_FAILED",
        "robustness_passed": passed,
        "failed_gates": failed_gates,
        "candidate_hypothesis_id": args.candidate_hypothesis_id,
        "candidate_shape_key": args.candidate_shape_key,
        "runtime_authority": sca.SAFE_RUNTIME_AUTHORITY,
        "broker_actions_allowed": sca.SAFE_BROKER_ACTIONS_ALLOWED,
        "metrics": all_metrics,
        "train_metrics": train_metrics,
        "oos_metrics": oos_metrics,
        "walk_forward_chunks": chunk_metrics,
        "cost_slippage_stress": cost_stress,
        "session_concentration": concentration,
        "negative_control": negative_control,
        "fallback_rows": len(fallback_rows),
        "evidence_hashes": sca.evidence_hashes([screen_manifest_path, leaderboard_path, candidate_filter_path, trade_path]),
    }

    manifest = {
        **result,
        "screen_run_dir": str(screen_run_dir),
        "screen_manifest_sha256": sca.sha256_file(screen_manifest_path),
        "leaderboard_sha256": sca.sha256_file(leaderboard_path),
        "candidate_filter_report_sha256": sca.sha256_file(candidate_filter_path),
        "trades_csv": str(trade_path),
        "trades_csv_sha256": sca.sha256_file(trade_path),
        "thresholds": {
            "min_trades": args.min_trades,
            "oos_fraction": args.oos_fraction,
            "walk_forward_chunks": args.walk_forward_chunks,
            "cost_stress_bps": stress_values,
            "max_session_fraction": args.max_session_fraction,
            "negative_control_iterations": args.negative_control_iterations,
        },
    }

    sca.write_json(out_dir / "robustness_results.json", result)
    sca.write_json(out_dir / "robustness_manifest.json", manifest)
    sca.write_markdown_report(out_dir / "robustness_report.md", "Strategy Robustness Report", [
        f"- Verdict: `{result['status']}`",
        f"- Robustness passed: `{passed}`",
        f"- Failed gates: `{', '.join(failed_gates) if failed_gates else 'NONE'}`",
        f"- Trades: `{all_metrics['trades']}`",
        f"- Mean pnl bps: `{all_metrics['mean_pnl_bps']}`",
        f"- OOS mean pnl bps: `{oos_metrics['mean_pnl_bps']}`",
        f"- Runtime authority: `{sca.SAFE_RUNTIME_AUTHORITY}`",
        f"- Broker actions allowed: `{sca.SAFE_BROKER_ACTIONS_ALLOWED}`",
    ])
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-run-dir", required=True)
    parser.add_argument("--candidate-filter-report", default="")
    parser.add_argument("--candidate-hypothesis-id", default="")
    parser.add_argument("--candidate-shape-key", default="")
    parser.add_argument("--trades-csv", default="")
    parser.add_argument("--output-dir", default="research/hypotheses/robustness_runs")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--min-trades", type=int, default=100)
    parser.add_argument("--oos-fraction", type=float, default=0.30)
    parser.add_argument("--walk-forward-chunks", type=int, default=4)
    parser.add_argument("--cost-stress-bps", type=float, action="append", default=[])
    parser.add_argument("--max-session-fraction", type=float, default=0.30)
    parser.add_argument("--negative-control-iterations", type=int, default=200)
    parser.add_argument("--random-seed", type=int, default=1729)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run(args)
    print(json.dumps({
        "status": result["status"],
        "robustness_passed": result["robustness_passed"],
        "failed_gates": result.get("failed_gates", []),
        "blocking_reasons": result.get("blocking_reasons", []),
        "runtime_authority": result["runtime_authority"],
        "broker_actions_allowed": result["broker_actions_allowed"],
    }, indent=2, sort_keys=True))
    return 0 if result["robustness_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
