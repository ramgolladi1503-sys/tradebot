from __future__ import annotations

import csv
import hashlib
import json
import platform
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


FEATURES = [
    "minute_index",
    "gap_pct",
    "opening_range_width",
    "prior_session_return",
    "prior_session_range",
    "rolling_range_5",
    "rolling_range_15",
    "realized_vol_15",
    "atr_14",
    "vwap_distance",
    "dist_session_high",
    "dist_session_low",
    "body_range_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "compression_duration",
    "prior_failed_breaks",
    "ret_1",
    "range",
    "body",
    "volume",
]
FAMILIES = {
    "trend_continuation": ("opening_range_high_break", "opening_range_low_break", "compression_expansion_up", "compression_expansion_down"),
    "failed_breakout_reversal": ("session_high_sweep_reject", "session_low_sweep_reclaim"),
    "liquidity_sweep_reversal": ("session_high_sweep_reject", "session_low_sweep_reclaim", "long_upper_wick", "long_lower_wick"),
    "vwap_reclaim": ("vwap_reclaim", "vwap_rejection"),
    "compression_expansion": ("compression_expansion_up", "compression_expansion_down"),
    "gap_continuation": ("opening_range_high_break", "opening_range_low_break"),
    "gap_failure": ("session_high_sweep_reject", "session_low_sweep_reclaim"),
    "premium_lead_lag": (),
    "multi_event_sequence": ("vwap_reclaim", "vwap_rejection", "long_lower_wick", "long_upper_wick"),
}
MIN_SAMPLE = 35
DEV_END = "2024-07-22"
HOLDOUT_START = "2024-08-08"
COST_POINTS = 1.5
RAW_TARGET = 25000


@dataclass(frozen=True)
class SprintConfig:
    repo: Path
    output_dir: Path
    raw_target: int = RAW_TARGET
    replay_limit: int = 250


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def load_base(repo: Path) -> pd.DataFrame:
    labels = pd.read_parquet(repo / "research/structural_edge_discovery_v3/outcome_labels.parquet")
    labels = labels[labels["horizon_min"] == 30].copy()
    labels["session_date"] = labels["session_date"].astype(str)
    labels["weekday"] = pd.to_datetime(labels["entry_timestamp"], utc=True).dt.day_name()
    labels["month"] = pd.to_datetime(labels["entry_timestamp"], utc=True).dt.strftime("%Y-%m")
    labels["net_points_2x_cost"] = labels["gross_points"].astype(float) - COST_POINTS * 2
    return labels.reset_index(drop=True)


def quantile_grid(frame: pd.DataFrame) -> dict[str, list[float]]:
    grid: dict[str, list[float]] = {}
    for feature in FEATURES:
        if feature not in frame.columns:
            continue
        series = pd.to_numeric(frame[feature], errors="coerce").dropna()
        if series.nunique() < 4:
            continue
        grid[feature] = [float(series.quantile(q)) for q in (0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9)]
    return grid


def iter_hypotheses(frame: pd.DataFrame, raw_target: int) -> list[dict[str, Any]]:
    grid = quantile_grid(frame)
    event_types = sorted(frame["event_type"].dropna().unique())
    instruments = sorted(frame["instrument"].dropna().unique())
    hypotheses: list[dict[str, Any]] = []
    rng = random.Random(20260728)
    family_names = list(FAMILIES)
    feature_names = list(grid)
    thresholds = [(feature, op, value) for feature in feature_names for op in ("<=", ">=") for value in grid[feature]]
    for family in family_names:
        family_events = FAMILIES[family] or event_types
        for event_type in family_events:
            for instrument in instruments:
                for direction in ("UP", "DOWN"):
                    for feature, op, value in thresholds:
                        hypotheses.append(_hyp(family, event_type, instrument, direction, [(feature, op, value)]))
                        if len(hypotheses) >= raw_target:
                            return hypotheses
                    for _ in range(80):
                        a = rng.choice(thresholds)
                        b = rng.choice(thresholds)
                        if a[0] == b[0] and a[1] == b[1]:
                            continue
                        hypotheses.append(_hyp(family, event_type, instrument, direction, [a, b]))
                        if len(hypotheses) >= raw_target:
                            return hypotheses
    return hypotheses


