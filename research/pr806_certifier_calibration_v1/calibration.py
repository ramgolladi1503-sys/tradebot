from __future__ import annotations

import copy
import hashlib
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import binomtest

from research.autonomous_structural_edge_exhaustion_v1.certification import (
    robustness,
    validation_and_wfa,
)
from research.autonomous_structural_edge_exhaustion_v1.certification_v3 import (
    CAMPAIGN_GLOBAL_Q_V3,
    structural_screen_v3,
)
from research.autonomous_structural_edge_exhaustion_v1.common import COST_BPS, digest
from research.autonomous_structural_edge_exhaustion_v1.outcomes import summarize

EXPECTED_ARTIFACT_SHA256 = "b00f8aeebc005112c6632a580a3123303c4aa1be64cc6158bfe244a55bb65b4a"
EXPECTED_STAGE6_SEMANTIC_SHA256 = "2bdf60d6d7d463146f4ac11b4c9078ed04f2cee965d9629858660b1af34e6ae3"
EXPECTED_HYPOTHESIS_COUNT = 648
CALIBRATION_SEED = 20260808
PLANT_DELTAS_BPS = (2.0, 5.0, 8.0, 15.0)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_zip_json(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    return json.loads(zf.read(name).decode("utf-8"))


def load_authoritative_artifact(path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sha = file_sha256(path)
    if sha != EXPECTED_ARTIFACT_SHA256:
        raise ValueError(f"artifact sha mismatch expected={EXPECTED_ARTIFACT_SHA256} actual={sha}")
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        required = {"stage5_development_outcomes.json", "stage6_structural_screen.json", "final_authority.json"}
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"required artifact members missing: {missing}")
        stage5 = _read_zip_json(zf, "stage5_development_outcomes.json")
        stage6 = _read_zip_json(zf, "stage6_structural_screen.json")
        final = _read_zip_json(zf, "final_authority.json")
    if len(stage5.get("records", [])) != EXPECTED_HYPOTHESIS_COUNT:
        raise ValueError(f"unexpected stage5 hypothesis count: {len(stage5.get('records', []))}")
    if len(stage6.get("results", [])) != EXPECTED_HYPOTHESIS_COUNT:
        raise ValueError(f"unexpected stage6 result count: {len(stage6.get('results', []))}")
    if stage6.get("semantic_sha256") != EXPECTED_STAGE6_SEMANTIC_SHA256:
        raise ValueError("stage6 semantic authority mismatch")
    forbidden_splits = {
        str(event.get("split"))
        for record in stage5.get("records", [])
        for event in record.get("events", [])
        if str(event.get("split")) not in {"observation", "replication", "validation"}
    }
    if forbidden_splits:
        raise ValueError(f"calibration input contains unauthorized split(s): {sorted(forbidden_splits)}")
    return stage5, stage6, final


def bh_qvalues(pvalues: Sequence[float]) -> np.ndarray:
    p = np.asarray(pvalues, dtype=float)
    if p.size == 0:
        return p
    order = np.argsort(p)
    ranked = p[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1, dtype=float)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    out = np.empty_like(adjusted)
    out[order] = adjusted
    return out


def actual_gate_attribution(stage6: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(stage6.get("results", []))
    gate_names = sorted({key for row in rows for key in (row.get("gates") or {})})
    gate_counts = {name: int(sum(bool((row.get("gates") or {}).get(name)) for row in rows)) for name in gate_names}
    pre_bh = []
    for row in rows:
        gates = dict(row.get("gates") or {})
        without_bh = [value for name, value in gates.items() if name != "campaign_global_bh_q_le_2_5pct"]
        if without_bh and all(without_bh):
            pre_bh.append(
                {
                    "hypothesis_id": row["hypothesis_id"],
                    "family": row["family"],
                    "replication_n": row["replication"]["n"],
                    "replication_mean_bps": row["replication"]["mean_bps"],
                    "replication_hit_rate": row["replication"]["hit_rate"],
                    "replication_ci90": row["replication"]["ci90"],
                    "sign_p": row["replication"]["sign_p"],
                    "bh_q": row["bh_q"],
                }
            )
    pre_bh.sort(key=lambda row: (float(row["bh_q"]), float(row["sign_p"]), str(row["hypothesis_id"])))
    return {
        "hypothesis_count": len(rows),
        "gate_pass_counts": gate_counts,
        "all_non_bh_gates_passed_count": len(pre_bh),
        "all_non_bh_gates_passed": pre_bh,
        "minimum_replication_sign_p": min(float(row["replication"]["sign_p"]) for row in rows),
        "minimum_bh_q": min(float(row["bh_q"]) for row in rows),
    }


def _events(record: Mapping[str, Any], split: str) -> list[dict[str, Any]]:
    return [dict(event) for event in record.get("events", []) if event.get("split") == split]


def _centered_directional_arrays(stage5: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for record in stage5.get("records", []):
        hyp = dict(record["hypothesis"])
        split_arrays = {}
        for split in ("observation", "replication", "validation"):
            values = np.asarray(
                [float(event["directional_excess_bps"]) for event in _events(record, split)],
                dtype=float,
            )
            split_arrays[split] = values - float(np.mean(values))
        rows.append({"hypothesis": hyp, "centered": split_arrays})
    return rows


def _precompute_centered_stage6(stage5: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[float, dict[str, dict[str, Any]]]]:
    rows = _centered_directional_arrays(stage5)
    cache: dict[float, dict[str, dict[str, Any]]] = {}
    for delta in (0.0, *PLANT_DELTAS_BPS):
        per_hyp: dict[str, dict[str, Any]] = {}
        for row in rows:
            hid = str(row["hypothesis"]["hypothesis_id"])
            obs = row["centered"]["observation"] + delta
            rep = row["centered"]["replication"] + delta
            rep_summary = summarize(rep)
            obs_mean = float(np.mean(obs))
            gates_without_bh = {
                "observation_n_ge_20": len(obs) >= 20,
                "observation_abs_mean_ge_2bps": abs(obs_mean) >= 2.0 - 1e-12,
                "replication_n_ge_10": len(rep) >= 10,
                "replication_mean_ge_2bps": float(rep_summary["mean_bps"] or -1e9) >= 2.0 - 1e-12,
                "replication_hit_rate_ge_55pct": float(rep_summary["hit_rate"] or 0.0) >= 0.55,
                "replication_ci90_lower_positive": (
                    rep_summary["ci90"][0] is not None and float(rep_summary["ci90"][0]) > 0.0
                ),
            }
            per_hyp[hid] = {
                "p": float(rep_summary["sign_p"]),
                "all_non_bh_gates": all(gates_without_bh.values()),
            }
        cache[float(delta)] = per_hyp
    return rows, cache


def dense_planted_edge_recovery(stage5: Mapping[str, Any]) -> dict[str, Any]:
    rows, cache = _precompute_centered_stage6(stage5)
    ids = [str(row["hypothesis"]["hypothesis_id"]) for row in rows]
    result = []
    for delta in PLANT_DELTAS_BPS:
        pvalues = [cache[float(delta)][hid]["p"] for hid in ids]
        qvalues = bh_qvalues(pvalues)
        bh_pass = 0
        full_pass = 0
        for hid, q in zip(ids, qvalues):
            bh = float(q) <= CAMPAIGN_GLOBAL_Q_V3
            bh_pass += int(bh)
            full_pass += int(bh and cache[float(delta)][hid]["all_non_bh_gates"])
        result.append(
            {
                "plant_bps": delta,
                "planted_hypotheses": len(ids),
                "bh_pass_count": bh_pass,
                "stage6_recovered_count": full_pass,
                "stage6_recall": full_pass / len(ids),
                "minimum_bh_q": float(np.min(qvalues)),
            }
        )
    return {"mode": "all_648_centered_hypotheses_planted", "results": result}


def sparse_planted_edge_recovery(
    stage5: Mapping[str, Any],
    trials: int = 200,
    seed: int = CALIBRATION_SEED,
) -> dict[str, Any]:
    rows, cache = _precompute_centered_stage6(stage5)
    ids = [str(row["hypothesis"]["hypothesis_id"]) for row in rows]
    family_ids: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        family_ids[str(row["hypothesis"]["family"])].append(str(row["hypothesis"]["hypothesis_id"]))
    families = sorted(family_ids)
    rng = np.random.default_rng(seed)
    result = []
    for delta in PLANT_DELTAS_BPS:
        recalls: list[float] = []
        false_positives: list[int] = []
        for _ in range(trials):
            planted = {str(rng.choice(family_ids[family])) for family in families}
            pvalues = [cache[float(delta if hid in planted else 0.0)][hid]["p"] for hid in ids]
            qvalues = bh_qvalues(pvalues)
            recovered: set[str] = set()
            for hid, q in zip(ids, qvalues):
                d = float(delta if hid in planted else 0.0)
                if float(q) <= CAMPAIGN_GLOBAL_Q_V3 and cache[d][hid]["all_non_bh_gates"]:
                    recovered.add(hid)
            recalls.append(len(recovered & planted) / len(planted))
            false_positives.append(len(recovered - planted))
        result.append(
            {
                "plant_bps": delta,
                "planted_per_trial": len(families),
                "trials": trials,
                "mean_recall": float(np.mean(recalls)),
                "median_recall": float(np.median(recalls)),
                "recall_p10": float(np.quantile(recalls, 0.10)),
                "recall_p90": float(np.quantile(recalls, 0.90)),
                "mean_false_positives": float(np.mean(false_positives)),
                "max_false_positives": int(max(false_positives)),
            }
        )
    return {"mode": "one_random_planted_hypothesis_per_family", "family_count": len(families), "results": result}


def _mean_bootstrap_p(values: Sequence[float]) -> float:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return 1.0
    observed = float(np.mean(arr))
    centered = arr - observed
    rng = np.random.default_rng(20260807 + len(arr))
    indexes = rng.integers(0, len(arr), size=(2000, len(arr)))
    null_means = centered[indexes].mean(axis=1)
    return float((1 + np.sum(null_means >= observed)) / (len(null_means) + 1))


def mean_targeting_diagnostic(stage5: Mapping[str, Any]) -> dict[str, Any]:
    pvalues = []
    for record in stage5.get("records", []):
        rep = [float(event["directional_excess_bps"]) for event in _events(record, "replication")]
        pvalues.append(_mean_bootstrap_p(rep))
    qvalues = bh_qvalues(pvalues)
    return {
        "test": "centered_session_bootstrap_one_sided_mean_excess_gt_zero_diagnostic",
        "minimum_p": float(np.min(pvalues)),
        "minimum_bh_q": float(np.min(qvalues)),
        "raw_p_lt_0_05": int(np.sum(np.asarray(pvalues) < 0.05)),
        "raw_p_lt_0_025": int(np.sum(np.asarray(pvalues) < 0.025)),
        "bh_q_le_0_10": int(np.sum(qvalues <= 0.10)),
        "bh_q_le_0_05": int(np.sum(qvalues <= 0.05)),
        "bh_q_le_0_025": int(np.sum(qvalues <= 0.025)),
        "promotion_authorized": False,
    }


def asymmetric_payoff_control() -> dict[str, Any]:
    values = np.asarray([20.0] * 40 + [-5.0] * 60, dtype=float)
    stats = summarize(values)
    mean_p = _mean_bootstrap_p(values)
    return {
        "distribution": "40x +20bps, 60x -5bps",
        "mean_bps": float(np.mean(values)),
        "hit_rate": float(np.mean(values > 0)),
        "current_sign_p": float(stats["sign_p"]),
        "mean_targeting_bootstrap_p": mean_p,
        "current_hit_rate_gate_ge_55pct": bool(float(stats["hit_rate"]) >= 0.55),
        "interpretation": "positive expectancy can be rejected by a hit-rate/sign-test definition even when mean return is strongly positive",
    }


def _raw_event_specs(stage5: Mapping[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    dates = sorted(
        {
            str(event["session_date"])
            for record in stage5.get("records", [])
            for event in record.get("events", [])
            if event.get("split") in {"observation", "replication"}
        }
    )
    date_idx = {date: i for i, date in enumerate(dates)}
    specs = []
    for record in stage5.get("records", []):
        obs = _events(record, "observation")
        rep = _events(record, "replication")
        specs.append(
            {
                "hypothesis_id": str(record["hypothesis"]["hypothesis_id"]),
                "family": str(record["hypothesis"]["family"]),
                "obs_values": np.asarray([float(event["raw_excess_bps"]) for event in obs], dtype=float),
                "obs_idx": np.asarray([date_idx[str(event["session_date"])] for event in obs], dtype=int),
                "rep_values": np.asarray([float(event["raw_excess_bps"]) for event in rep], dtype=float),
                "rep_idx": np.asarray([date_idx[str(event["session_date"])] for event in rep], dtype=int),
            }
        )
    return dates, specs


def null_session_sign_flip_calibration(
    stage5: Mapping[str, Any],
    worlds: int = 1000,
    seed: int = CALIBRATION_SEED,
) -> dict[str, Any]:
    dates, specs = _raw_event_specs(stage5)
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.asarray([-1.0, 1.0]), size=(worlds, len(dates)))
    p_matrix = np.empty((worlds, len(specs)), dtype=float)
    pre_ci_gates = np.zeros((worlds, len(specs)), dtype=bool)
    max_n = max(len(spec["obs_values"]) for spec in specs)
    binom = {(n, h): float(binomtest(h, n, 0.5, alternative="greater").pvalue) for n in range(1, max_n + 1) for h in range(n + 1)}

    for j, spec in enumerate(specs):
        obs_world = signs[:, spec["obs_idx"]] * spec["obs_values"][None, :]
        rep_world = signs[:, spec["rep_idx"]] * spec["rep_values"][None, :]
        direction = np.where(obs_world.mean(axis=1) >= 0.0, 1.0, -1.0)
        obs_dir = obs_world * direction[:, None]
        rep_dir = rep_world * direction[:, None]
        hits = (rep_dir > 0.0).sum(axis=1)
        n_rep = rep_dir.shape[1]
        p_matrix[:, j] = np.asarray([binom[(n_rep, int(hit))] for hit in hits], dtype=float)
        pre_ci_gates[:, j] = (
            (np.abs(obs_dir.mean(axis=1)) >= 2.0)
            & (rep_dir.mean(axis=1) >= 2.0)
            & ((hits / n_rep) >= 0.55)
        )

    bh_any = 0
    bh_pass_total = 0
    full_false_positives: list[dict[str, Any]] = []
    min_qs = []
    for world in range(worlds):
        q = bh_qvalues(p_matrix[world])
        min_qs.append(float(np.min(q)))
        bh = q <= CAMPAIGN_GLOBAL_Q_V3
        if np.any(bh):
            bh_any += 1
            bh_pass_total += int(np.sum(bh))
        candidates = np.flatnonzero(bh & pre_ci_gates[world])
        for j in candidates:
            spec = specs[int(j)]
            obs = signs[world, spec["obs_idx"]] * spec["obs_values"]
            rep = signs[world, spec["rep_idx"]] * spec["rep_values"]
            direction = 1.0 if float(np.mean(obs)) >= 0.0 else -1.0
            obs_stats = summarize(obs * direction)
            rep_stats = summarize(rep * direction)
            gates = {
                "observation_n_ge_20": obs_stats["n"] >= 20,
                "observation_abs_mean_ge_2bps": abs(float(obs_stats["mean_bps"] or 0.0)) >= 2.0,
                "replication_n_ge_10": rep_stats["n"] >= 10,
                "replication_mean_ge_2bps": float(rep_stats["mean_bps"] or -1e9) >= 2.0,
                "replication_hit_rate_ge_55pct": float(rep_stats["hit_rate"] or 0.0) >= 0.55,
                "replication_ci90_lower_positive": rep_stats["ci90"][0] is not None and float(rep_stats["ci90"][0]) > 0.0,
                "campaign_global_bh_q_le_2_5pct": float(q[int(j)]) <= CAMPAIGN_GLOBAL_Q_V3,
            }
            if all(gates.values()):
                full_false_positives.append(
                    {
                        "world": world,
                        "hypothesis_id": spec["hypothesis_id"],
                        "family": spec["family"],
                        "bh_q": float(q[int(j)]),
                        "observation": obs_stats,
                        "replication": rep_stats,
                    }
                )
    return {
        "null": "global session-level Rademacher sign flip of raw excess; observation-only direction reselected per world",
        "worlds": worlds,
        "worlds_with_any_bh_pass": bh_any,
        "bh_passes_total": bh_pass_total,
        "full_stage6_false_positive_count": len(full_false_positives),
        "full_stage6_false_positive_rate_per_world": len(full_false_positives) / worlds,
        "full_stage6_false_positives": full_false_positives,
        "minimum_q_quantiles": {
            "min": float(np.min(min_qs)),
            "p01": float(np.quantile(min_qs, 0.01)),
            "p05": float(np.quantile(min_qs, 0.05)),
            "median": float(np.median(min_qs)),
            "p95": float(np.quantile(min_qs, 0.95)),
            "max": float(np.max(min_qs)),
        },
    }


def _center_event_field(events: list[dict[str, Any]], split: str, field: str) -> float | None:
    vals = [float(event[field]) for event in events if event.get("split") == split and event.get(field) is not None and math.isfinite(float(event[field]))]
    return float(np.mean(vals)) if vals else None


def _synthetic_stage5_for_full_lane(stage5: Mapping[str, Any], planted: set[str], delta: float) -> dict[str, Any]:
    output = {"records": []}
    fields = (
        "directional_excess_bps",
        "directional_gross_bps",
        "delayed_net_proxy_bps",
        "shorter_net_proxy_bps",
        "longer_net_proxy_bps",
    )
    for original in stage5.get("records", []):
        record = copy.deepcopy(original)
        hid = str(record["hypothesis"]["hypothesis_id"])
        d = float(delta if hid in planted else 0.0)
        events = record["events"]
        centers = {
            split: {field: _center_event_field(events, split, field) for field in fields}
            for split in ("observation", "replication", "validation")
        }
        for event in events:
            split = str(event["split"])
            c = centers[split]
            if event.get("directional_excess_bps") is not None:
                event["directional_excess_bps"] = float(event["directional_excess_bps"]) - float(c["directional_excess_bps"]) + d
            if event.get("directional_gross_bps") is not None:
                event["directional_gross_bps"] = float(event["directional_gross_bps"]) - float(c["directional_gross_bps"]) + COST_BPS + d
                event["net_proxy_bps"] = float(event["directional_gross_bps"]) - COST_BPS
            for field in ("delayed_net_proxy_bps", "shorter_net_proxy_bps", "longer_net_proxy_bps"):
                if event.get(field) is not None and c[field] is not None:
                    event[field] = float(event[field]) - float(c[field]) + d
        stats = {}
        for split in ("observation", "replication", "validation"):
            lane = [event for event in events if event["split"] == split]
            stats[split] = {
                "directional_excess": summarize([event["directional_excess_bps"] for event in lane]),
                "net_proxy": summarize([event["net_proxy_bps"] for event in lane]),
            }
        record["stats"] = stats
        output["records"].append(record)
    return output


def representative_full_lane_recovery(stage5: Mapping[str, Any]) -> dict[str, Any]:
    family_ids: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for record in stage5.get("records", []):
        hid = str(record["hypothesis"]["hypothesis_id"])
        family = str(record["hypothesis"]["family"])
        n = int(record["stats"]["replication"]["directional_excess"]["n"])
        family_ids[family].append((hid, n))
    planted = set()
    for family in sorted(family_ids):
        values = family_ids[family]
        median_n = float(np.median([n for _, n in values]))
        hid, _ = min(values, key=lambda item: (abs(item[1] - median_n), item[0]))
        planted.add(hid)
    results = []
    for delta in PLANT_DELTAS_BPS:
        synthetic = _synthetic_stage5_for_full_lane(stage5, planted, delta)
        screen = structural_screen_v3(synthetic)
        wfa = validation_and_wfa(synthetic, screen)
        robust = robustness(synthetic, wfa)
        results.append(
            {
                "plant_bps": delta,
                "planted_hypotheses": len(planted),
                "stage6_survivors": len(screen.get("survivor_hypothesis_ids", [])),
                "stage7_validation_wfa_survivors": len(wfa.get("survivor_hypothesis_ids", [])),
                "stage8_robustness_survivors": len(robust.get("survivor_hypothesis_ids", [])),
                "stage8_survivor_ids": list(robust.get("survivor_hypothesis_ids", [])),
            }
        )
    return {
        "mode": "one deterministic median-n representative per family; non-plants centered to zero",
        "representative_ids": sorted(planted),
        "results": results,
        "unopened_test_run": False,
    }


def build_calibration_report(payload: Mapping[str, Any]) -> str:
    actual = payload["actual_gate_attribution"]
    sparse = payload["sparse_planted_edge_recovery"]["results"]
    full_lane = payload["representative_full_lane_recovery"]["results"]
    null = payload["null_session_sign_flip"]
    mean_diag = payload["mean_targeting_diagnostic"]
    lines = [
        "# PR #806 Certifier Calibration — Initial Authority",
        "",
        "This is a calibration of the frozen certifier, not a strategy search and not a re-evaluation of any failed near miss.",
        "The sealed 63-session final tail is not loaded or scored.",
        "",
        "## Frozen input authority",
        "",
        f"- Artifact SHA-256: `{payload['artifact_sha256']}`",
        f"- Stage-6 semantic SHA-256: `{EXPECTED_STAGE6_SEMANTIC_SHA256}`",
        f"- Hypotheses: {actual['hypothesis_count']}",
        "",
        "## Actual #806 attrition",
        "",
        f"- Replication CI90 lower bound > 0: {actual['gate_pass_counts'].get('replication_ci90_lower_positive', 0)} / 648",
        f"- All non-BH Stage-6 gates passed: {actual['all_non_bh_gates_passed_count']} / 648",
        f"- BH q <= 2.5%: {actual['gate_pass_counts'].get('campaign_global_bh_q_le_2_5pct', 0)} / 648",
        f"- Minimum observed BH q: {actual['minimum_bh_q']:.6f}",
        "",
        "## Sparse planted-edge power (18 true hypotheses per world)",
        "",
        "| Plant | Mean recall | Median recall | P10–P90 | Mean false positives |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in sparse:
        lines.append(
            f"| +{row['plant_bps']:.0f} bps | {row['mean_recall']:.1%} | {row['median_recall']:.1%} | "
            f"{row['recall_p10']:.1%}–{row['recall_p90']:.1%} | {row['mean_false_positives']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Representative full-lane recovery (Stages 6 → 8)",
            "",
            "| Plant | Stage 6 | Stage 7 | Stage 8 |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in full_lane:
        lines.append(
            f"| +{row['plant_bps']:.0f} bps | {row['stage6_survivors']}/18 | "
            f"{row['stage7_validation_wfa_survivors']}/18 | {row['stage8_robustness_survivors']}/18 |"
        )
    lines.extend(
        [
            "",
            "## Null calibration",
            "",
            f"- Null worlds: {null['worlds']}",
            f"- Worlds with any BH pass: {null['worlds_with_any_bh_pass']}",
            f"- Full Stage-6 false positives: {null['full_stage6_false_positive_count']}",
            f"- Full Stage-6 false-positive rate per world: {null['full_stage6_false_positive_rate_per_world']:.3%}",
            "",
            "## Mean-targeting diagnostic",
            "",
            f"- Raw mean-bootstrap p < 0.05: {mean_diag['raw_p_lt_0_05']} / 648",
            f"- BH q <= 10%: {mean_diag['bh_q_le_0_10']} / 648",
            f"- BH q <= 5%: {mean_diag['bh_q_le_0_05']} / 648",
            f"- BH q <= 2.5%: {mean_diag['bh_q_le_0_025']} / 648",
            f"- Minimum mean-bootstrap BH q: {mean_diag['minimum_bh_q']:.6f}",
            "",
            "## Interpretation",
            "",
            "1. The certifier is not an always-fail implementation: large planted effects are recoverable.",
            "2. Sparse +2 bps effects are effectively undetectable under the current 648-test campaign, and +5 bps power is very low.",
            "3. Null false positives are tightly controlled under the session sign-flip diagnostic.",
            "4. Replacing the hit-rate sign p-value with a mean-targeting bootstrap p-value does not rescue the real #806 corpus after BH correction; the sign-test mismatch is real but is not the sole cause of the zero-survivor result.",
            "5. Therefore the current negative result mixes genuine weak evidence with a materially underpowered sparse-edge detection regime. It should not be interpreted as proof that no economically modest edge exists.",
            "6. This calibration does not authorize relaxing #806, promoting its near misses, opening the sealed tail, or changing strategy/live authority.",
            "",
            "## Authority",
            "",
            f"`{payload['principal_verdict']}`",
            "",
        ]
    )
    return "\n".join(lines)


def run_calibration(
    artifact_zip: Path,
    sparse_trials: int = 200,
    null_worlds: int = 1000,
) -> dict[str, Any]:
    stage5, stage6, final = load_authoritative_artifact(artifact_zip)
    payload = {
        "schema_version": 1,
        "campaign": "pr806_certifier_calibration_v1",
        "source_campaign": "autonomous_structural_edge_exhaustion_v1",
        "artifact_sha256": file_sha256(artifact_zip),
        "source_final_authority": final,
        "sealed_unopened_loaded": False,
        "sealed_unopened_scored": False,
        "actual_gate_attribution": actual_gate_attribution(stage6),
        "dense_planted_edge_recovery": dense_planted_edge_recovery(stage5),
        "sparse_planted_edge_recovery": sparse_planted_edge_recovery(stage5, trials=sparse_trials),
        "mean_targeting_diagnostic": mean_targeting_diagnostic(stage5),
        "asymmetric_payoff_control": asymmetric_payoff_control(),
        "null_session_sign_flip": null_session_sign_flip_calibration(stage5, worlds=null_worlds),
        "representative_full_lane_recovery": representative_full_lane_recovery(stage5),
        "promotion_authorized": False,
        "threshold_relaxation_authorized": False,
        "failed_near_miss_rescue_authorized": False,
        "principal_verdict": "PR806_CERTIFIER_FUNCTIONAL_BUT_SPARSE_MODEST_EDGE_DETECTION_UNDERPOWERED",
    }
    payload["semantic_sha256"] = digest(payload)
    return payload
