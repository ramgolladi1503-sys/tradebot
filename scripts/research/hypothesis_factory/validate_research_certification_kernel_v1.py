#!/usr/bin/env python3
"""Adversarial validation for the research certification kernel.

This script attacks the certification machinery rather than any trading strategy.
It is research-only and grants no runtime/broker authority.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

RUNNER_REL = Path("scripts/research/hypothesis_factory/run_pairs_arbitrage_successor_v1_certification.py")
PASSPORT_REL = Path("research/strategy_certification/passports/pairs_arbitrage_successor_v1.json")
DATASET_REL = Path("research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv")
OUT_REL = Path("research/evidence/strategy_certification/RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_VALIDATION_V1.json")


def load_runner(root: Path):
    path = root / RUNNER_REL
    spec = importlib.util.spec_from_file_location("pairs_cert_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("runner_import_spec_failed")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def check(name: str, ok: bool, detail: Any = None) -> dict[str, Any]:
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def synthetic_rows(n: int = 20) -> list[dict[str, Any]]:
    rows = []
    for i in range(n):
        rows.append({
            "timestamp": f"2026-01-01T09:{15+i:02d}:00",
            "session": "2026-01-01",
            "banknifty_open": str(100.0 + i),
            "banknifty_close": str(100.0 + i),
            "nifty_close": str(50.0 + i * 0.5),
            "sensex_close": str(200.0 + i),
        })
    return rows


def stub_signal(price_a, price_b, historical_a=None, historical_b=None, min_zscore=2.0, **kwargs):
    z = 2.5 if float(min_zscore) > 0 else -0.1
    return {
        "direction": "SELL_SPREAD",
        "hedge_ratio": 1.0,
        "spread_truth": {"zscore": z, "current_spread": 1.0},
    }


def run_fail_closed_case(mod, root: Path, passport_payload: dict[str, Any], dataset_path: Path, label: str):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pp = td / "passport.json"
        out = td / "out.json"
        pp.write_text(json.dumps(passport_payload), encoding="utf-8")
        rc = mod.main([
            "--repo-root", str(root),
            "--dataset", str(dataset_path),
            "--passport", str(pp),
            "--output", str(out),
        ])
        payload = json.loads(out.read_text(encoding="utf-8"))
        ok = (
            rc != 0
            and payload.get("status") == "FAIL_CLOSED"
            and payload.get("runtime_authority") == "NONE"
            and payload.get("broker_actions_permitted") is False
            and payload.get("edge_claimed") is False
        )
        return check(label, ok, payload)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    mod = load_runner(root)
    passport_path = root / PASSPORT_REL
    dataset_path = root / DATASET_REL
    passport = json.loads(passport_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    rows = [{"session": f"2026-01-{i:02d}"} for i in range(1, 11)]
    dev, val, hold = mod.split_sessions(rows, 0.6, 0.2)
    ordered_ok = (
        not (dev & val or dev & hold or val & hold)
        and max(dev) < min(val)
        and max(val) < min(hold)
        and len(dev) == 6 and len(val) == 2 and len(hold) == 2
    )
    results.append(check("CHRONOLOGICAL_SPLIT_ISOLATION", ordered_ok, {"dev": sorted(dev), "validation": sorted(val), "holdout": sorted(hold)}))

    srows = synthetic_rows()
    trades = mod.run_pair(
        srows, set(range(len(srows))), "banknifty_close", "nifty_close",
        stub_signal, 9, 2.0, 36.0, 2.0, progress_label="adversarial/no-same-bar",
    )
    same_bar_ok = bool(trades) and trades[0].entry_i == 10 and trades[0].entry_i > 9
    results.append(check("NO_SAME_BAR_ENTRY_FILL", same_bar_ok, {"first_entry_i": trades[0].entry_i if trades else None, "decision_i": 9}))

    base_trades = [mod.Trade(1, 2, "SELL_SPREAD", 1.0, 0.002, 0.0018, "X", "S") for _ in range(5)]
    m2 = mod.metrics_at_cost(base_trades, 2.0, 2.0)
    m8 = mod.metrics_at_cost(base_trades, 8.0, 2.0)
    m12 = mod.metrics_at_cost(base_trades, 12.0, 2.0)
    cost_ok = m2["mean_net_bps"] > m8["mean_net_bps"] > m12["mean_net_bps"]
    results.append(check("COST_STRESS_MONOTONICITY", cost_ok, {"2": m2, "8": m8, "12": m12}))

    with tempfile.TemporaryDirectory() as td:
        bad_ds = Path(td) / "bad.csv"
        data = dataset_path.read_bytes()
        bad_ds.write_bytes(data + b"\nCORRUPTION")
        results.append(run_fail_closed_case(mod, root, passport, bad_ds, "DATASET_HASH_CORRUPTION_FAILS_CLOSED"))

    bad = dict(passport)
    bad["passport_id"] = "TAMPERED"
    results.append(run_fail_closed_case(mod, root, bad, dataset_path, "PASSPORT_ID_TAMPER_FAILS_CLOSED"))

    bad = dict(passport)
    bad["parent_implementation_commit"] = "0" * 40
    results.append(run_fail_closed_case(mod, root, bad, dataset_path, "PARENT_COMMIT_TAMPER_FAILS_CLOSED"))

    source = (root / RUNNER_REL).read_text(encoding="utf-8")
    neighborhood_slice = source[source.find('if ok:'):source.find('verdict =')]
    holdout_selection_ok = (
        'idx_sets["validation"]' in neighborhood_slice
        and 'idx_sets["holdout"]' not in neighborhood_slice
        and 'parameter_neighborhood_validation_only' in source
    )
    results.append(check("HOLDOUT_NOT_USED_FOR_PARAMETER_SELECTION", holdout_selection_ok))

    authority_ok = '"runtime_authority": "NONE"' in source and '"broker_actions_permitted": False' in source
    results.append(check("RESEARCH_AUTHORITY_REMAINS_NONE", authority_ok))

    mandatory = {r["check"] for r in results}
    failed = [r for r in results if r["status"] != "PASS"]
    verdict = "RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_PASS" if not failed else "RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_FAIL"
    payload = {
        "schema_version": 1,
        "status": verdict,
        "checks_total": len(results),
        "checks_passed": len(results) - len(failed),
        "checks_failed": len(failed),
        "mandatory_checks": sorted(mandatory),
        "results": results,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "platform_trust_claimed": False,
        "interpretation": "A PASS validates these adversarial controls for this kernel version only. It is not proof that the full research platform is bug-free.",
    }
    out = root / OUT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
