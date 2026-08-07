from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

EXPECTED_SHA256 = "b00f8aeebc005112c6632a580a3123303c4aa1be64cc6158bfe244a55bb65b4a"
EXPECTED_HYPOTHESES = 648
Q = 0.025
DELTAS = (2.0, 5.0, 8.0, 15.0)
SEED = 20260808
BOOTSTRAP_SEED = 20260807


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    digest = sha256(path)
    if digest != EXPECTED_SHA256:
        raise ValueError(f"artifact digest mismatch: {digest}")
    with zipfile.ZipFile(path) as zf:
        stage5 = json.loads(zf.read("stage5_development_outcomes.json"))
        stage6 = json.loads(zf.read("stage6_structural_screen.json"))
        stage9 = json.loads(zf.read("stage9_final_unopened.json"))
    if len(stage5["records"]) != EXPECTED_HYPOTHESES or len(stage6["results"]) != EXPECTED_HYPOTHESES:
        raise ValueError("unexpected hypothesis count")
    forbidden = {
        str(event.get("split"))
        for record in stage5["records"]
        for event in record["events"]
        if str(event.get("split")) not in {"observation", "replication", "validation"}
    }
    if forbidden:
        raise ValueError(f"unauthorized splits: {sorted(forbidden)}")
    if stage9.get("unopened_sessions_scored") is not False or stage9.get("tested_hypothesis_ids") or stage9.get("results"):
        raise ValueError("sealed Stage-9 boundary violated")
    return digest, stage5, stage6, stage9


def bh_qvalues(values):
    p = np.asarray(values, dtype=float)
    order = np.argsort(p)
    ranked = p[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1, dtype=float)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    out = np.empty_like(adjusted)
    out[order] = np.clip(adjusted, 0.0, 1.0)
    return out


def stage6_attribution(stage6):
    rows = stage6["results"]
    gates = sorted(rows[0]["gates"])
    counts = {gate: sum(bool(row["gates"][gate]) for row in rows) for gate in gates}
    non_bh = [gate for gate in gates if gate != "campaign_global_bh_q_le_2_5pct"]
    return {
        "hypotheses": len(rows),
        "gate_pass_counts": counts,
        "all_non_bh": sum(all(row["gates"][gate] for gate in non_bh) for row in rows),
        "full_pass": sum(bool(row["passed"]) for row in rows),
        "min_sign_p": min(float(row["replication"]["sign_p"]) for row in rows),
        "min_bh_q": min(float(row["bh_q"]) for row in rows),
    }


def centered_cache(stage5):
    rows = []
    for record in stage5["records"]:
        hid = str(record["hypothesis"]["hypothesis_id"])
        family = str(record["hypothesis"]["family"])
        obs0 = np.asarray([e["directional_excess_bps"] for e in record["events"] if e["split"] == "observation"], float)
        rep0 = np.asarray([e["directional_excess_bps"] for e in record["events"] if e["split"] == "replication"], float)
        original = record["stats"]["replication"]["directional_excess"]
        cache = {}
        for delta in (0.0, *DELTAS):
            obs = obs0 - obs0.mean() + delta
            rep = rep0 - rep0.mean() + delta
            hits = int(np.sum(rep > 0.0))
            p = float(binomtest(hits, len(rep), 0.5, alternative="greater").pvalue)
            ci_lower = float(original["ci90"][0]) - float(original["mean_bps"]) + delta
            non_bh = bool(
                len(obs) >= 20
                and abs(float(obs.mean())) >= 2.0 - 1e-12
                and len(rep) >= 10
                and float(rep.mean()) >= 2.0 - 1e-12
                and hits / len(rep) >= 0.55
                and ci_lower > 0.0
            )
            cache[float(delta)] = (p, non_bh)
        rows.append((hid, family, cache))
    return rows


def planted_recovery(stage5, trials=200):
    rows = centered_cache(stage5)
    ids = [hid for hid, _, _ in rows]
    by_id = {hid: cache for hid, _, cache in rows}
    family_ids = defaultdict(list)
    for hid, family, _ in rows:
        family_ids[family].append(hid)
    families = sorted(family_ids)
    dense = []
    for delta in DELTAS:
        q = bh_qvalues([by_id[hid][delta][0] for hid in ids])
        recovered = sum(float(qv) <= Q and by_id[hid][delta][1] for hid, qv in zip(ids, q))
        dense.append({"delta_bps": delta, "bh_pass": int(np.sum(q <= Q)), "recovered": recovered, "recall": recovered / len(ids)})
    rng = np.random.default_rng(SEED)
    sparse = []
    for delta in DELTAS:
        recalls, fps = [], []
        for _ in range(trials):
            planted = {str(rng.choice(family_ids[family])) for family in families}
            q = bh_qvalues([by_id[hid][delta if hid in planted else 0.0][0] for hid in ids])
            recovered = {
                hid for hid, qv in zip(ids, q)
                if float(qv) <= Q and by_id[hid][delta if hid in planted else 0.0][1]
            }
            recalls.append(len(recovered & planted) / len(planted))
            fps.append(len(recovered - planted))
        sparse.append({
            "delta_bps": delta,
            "mean_recall": float(np.mean(recalls)),
            "median_recall": float(np.median(recalls)),
            "p10": float(np.quantile(recalls, 0.10)),
            "p90": float(np.quantile(recalls, 0.90)),
            "mean_false_positives": float(np.mean(fps)),
            "max_false_positives": int(max(fps)),
        })
    return {"dense": dense, "sparse": sparse}