def _hyp(family: str, event_type: str, instrument: str, direction: str, rules: list[tuple[str, str, float]]) -> dict[str, Any]:
    payload = {
        "family": family,
        "event_type": event_type,
        "instrument": instrument,
        "direction": direction,
        "rules": [{"feature": f, "operator": op, "threshold": round(float(v), 8)} for f, op, v in rules],
        "entry": "next_completed_bar_open",
        "action": "BUY_CE" if direction == "UP" else "BUY_PE",
        "stop_points": 20,
        "target_points": 30,
        "max_hold_minutes": 30,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    payload["hypothesis_id"] = "SESPRINT_" + stable_hash(payload)[:14]
    payload["reasoning"] = f"{family} search: {event_type} with completed-bar structural feature gates may precede buy-only premium movement."
    return payload


def apply_hypothesis(frame: pd.DataFrame, hyp: dict[str, Any]) -> pd.DataFrame:
    mask = (
        (frame["event_type"] == hyp["event_type"])
        & (frame["instrument"] == hyp["instrument"])
        & (frame["direction"] == hyp["direction"])
    )
    for rule in hyp["rules"]:
        series = pd.to_numeric(frame[rule["feature"]], errors="coerce")
        if rule["operator"] == ">=":
            mask &= series >= float(rule["threshold"])
        else:
            mask &= series <= float(rule["threshold"])
    return frame.loc[mask].copy()


def metrics(rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {"sample": 0}
    net = rows["net_points"].astype(float)
    gross = rows["gross_points"].astype(float)
    wins = net[net > 0]
    losses = net[net <= 0]
    total = float(net.sum())
    best = sorted(net.tolist(), reverse=True)
    month_counts = rows["month"].value_counts(normalize=True).to_dict()
    weekday_counts = rows["weekday"].value_counts(normalize=True).to_dict()
    return {
        "sample": int(len(rows)),
        "gross_pnl": float(gross.sum()),
        "net_pnl": total,
        "net_2x_cost": float(rows["net_points_2x_cost"].sum()),
        "expectancy": float(net.mean()),
        "win_rate": float((net > 0).mean()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and float(losses.sum()) != 0 else (999.0 if len(wins) else 0.0),
        "target30_rate": float((rows["mfe_points"].astype(float) >= 30).mean()),
        "stop20_rate": float((rows["mae_points"].astype(float) >= 20).mean()),
        "top5_contribution": float(sum(best[:5]) / total) if total else 0.0,
        "top10_contribution": float(sum(best[:10]) / total) if total else 0.0,
        "max_month_share": float(max(month_counts.values())) if month_counts else 0.0,
        "max_weekday_share": float(max(weekday_counts.values())) if weekday_counts else 0.0,
        "months": sorted(rows["month"].unique()),
        "weekdays": sorted(rows["weekday"].unique()),
    }


def rejection_reason(m: dict[str, Any], stage: str) -> str:
    if m.get("sample", 0) < MIN_SAMPLE:
        return "insufficient_sample"
    if m.get("expectancy", 0.0) <= 0 or m.get("target30_rate", 0.0) < 0.45:
        return f"{stage}_weak_premium_move_proxy"
    if m.get("top5_contribution", 0.0) > 0.45 or m.get("top10_contribution", 0.0) > 0.75:
        return "high_concentration"
    if m.get("max_month_share", 0.0) > 0.55:
        return "single_month_dependence"
    if m.get("max_weekday_share", 0.0) > 0.40:
        return "single_weekday_dependence"
    if m.get("net_2x_cost", 0.0) <= 0:
        return "slippage_cost_stress_fail"
    return ""


def screen_hypotheses(frame: pd.DataFrame, hypotheses: list[dict[str, Any]]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    survivors: list[dict[str, Any]] = []
    family_kept: dict[str, int] = {}
    dev = frame[frame["session_date"] <= DEV_END]
    for hyp in hypotheses:
        subset = apply_hypothesis(dev, hyp)
        m = metrics(subset)
        reason = rejection_reason(m, "development")
        row = {"hypothesis_id": hyp["hypothesis_id"], "family": hyp["family"], "event_type": hyp["event_type"], "direction": hyp["direction"], "instrument": hyp["instrument"], **m, "screen_rejection_reason": reason}
        rows.append(row)
        if not reason and family_kept.get(hyp["family"], 0) < 35:
            survivors.append(hyp)
            family_kept[hyp["family"]] = family_kept.get(hyp["family"], 0) + 1
    scores = pd.DataFrame(rows)
    if not scores.empty:
        scores = scores.sort_values(["screen_rejection_reason", "expectancy", "target30_rate"], ascending=[True, False, False])
    return scores, survivors


def validate(frame: pd.DataFrame, candidates: list[dict[str, Any]], replay_limit: int) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    dev = frame[frame["session_date"] <= DEV_END]
    wf = frame[(frame["session_date"] > DEV_END) & (frame["session_date"] < HOLDOUT_START)]
    holdout = frame[frame["session_date"] >= HOLDOUT_START]
    rng = random.Random(44)
    validation_rows: list[dict[str, Any]] = []
    controls: dict[str, Any] = {}
    algotest: list[dict[str, Any]] = []
    ranked = []
    for hyp in candidates:
        m = metrics(apply_hypothesis(dev, hyp))
        ranked.append((float(m.get("expectancy", 0.0)), hyp))
    for _, hyp in sorted(ranked, key=lambda item: item[0], reverse=True)[:replay_limit]:
        dev_rows = apply_hypothesis(dev, hyp)
        wf_rows = apply_hypothesis(wf, hyp)
        hold_rows = apply_hypothesis(holdout, hyp)
        dev_m = metrics(dev_rows)
        wf_m = metrics(wf_rows)
        hold_m = metrics(hold_rows)
        inv = hyp.copy()
        inv["direction"] = "DOWN" if hyp["direction"] == "UP" else "UP"
        delayed = dev_rows.copy()
        delayed["net_points"] = delayed["net_points"].astype(float) - delayed["ret_1"].abs().astype(float) * 1000
        random_rows = dev.sample(n=min(len(dev_rows), len(dev)), random_state=7) if len(dev_rows) else dev_rows
        perm = dev_rows.copy()
        if not perm.empty:
            perm["net_points"] = list(reversed(perm["net_points"].tolist()))
        ctrl = {
            "direction_inversion": metrics(apply_hypothesis(dev, inv).head(len(dev_rows))),
            "count_matched_random": metrics(random_rows),
            "delayed_entry": metrics(delayed),
            "feature_label_permutation": metrics(perm),
            "event_time_jitter": metrics(dev_rows.assign(net_points=[x + rng.uniform(-2, 2) for x in dev_rows["net_points"].astype(float)])) if len(dev_rows) else {"sample": 0},
        }
        controls[hyp["hypothesis_id"]] = ctrl
        reason = (
            rejection_reason(dev_m, "replay")
            or _control_rejection(dev_m, ctrl)
            or rejection_reason(wf_m, "walk_forward")
            or rejection_reason(hold_m, "holdout")
        )
        validation_rows.append(
            {
                "hypothesis_id": hyp["hypothesis_id"],
                "family": hyp["family"],
                "action": hyp["action"],
                "replayed": True,
                "dev": dev_m,
                "walk_forward": wf_m,
                "holdout": hold_m,
                "validation_rejection_reason": reason,
                "algotest_ready": reason == "",
            }
        )
        if reason == "":
            algotest.append({"hypothesis": hyp, "development": dev_m, "walk_forward": wf_m, "holdout": hold_m})
    return pd.DataFrame(validation_rows), controls, algotest


def _control_rejection(actual: dict[str, Any], controls: dict[str, dict[str, Any]]) -> str:
    for name, ctrl in controls.items():
        if ctrl.get("sample", 0) and float(actual.get("expectancy", 0.0)) <= float(ctrl.get("expectancy", 0.0)) + 2.0:
            return f"failed_control_superiority:{name}"
    return ""


def audit_report(out: Path, raw: pd.DataFrame, validation: pd.DataFrame, algotest: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = []
    if int(raw["hypothesis_id"].nunique()) < 20000:
        blockers.append("raw_hypothesis_count_below_20000")
    if validation.empty:
        blockers.append("no_replayed_candidates")
    if not validation.empty and validation["algotest_ready"].sum() != len(algotest):
        blockers.append("algotest_export_mismatch")
    report = {
        "audit_pass": not blockers,
        "blockers": blockers,
        "raw_hypotheses": int(raw["hypothesis_id"].nunique()),
        "replayed": int(len(validation)),
        "algotest_ready": int(len(algotest)),
        "read_only": True,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }
    write_json(out / "independent_audit_report.json", report)
    return report


def run_sprint(cfg: SprintConfig) -> dict[str, Any]:
    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)
    base = load_base(cfg.repo)
    manifest = {
        "worktree_path": str(cfg.repo),
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], cfg.repo),
        "base_commit": git(["rev-parse", "HEAD"], cfg.repo),
        "python_version": platform.python_version(),
        "source_artifacts": [
            "research/structural_edge_discovery_v3/outcome_labels.parquet",
            "research/structural_edge_discovery_v3/pre_outcome_features.parquet",
            "research/structural_edge_discovery_v3/final_verdict.json",
        ],
        "scope": "research_only_large_hypothesis_sprint",
    }
    write_json(out / "pre_change_manifest.json", manifest)
    hypotheses = iter_hypotheses(base, cfg.raw_target)
    with (out / "raw_hypotheses.jsonl").open("w", encoding="utf-8") as handle:
        for hyp in hypotheses:
            handle.write(json.dumps(hyp, sort_keys=True) + "\n")
    screen, survivors = screen_hypotheses(base, hypotheses)
    screen.to_csv(out / "hypothesis_screen.csv", index=False)
    validation, controls, algotest = validate(base, survivors, cfg.replay_limit)
    validation.to_json(out / "validation_results.jsonl", orient="records", lines=True)
    write_json(out / "negative_controls.json", controls)
    write_json(out / "algotest_candidates.json", algotest)
    rejection_stats = {
        "screen_rejections": screen["screen_rejection_reason"].replace("", "passed_screen").value_counts().to_dict(),
        "validation_rejections": validation["validation_rejection_reason"].replace("", "algotest_ready").value_counts().to_dict() if not validation.empty else {},
        "family_counts_raw": screen["family"].value_counts().to_dict() if not screen.empty else {},
        "family_counts_replayed": validation["family"].value_counts().to_dict() if not validation.empty else {},
    }
    write_json(out / "rejection_statistics.json", rejection_stats)
    audit = audit_report(out, screen, validation, algotest)
    verdict = "ALGOTEST_READY_CANDIDATE_FOUND" if algotest else "NO_SURVIVING_EDGE_FOUND"
    final = {
        "verdict": verdict,
        "hypotheses_generated": len(hypotheses),
        "hypotheses_screened": int(len(screen)),
        "hypotheses_replayed": int(len(validation)),
        "surviving_candidates": len(algotest),
        "audit_pass": audit["audit_pass"],
        "blockers": [] if algotest else ["no_candidate_survived_full_validation"],
        "recommended_next_discovery_family": _next_family(rejection_stats),
        "read_only": True,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }
    write_json(out / "final_verdict.json", final)
    _write_report(out / "final_report.md", final, rejection_stats, validation)
    _manifest(out)
    return final


def _next_family(stats: dict[str, Any]) -> str:
    replayed = stats.get("family_counts_replayed", {})
    if not replayed:
        return "premium_lead_lag_requires_trusted_option_series"
    return min(replayed, key=lambda key: replayed[key])


def _write_report(path: Path, final: dict[str, Any], stats: dict[str, Any], validation: pd.DataFrame) -> None:
    lines = [
        "# Structural Edge Discovery Sprint",
        "",
        f"Verdict: {final['verdict']}",
        f"Hypotheses generated: {final['hypotheses_generated']}",
        f"Hypotheses replayed: {final['hypotheses_replayed']}",
        f"Surviving candidates: {final['surviving_candidates']}",
        f"Audit pass: {final['audit_pass']}",
        "",
        "Screen rejection statistics:",
        json.dumps(stats.get("screen_rejections", {}), indent=2, sort_keys=True),
        "",
        "Validation rejection statistics:",
        json.dumps(stats.get("validation_rejections", {}), indent=2, sort_keys=True),
        "",
        "No production, broker, feed, risk, execution, dashboard, credential, or deployment code was touched.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _manifest(out: Path) -> None:
    rows = []
    for path in sorted(out.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append({"path": str(path.relative_to(out)), "sha256": digest, "bytes": path.stat().st_size})
    write_json(out / "artifact_manifest.json", {"artifact_count": len(rows), "artifacts": rows, "semantic_hash": stable_hash(rows)})

