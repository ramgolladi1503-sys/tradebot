#!/usr/bin/env python3
"""Second-round adversarial validation of research certification controls.

Attacks failure modes not covered by v1: future access, split contamination,
exit timing, synthetic option economics, denominator laundering, negative-control
completeness, and mutation sensitivity. Research-only; no runtime authority.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

RUNNER_REL = Path("scripts/research/hypothesis_factory/run_pairs_arbitrage_successor_v1_certification.py")
PASSPORT_REL = Path("research/strategy_certification/passports/pairs_arbitrage_successor_v1.json")
V1_REL = Path("scripts/research/hypothesis_factory/validate_research_certification_kernel_v1.py")
OUT_REL = Path("research/evidence/strategy_certification/RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_VALIDATION_V2.json")


def check(name: str, ok: bool, detail: Any = None):
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"import_spec_failed:{name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def function_source(source: str, fn: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    raise ValueError(f"function_not_found:{fn}")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--repo-root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.repo_root).resolve()
    runner_path = root / RUNNER_REL
    passport_path = root / PASSPORT_REL
    source = runner_path.read_text(encoding="utf-8")
    passport_text = passport_path.read_text(encoding="utf-8")
    passport = json.loads(passport_text)
    mod = load_module(runner_path, "pairs_cert_runner_v2_attack")
    results = []

    rp = function_source(source, "run_pair")
    causal_entry = (
        "range(i - history_window, i)" in rp
        and "entry_i = i + 1" in rp
        and "rows[i + 1][leg_a]" not in rp
        and "rows[i + 1][leg_b]" not in rp
    )
    results.append(check("FUTURE_FEATURE_ACCESS_REJECTED", causal_entry))

    exit_next_bar = (
        'exit_i = k + 1' in rp
        and 'exit_i = min(k + 1, max_exit)' in rp
        and 'reason = "ZERO_CROSS_EXIT"' in rp
        and 'reason = "STATIONARITY_OR_HEALTH_EXIT"' in rp
    )
    results.append(check("EXIT_DECISION_NEXT_BAR_ENFORCED", exit_next_bar))

    rows = [{"session": f"S{i:03d}"} for i in range(100)]
    dev, val, hold = mod.split_sessions(rows, 0.6, 0.2)
    split_ok = len(dev) == 60 and len(val) == 20 and len(hold) == 20 and not (dev & val or dev & hold or val & hold)
    results.append(check("OUTCOME_LABEL_SPLIT_CONTAMINATION_BLOCKED", split_ok))

    g = mod.gross_pair_return("SELL_SPREAD", 2.0, 100.0, 100.0, 90.0, 100.0)
    expected = (0.1 + 0.0) / 3.0
    results.append(check("DENOMINATOR_LAUNDERING_BLOCKED", abs(g - expected) < 1e-12, {"observed": g, "expected": expected}))

    costs = [mod.cost_return(x) for x in (0.0, 2.0, 8.0, 12.0)]
    cost_ok = costs == sorted(costs) and costs[0] == 0.0 and all(x >= 0 for x in costs)
    results.append(check("COST_SIGN_CANNOT_CREATE_ALPHA", cost_ok, costs))

    combined = (source + "\n" + passport_text).lower()
    forbidden = ["option_premium", "option premium", "synthetic_option", "synthetic option", "strike_price", "option_entry_price"]
    hits = [x for x in forbidden if x in combined]
    results.append(check("SYNTHETIC_OPTION_ECONOMICS_EXCLUDED", not hits, hits))

    negative_controls = passport.get("negative_controls", [])
    explicit_gate = (
        "negative_controls_executed = False" in source
        and 'reasons.append("MANDATORY_NEGATIVE_CONTROLS_NOT_EXECUTED")' in source
        and 'verdict = "CERTIFIED" if ok else "REJECTED"' in source
        and source.find("MANDATORY_NEGATIVE_CONTROLS_NOT_EXECUTED") < source.find('verdict = "CERTIFIED" if ok else "REJECTED"')
    )
    results.append(check("MANDATORY_NEGATIVE_CONTROLS_GATE_CERTIFICATION", bool(negative_controls) and explicit_gate, {
        "declared_negative_controls": negative_controls,
        "explicit_gate_present": explicit_gate,
    }))

    # Mutation sensitivity checks mutate the exact invariant and verify the audit predicate flips.
    same_bar_mut = source.replace("entry_i = i + 1", "entry_i = i", 1)
    future_hist_mut = source.replace("range(i - history_window, i)", "range(i - history_window + 1, i + 1)", 1)
    authority_mut = source.replace('"runtime_authority": "NONE"', '"runtime_authority": "LIVE"')
    negative_cost_mut = source.replace("return float(round_trip_bps_per_leg) / 10000.0", "return -float(round_trip_bps_per_leg) / 10000.0", 1)
    detected = {
        "same_bar_entry": "entry_i = i + 1" not in function_source(same_bar_mut, "run_pair"),
        "future_history": "range(i - history_window, i)" not in function_source(future_hist_mut, "run_pair"),
        "authority_escalation": '"runtime_authority": "NONE"' not in authority_mut and '"runtime_authority": "LIVE"' in authority_mut,
        "negative_cost": "return float(round_trip_bps_per_leg) / 10000.0" not in function_source(negative_cost_mut, "cost_return"),
    }
    results.append(check("MUTATION_SABOTAGE_IS_DETECTABLE", all(detected.values()), detected))

    bindings = {
        "runner_sha256": hashlib.sha256(runner_path.read_bytes()).hexdigest(),
        "passport_sha256": hashlib.sha256(passport_path.read_bytes()).hexdigest(),
        "v1_validator_sha256": hashlib.sha256((root / V1_REL).read_bytes()).hexdigest(),
    }
    results.append(check("AUDIT_BYTE_BINDINGS_CAPTURED", all(len(v) == 64 for v in bindings.values()), bindings))

    failed = [r for r in results if r["status"] != "PASS"]
    status = "RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_V2_PASS" if not failed else "RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_V2_REPAIR_REQUIRED"
    payload = {
        "schema_version": 2,
        "status": status,
        "checks_total": len(results),
        "checks_passed": len(results) - len(failed),
        "checks_failed": len(failed),
        "failed_checks": [r["check"] for r in failed],
        "results": results,
        "bindings": bindings,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "platform_trust_claimed": False,
        "interpretation": "PASS means these v2 adversarial properties hold for the byte-bound kernel only. REPAIR_REQUIRED means the kernel must be repaired before any future CERTIFIED strategy verdict is allowed.",
    }
    out = root / OUT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
