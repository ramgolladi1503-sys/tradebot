#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

FAMILY = "RAPID_DOWNTREND_CONTINUATION_V1"
MOTIF = "DOWNTREND_CONTINUATION_SWING"
EXPECTED = "RAPID"
EPS = 1e-12


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_jsonl(p: Path):
    out = []
    with p.open(encoding="utf-8") as h:
        for line in h:
            if line.strip():
                out.append(json.loads(line))
    return out


def load_rows(p: Path):
    with p.open(newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    req = {"timestamp", "session", "banknifty_close", "banknifty_low"}
    if not rows or not req.issubset(rows[0]):
        raise ValueError("dataset_schema_mismatch")
    return rows


def finite(x):
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def eq(a, b, eps=EPS):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= eps


def rate(vals, pred):
    xs = [float(x) for x in vals if finite(x)]
    if not xs:
        return None
    return sum(1 for x in xs if pred(x)) / len(xs)


def summarize(vals):
    xs = [float(x) for x in vals if finite(x)]
    if not xs:
        return {"n": 0, "mean": None, "median": None}
    return {"n": len(xs), "mean": mean(xs), "median": median(xs)}


def temporal(m, ts_to_i):
    piv = m.get("pivots") or []
    if len(piv) != 3:
        return None
    try:
        p0 = ts_to_i[piv[0]["pivot_timestamp"]]
        p1 = ts_to_i[piv[1]["pivot_timestamp"]]
        p2 = ts_to_i[piv[2]["pivot_timestamp"]]
        ci = ts_to_i[m["confirmation_timestamp"]]
    except (KeyError, TypeError):
        return None
    if not (p0 <= p1 <= p2 <= ci):
        return None
    return p2 - p0, p2 - p1, ci - p2, ci


def add(checks, name, ok, detail=None):
    checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.repo_root).resolve()

    freeze_p = root / "research/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_FREEZE.json"
    dev_p = root / "research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_DEVELOPMENT.json"
    locked_p = root / "research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_LOCKED_TEST.json"
    consumed_p = root / "research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_LOCKED_TEST_CONSUMED.json"
    motifs_p = root / "research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_motifs.jsonl"
    dev_outcomes_p = root / "research/evidence/market_structure_pattern_atlas_v1/BANKNIFTY_post_confirmation_outcomes_v1.jsonl"
    data_p = root / "research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv"
    runner_p = root / "scripts/research/hypothesis_factory/run_rapid_downtrend_continuation_v1_locked_test.py"
    out_p = root / "research/evidence/strategy_certification/RAPID_DOWNTREND_CONTINUATION_V1_INTEGRITY_VALIDATION.json"

    res = {
        "schema_version": 1,
        "status": "FAIL_CLOSED",
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "research_verdict_changed": False,
    }
    checks = []
    try:
        freeze = json.loads(freeze_p.read_text())
        dev = json.loads(dev_p.read_text())
        locked = json.loads(locked_p.read_text())
        consumed = json.loads(consumed_p.read_text())
        rows = load_rows(data_p)
        motifs = [m for m in load_jsonl(motifs_p) if m.get("motif") == MOTIF]
        dev_outcomes = [o for o in load_jsonl(dev_outcomes_p) if o.get("motif") == MOTIF]

        sessions = sorted({r["session"] for r in rows})
        cut = int(len(sessions) * 0.80)
        characterization = set(sessions[:cut])
        locked_sessions = set(sessions[cut:])
        ts_to_i = {r["timestamp"]: i for i, r in enumerate(rows)}

        add(checks, "SESSION_SPLIT_394_99", len(sessions) == 493 and len(characterization) == 394 and len(locked_sessions) == 99,
            {"total": len(sessions), "characterization": len(characterization), "locked": len(locked_sessions), "first_locked": sessions[cut] if cut < len(sessions) else None})
        add(checks, "SPLIT_DISJOINT", not (characterization & locked_sessions))

        dev_sessions = {o.get("session") for o in dev_outcomes}
        leaked = sorted(s for s in dev_sessions if s in locked_sessions)
        add(checks, "DEVELOPMENT_OUTCOMES_EXCLUDE_LOCKED_SESSIONS", not leaked,
            {"development_sessions_observed": len(dev_sessions), "locked_sessions_found": leaked[:10], "locked_sessions_found_count": len(leaked)})

        definition = next((d for d in freeze.get("definitions", []) if d.get("candidate_id") == EXPECTED), None)
        add(checks, "EXACT_FROZEN_NOMINEE", definition is not None and locked.get("definition") == definition and dev.get("nominated_candidate_id") == EXPECTED and dev.get("advanced_count") == 1,
            {"development_nominee": dev.get("nominated_candidate_id"), "locked_candidate": locked.get("candidate_id"), "definition": definition})

        add(checks, "HASH_BINDINGS_MATCH", dev.get("freeze_sha256") == sha256(freeze_p)
            and locked.get("freeze_sha256") == sha256(freeze_p)
            and dev.get("motifs_sha256") == sha256(motifs_p)
            and locked.get("motifs_sha256") == sha256(motifs_p)
            and dev.get("dataset_sha256") == sha256(data_p)
            and locked.get("dataset_sha256") == sha256(data_p),
            {"freeze_sha256": sha256(freeze_p), "motifs_sha256": sha256(motifs_p), "dataset_sha256": sha256(data_p)})

        add(checks, "CONSUMPTION_MARKER_PRESENT", consumed_p.exists() and consumed.get("locked_test_consumed") is True
            and consumed.get("family_id") == FAMILY and consumed.get("candidate_id") == EXPECTED,
            {"marker": str(consumed_p), "content": consumed})
        runner_text = runner_p.read_text(encoding="utf-8")
        add(checks, "RUNNER_GUARDS_REPEAT_CONSUMPTION", "if seal_p.exists():raise ValueError('LOCKED_TEST_ALREADY_CONSUMED')" in runner_text)

        parent = []
        selected = []
        missing = 0
        for m in motifs:
            ts = m.get("confirmation_timestamp")
            i = ts_to_i.get(ts)
            if i is None:
                missing += 1
                continue
            sess = rows[i]["session"]
            if sess not in locked_sessions:
                continue
            feat = temporal(m, ts_to_i)
            if feat is None:
                continue
            formation, middle_to_second, confirmation_delay, ci = feat
            c0 = float(rows[ci]["banknifty_close"])
            lows, ret6, ret12 = [], None, None
            for j in range(ci + 1, min(len(rows), ci + 13)):
                if rows[j]["session"] != sess:
                    break
                lows.append((float(rows[j]["banknifty_low"]) / c0 - 1.0) * 10000.0)
                if j == ci + 6:
                    ret6 = (float(rows[j]["banknifty_close"]) / c0 - 1.0) * 10000.0
                if j == ci + 12:
                    ret12 = (float(rows[j]["banknifty_close"]) / c0 - 1.0) * 10000.0
            rec = {
                "session": sess,
                "mae": min(lows) if lows else None,
                "ret6": ret6,
                "ret12": ret12,
                "formation": formation,
                "middle_to_second": middle_to_second,
                "confirmation_delay": confirmation_delay,
            }
            parent.append(rec)
            if (formation <= definition["formation_bars_max"]
                and middle_to_second <= definition["middle_to_second_bars_max"]
                and confirmation_delay <= definition["confirmation_delay_bars_max"]):
                selected.append(rec)

        selected_bad_sessions = sorted({x["session"] for x in selected if x["session"] not in locked_sessions})
        add(checks, "LOCKED_SELECTION_CONTAINS_ONLY_LOCKED_SESSIONS", not selected_bad_sessions,
            {"selected": len(selected), "non_locked_selected": selected_bad_sessions})

        p30 = rate([x["mae"] for x in parent], lambda x: x <= -30.0)
        p20 = rate([x["mae"] for x in parent], lambda x: x <= -20.0)
        c30 = rate([x["mae"] for x in selected], lambda x: x <= -30.0)
        c20 = rate([x["mae"] for x in selected], lambda x: x <= -20.0)
        r6 = summarize([x["ret6"] for x in selected])
        r12 = summarize([x["ret12"] for x in selected])

        counts_ok = (len(parent) == locked.get("locked_parent_episodes") and len(selected) == locked.get("locked_candidate_episodes") and missing == locked.get("motifs_missing_timestamp_match"))
        add(checks, "LOCKED_COUNTS_RECOMPUTE", counts_ok,
            {"parent_recomputed": len(parent), "parent_recorded": locked.get("locked_parent_episodes"), "candidate_recomputed": len(selected), "candidate_recorded": locked.get("locked_candidate_episodes"), "missing_recomputed": missing, "missing_recorded": locked.get("motifs_missing_timestamp_match")})

        rates_ok = eq(p30, locked.get("locked_parent_down_30bps_rate")) and eq(p20, locked.get("locked_parent_down_20bps_rate")) and eq(c30, locked.get("locked_candidate_down_30bps_rate")) and eq(c20, locked.get("locked_candidate_down_20bps_rate"))
        add(checks, "LOCKED_RATES_RECOMPUTE", rates_ok,
            {"parent30": p30, "parent20": p20, "candidate30": c30, "candidate20": c20})

        ret_ok = (r6["n"] == locked.get("candidate_ret6_bps", {}).get("n") and eq(r6["mean"], locked.get("candidate_ret6_bps", {}).get("mean")) and eq(r6["median"], locked.get("candidate_ret6_bps", {}).get("median"))
                  and r12["n"] == locked.get("candidate_ret12_bps", {}).get("n") and eq(r12["mean"], locked.get("candidate_ret12_bps", {}).get("mean")) and eq(r12["median"], locked.get("candidate_ret12_bps", {}).get("median")))
        add(checks, "LOCKED_FORWARD_RETURNS_RECOMPUTE", ret_ok, {"ret6": r6, "ret12": r12})

        expected_reasons = []
        if len(selected) < int(freeze["locked_test_policy"]["minimum_locked_episodes"]):
            expected_reasons.append("INSUFFICIENT_LOCKED_EPISODES")
        if c30 is None or c30 < float(dev["parent_down_30bps_rate"]):
            expected_reasons.append("PRIMARY_RATE_BELOW_CHARACTERIZATION_PARENT")
        expected_verdict = "LOCKED_VALIDATION_PASS" if not expected_reasons else "LOCKED_VALIDATION_FAIL"
        add(checks, "VERDICT_RECOMPUTES_FROM_FROZEN_POLICY", locked.get("verdict") == expected_verdict and locked.get("reasons") == expected_reasons,
            {"expected_verdict": expected_verdict, "recorded_verdict": locked.get("verdict"), "expected_reasons": expected_reasons, "recorded_reasons": locked.get("reasons")})

        failed = [c["check"] for c in checks if c["status"] != "PASS"]
        res.update({
            "status": "RAPID_DOWNTREND_INTEGRITY_PASS" if not failed else "RAPID_DOWNTREND_INTEGRITY_REPAIR_REQUIRED",
            "checks_total": len(checks),
            "checks_passed": len(checks) - len(failed),
            "checks_failed": len(failed),
            "failed_checks": failed,
            "checks": checks,
            "locked_test_verdict": locked.get("verdict"),
            "locked_test_reasons": locked.get("reasons"),
            "research_verdict_changed": False,
            "interpretation": "Mechanical integrity audit only. PASS means the recorded one-time locked result reproduces from the frozen definition, session split, motifs, and dataset. It does not upgrade the failed research candidate or certify an edge."
        })
    except Exception as e:
        res["error"] = f"{type(e).__name__}:{e}"

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") == "RAPID_DOWNTREND_INTEGRITY_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
