#!/usr/bin/env python3
"""Certification runner for PAIRS_ARBITRAGE_SUCCESSOR_V1.

Research-only. Fails closed on passport/dataset mismatches. Uses the frozen parent
entry logic and frozen successor economic contract. Does not mutate strategy code
or passport. Holdout is chronological and is never used for parameter selection.

Performance note: expensive neighborhood diagnostics are executed only if the
mandatory base/holdout gates survive. A rejected base candidate is terminal and
needs no parameter-neighborhood work to establish rejection.
"""
from __future__ import annotations

import argparse, csv, hashlib, importlib, json, math, sys, time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

EXPECTED_PASSPORT_ID = "PAIRS_ARBITRAGE_SUCCESSOR_V1"
EXPECTED_DATASET_SHA = "66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32"
EXPECTED_PARENT_COMMIT = "561041b2e11f03283ebca3fd5eb70e6ef6fc1d6d"


def log(msg: str) -> None:
    print(f"[pairs-cert] {msg}", flush=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def f(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    req = {"timestamp", "session", "banknifty_open", "banknifty_close", "nifty_close", "sensex_close"}
    if not rows or not req.issubset(rows[0]):
        raise ValueError("dataset_schema_mismatch")
    return rows


def split_sessions(rows: list[dict[str, Any]], dev_frac: float, val_frac: float):
    sessions = sorted({r["session"] for r in rows})
    n = len(sessions)
    d = int(n * dev_frac)
    v = int(n * val_frac)
    return set(sessions[:d]), set(sessions[d:d + v]), set(sessions[d + v:])


def pct_return(entry: float, exit_: float) -> float:
    return 0.0 if entry <= 0 else (exit_ - entry) / entry


def gross_pair_return(direction: str, beta: float, a0: float, b0: float, a1: float, b1: float) -> float:
    wa, wb = 1.0, abs(beta)
    ra, rb = pct_return(a0, a1), pct_return(b0, b1)
    if direction == "SELL_SPREAD":
        pnl = -wa * ra + abs(beta) * rb
    else:
        pnl = wa * ra - abs(beta) * rb
    denom = wa + wb
    return pnl / denom if denom > 0 else 0.0


def cost_return(round_trip_bps_per_leg: float) -> float:
    # Passport applies equal RT bps to each leg's absolute traded notional.
    # After normalization by total absolute pair notional this is exactly the
    # same scalar return deduction irrespective of beta.
    return float(round_trip_bps_per_leg) / 10000.0


@dataclass
class Trade:
    entry_i: int
    exit_i: int
    direction: str
    beta: float
    gross: float
    net: float
    reason: str
    session: str


def run_pair(rows, idxs, leg_a, leg_b, signal_fn, history_window, min_z, max_hl, cost_bps, progress_label=""):
    trades = []
    i0 = min(idxs) if idxs else 0
    i1 = max(idxs) if idxs else -1
    i = i0 + history_window
    examined = 0
    next_progress = 5000
    started = time.time()

    while i <= i1 - 1:
        if i not in idxs:
            i += 1
            continue
        examined += 1
        if examined >= next_progress:
            log(f"{progress_label}: examined={examined} trades={len(trades)} elapsed={time.time()-started:.1f}s")
            next_progress += 5000

        r = rows[i]
        sess = r["session"]
        hist_idx = [j for j in range(i - history_window, i) if j in idxs]
        if len(hist_idx) != history_window:
            i += 1
            continue
        ha = [f(rows[j][leg_a]) for j in hist_idx]
        hb = [f(rows[j][leg_b]) for j in hist_idx]
        pa, pb = f(r[leg_a]), f(r[leg_b])
        if not all(math.isfinite(x) and x > 0 for x in ha + hb + [pa, pb]):
            i += 1
            continue

        sig = signal_fn(
            pa, pb,
            historical_a=ha,
            historical_b=hb,
            min_zscore=min_z,
            regime="RANGE",
            expiry_context=False,
            leg_a_age_sec=0.0,
            leg_b_age_sec=0.0,
            max_leg_age_sec=5.0,
            cross_asset_health=True,
            max_half_life_periods=max_hl,
        )
        if not sig:
            i += 1
            continue

        entry_i = i + 1
        if entry_i > i1 or entry_i not in idxs:
            i += 1
            continue
        if rows[entry_i]["session"] != sess:
            i += 1
            continue

        beta = float(sig["hedge_ratio"])
        direction = sig["direction"]
        # Matrix has only leader closes, so use next synchronized bar closes for
        # all legs consistently; same-bar entry is forbidden.
        a0 = f(rows[entry_i][leg_a])
        b0 = f(rows[entry_i][leg_b])
        exit_i = None
        reason = None
        entry_z = float(sig["spread_truth"]["zscore"])
        max_exit = min(i1, entry_i + 36)

        for k in range(entry_i, max_exit + 1):
            if k not in idxs or rows[k]["session"] != sess:
                exit_i = k - 1 if k - 1 >= entry_i else entry_i
                reason = "SESSION_EXIT"
                break
            hstart = max(i0, k - history_window)
            hk = [j for j in range(hstart, k) if j in idxs and rows[j]["session"] == sess]
            if len(hk) < 9:
                continue
            hka = [f(rows[j][leg_a]) for j in hk]
            hkb = [f(rows[j][leg_b]) for j in hk]
            cur = signal_fn(
                f(rows[k][leg_a]), f(rows[k][leg_b]),
                historical_a=hka,
                historical_b=hkb,
                min_zscore=0.0,
                regime="RANGE",
                expiry_context=False,
                leg_a_age_sec=0.0,
                leg_b_age_sec=0.0,
                max_leg_age_sec=5.0,
                cross_asset_health=True,
                max_half_life_periods=max_hl,
            )
            if cur is None:
                if k < max_exit:
                    exit_i = k + 1
                    reason = "STATIONARITY_OR_HEALTH_EXIT"
                else:
                    exit_i = k
                    reason = "MAX_HOLD"
                break
            z = float(cur["spread_truth"]["zscore"])
            if z == 0 or (entry_z > 0 and z < 0) or (entry_z < 0 and z > 0):
                exit_i = min(k + 1, max_exit)
                reason = "ZERO_CROSS_EXIT"
                break
            if k == max_exit:
                exit_i = k
                reason = "MAX_HOLD"

        if exit_i is None:
            exit_i = max_exit
            reason = "MAX_HOLD"

        a1 = f(rows[exit_i][leg_a])
        b1 = f(rows[exit_i][leg_b])
        gross = gross_pair_return(direction, beta, a0, b0, a1, b1)
        net = gross - cost_return(cost_bps)
        trades.append(Trade(entry_i, exit_i, direction, beta, gross, net, reason, sess))
        i = exit_i + 1

    log(f"{progress_label}: complete examined={examined} trades={len(trades)} elapsed={time.time()-started:.1f}s")
    return trades


def metrics(trades):
    nets = [t.net for t in trades]
    if not nets:
        return {"trades": 0, "mean_net_bps": None, "win_rate": None, "total_net_bps": None}
    return {
        "trades": len(nets),
        "mean_net_bps": mean(nets) * 10000,
        "win_rate": sum(x > 0 for x in nets) / len(nets),
        "total_net_bps": sum(nets) * 10000,
    }


def metrics_at_cost(trades, target_cost_bps: float, source_cost_bps: float = 2.0):
    delta = cost_return(target_cost_bps) - cost_return(source_cost_bps)
    adjusted = [t.net - delta for t in trades]
    if not adjusted:
        return {"trades": 0, "mean_net_bps": None, "win_rate": None, "total_net_bps": None}
    return {
        "trades": len(adjusted),
        "mean_net_bps": mean(adjusted) * 10000,
        "win_rate": sum(x > 0 for x in adjusted) / len(adjusted),
        "total_net_bps": sum(adjusted) * 10000,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--dataset", default="research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv")
    ap.add_argument("--passport", default="research/strategy_certification/passports/pairs_arbitrage_successor_v1.json")
    ap.add_argument("--output", default="research/evidence/strategy_certification/PAIRS_ARBITRAGE_SUCCESSOR_V1_CERTIFICATION.json")
    a = ap.parse_args(argv)
    root = Path(a.repo_root).resolve()
    ds = root / a.dataset
    pp = root / a.passport
    out = root / a.output
    result = {"status": "FAIL_CLOSED", "runtime_authority": "NONE", "broker_actions_permitted": False, "edge_claimed": False}

    try:
        # Script location is nested; direct execution does not automatically put
        # repository root on sys.path.
        root_text = str(root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)

        p = load_json(pp)
        if p.get("passport_id") != EXPECTED_PASSPORT_ID:
            raise ValueError("passport_id_mismatch")
        if p.get("parent_implementation_commit") != EXPECTED_PARENT_COMMIT:
            raise ValueError("parent_commit_mismatch")
        if p.get("dataset_sha256") != EXPECTED_DATASET_SHA or sha256(ds) != EXPECTED_DATASET_SHA:
            raise ValueError("dataset_hash_mismatch")

        rows = load_rows(ds)
        dev, val, hold = split_sessions(
            rows,
            p["certification_split"]["development_fraction"],
            p["certification_split"]["validation_fraction"],
        )
        sets = {"development": dev, "validation": val, "holdout": hold}
        idx_sets = {name: {i for i, r in enumerate(rows) if r["session"] in sessions} for name, sessions in sets.items()}

        mod = importlib.import_module("strategies.pairs_arbitrage")
        signal_fn = mod.generate_signal
        pairs = [
            ("BANKNIFTY_NIFTY", "banknifty_close", "nifty_close"),
            ("BANKNIFTY_SENSEX", "banknifty_close", "sensex_close"),
        ]

        log(f"dataset verified rows={len(rows)} sessions={len({r['session'] for r in rows})}")
        log("stage 1/2: mandatory base replay + holdout 8bps stress")

        base = {}
        holdout_trades_by_pair = {}
        for name, la, lb in pairs:
            base[name] = {}
            for split in ("development", "validation", "holdout"):
                tr = run_pair(
                    rows, idx_sets[split], la, lb, signal_fn,
                    36, 2.0, 36.0, 2.0,
                    progress_label=f"{name}/{split}/base",
                )
                base[name][split] = metrics(tr)
                if split == "holdout":
                    holdout_trades_by_pair[name] = tr

        stress = {}
        ok = True
        reasons = []
        for name, _, _ in pairs:
            tr = holdout_trades_by_pair[name]
            stress[name] = {}
            for c in [2.0] + [float(x) for x in p["cost_contract"]["stress_round_trip_bps_per_leg"]]:
                stress[name][str(c)] = metrics_at_cost(tr, c, source_cost_bps=2.0)
            hm = base[name]["holdout"]
            sm = stress[name]["8.0"]
            if hm["trades"] < 30:
                ok = False
                reasons.append(f"{name}:INSUFFICIENT_HOLDOUT_TRADES")
            if hm["mean_net_bps"] is None or hm["mean_net_bps"] <= 0:
                ok = False
                reasons.append(f"{name}:NONPOSITIVE_HOLDOUT_MEAN")
            if sm["mean_net_bps"] is None or sm["mean_net_bps"] <= 0:
                ok = False
                reasons.append(f"{name}:FAILS_8BPS_PER_LEG_STRESS")

        neighborhood = {}
        if ok:
            log("stage 2/2: base gates survived; running validation-only parameter neighborhood")
            for name, la, lb in pairs:
                neighborhood[name] = []
                total = (
                    len(p["parameter_neighborhood"]["history_window_bars"])
                    * len(p["parameter_neighborhood"]["min_zscore"])
                    * len(p["parameter_neighborhood"]["max_half_life_periods"])
                )
                ncombo = 0
                for hz in p["parameter_neighborhood"]["history_window_bars"]:
                    for mz in p["parameter_neighborhood"]["min_zscore"]:
                        for mh in p["parameter_neighborhood"]["max_half_life_periods"]:
                            ncombo += 1
                            log(f"{name}: neighborhood {ncombo}/{total} hz={hz} z={mz} hl={mh}")
                            tr = run_pair(
                                rows, idx_sets["validation"], la, lb, signal_fn,
                                int(hz), float(mz), float(mh), 2.0,
                                progress_label=f"{name}/validation/neighborhood-{ncombo}",
                            )
                            neighborhood[name].append({
                                "history_window_bars": hz,
                                "min_zscore": mz,
                                "max_half_life_periods": mh,
                                "metrics": metrics(tr),
                            })
        else:
            log("mandatory base gate failed; skipping expensive neighborhood because candidate is already REJECTED")

        verdict = "CERTIFIED" if ok else "REJECTED"
        result.update({
            "status": "CERTIFICATION_COMPLETE",
            "verdict": verdict,
            "reasons": reasons,
            "dataset_sha256": sha256(ds),
            "passport_sha256": sha256(pp),
            "rows": len(rows),
            "sessions": len({r["session"] for r in rows}),
            "base": base,
            "parameter_neighborhood_validation_only": neighborhood,
            "parameter_neighborhood_skipped_due_terminal_base_rejection": not ok,
            "cost_stress_holdout": stress,
            "limitations": [
                "SYNCHRONIZED MATRIX EXPOSES LEADER CLOSES BUT NOT ALL LEG OPENS; RUNNER USES NEXT-BAR SYNCHRONIZED CLOSES AS CONSISTENT FILL PROXY. THIS IS RESEARCH EVIDENCE, NOT BROKER FILL CERTIFICATION.",
                "NEGATIVE CONTROLS DECLARED IN PASSPORT ARE NOT YET EXECUTED BY THIS RUNNER; ANY OTHERWISE-PASSING RESULT MUST REMAIN NON-CERTIFIED UNTIL THEY PASS.",
            ],
            "runtime_authority": "NONE",
            "broker_actions_permitted": False,
            "edge_claimed": False,
        })
        if verdict == "CERTIFIED":
            result["verdict"] = "REJECTED"
            result["reasons"].append("MANDATORY_NEGATIVE_CONTROLS_NOT_EXECUTED")

    except KeyboardInterrupt:
        result["error"] = "KeyboardInterrupt:operator_cancelled"
        log("cancelled by operator; writing fail-closed partial result")
    except Exception as e:
        result["error"] = f"{type(e).__name__}:{e}"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result.get("status") == "CERTIFICATION_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