def bootstrap_ci(values):
    arr = np.asarray(values, float)
    rng = np.random.default_rng(BOOTSTRAP_SEED + len(arr))
    indexes = rng.integers(0, len(arr), size=(2000, len(arr)))
    means = arr[indexes].mean(axis=1)
    return np.quantile(means, [0.05, 0.95])


def null_worlds(stage5, worlds=1000):
    dates = sorted({str(e["session_date"]) for r in stage5["records"] for e in r["events"] if e["split"] in {"observation", "replication"}})
    date_idx = {date: i for i, date in enumerate(dates)}
    specs = []
    for record in stage5["records"]:
        obs = [e for e in record["events"] if e["split"] == "observation"]
        rep = [e for e in record["events"] if e["split"] == "replication"]
        specs.append((
            str(record["hypothesis"]["hypothesis_id"]),
            np.asarray([e["raw_excess_bps"] for e in obs], float), np.asarray([date_idx[str(e["session_date"])] for e in obs]),
            np.asarray([e["raw_excess_bps"] for e in rep], float), np.asarray([date_idx[str(e["session_date"])] for e in rep]),
        ))
    rng = np.random.default_rng(SEED)
    signs = rng.choice(np.asarray([-1.0, 1.0]), size=(worlds, len(dates)))
    p = np.empty((worlds, len(specs)), float)
    pre = np.zeros((worlds, len(specs)), bool)
    for j, (_, ov, oi, rv, ri) in enumerate(specs):
        ow, rw = signs[:, oi] * ov, signs[:, ri] * rv
        direction = np.where(ow.mean(axis=1) >= 0.0, 1.0, -1.0)
        od, rd = ow * direction[:, None], rw * direction[:, None]
        hits = (rd > 0.0).sum(axis=1)
        n = rd.shape[1]
        p[:, j] = [binomtest(int(h), n, 0.5, alternative="greater").pvalue for h in hits]
        pre[:, j] = (np.abs(od.mean(axis=1)) >= 2.0) & (rd.mean(axis=1) >= 2.0) & ((hits / n) >= 0.55)
    worlds_any = total_bh = full_fp = 0
    for world in range(worlds):
        q = bh_qvalues(p[world])
        mask = q <= Q
        worlds_any += int(np.any(mask))
        total_bh += int(np.sum(mask))
        for j in np.flatnonzero(mask & pre[world]):
            _, ov, oi, rv, ri = specs[int(j)]
            ow, rw = signs[world, oi] * ov, signs[world, ri] * rv
            direction = 1.0 if float(ow.mean()) >= 0.0 else -1.0
            if float(bootstrap_ci(rw * direction)[0]) > 0.0:
                full_fp += 1
    return {"worlds": worlds, "worlds_with_any_bh": worlds_any, "total_bh_passes": total_bh, "full_stage6_false_positives": full_fp}


def mean_targeting(stage5):
    ps = []
    for record in stage5["records"]:
        arr = np.asarray([e["directional_excess_bps"] for e in record["events"] if e["split"] == "replication"], float)
        observed = float(arr.mean())
        centered = arr - observed
        rng = np.random.default_rng(BOOTSTRAP_SEED + len(arr))
        idx = rng.integers(0, len(arr), size=(2000, len(arr)))
        null_means = centered[idx].mean(axis=1)
        ps.append(float((1 + np.sum(null_means >= observed)) / 2001))
    q = bh_qvalues(ps)
    p = np.asarray(ps)
    return {"min_p": float(p.min()), "min_q": float(q.min()), "p_lt_005": int(np.sum(p < 0.05)), "p_lt_0025": int(np.sum(p < 0.025)), "q_le_010": int(np.sum(q <= 0.10)), "q_le_005": int(np.sum(q <= 0.05)), "q_le_0025": int(np.sum(q <= 0.025))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    digest, stage5, stage6, stage9 = load(args.artifact)
    result = {
        "artifact_sha256": digest,
        "stage6": stage6_attribution(stage6),
        "stage9_unopened_scored": stage9["unopened_sessions_scored"],
        "planted_recovery": planted_recovery(stage5),
        "null_worlds": null_worlds(stage5),
        "mean_targeting": mean_targeting(stage5),
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
