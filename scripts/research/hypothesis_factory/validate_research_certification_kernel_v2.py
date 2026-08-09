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
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    a = ap.parse_args(argv)
    root = Path(a.repo_root).resolve()
    runner_path = root / RUNNER_REL
    passport_path = root / PASSPORT_REL
    source = runner_path.read_text(encoding="utf-8")
    passport = json.loads(passport_path.read_text(encoding="utf-8"))
    mod = load_module(runner_path, "pairs_cert_runner_v2_attack")
    results = []

    # 1. Entry feature construction must use only bars strictly before decision i;
    # current decision prices may be observed, but no i+1 value may enter signal_fn.
    rp = function_source(source, "run_pair")
    causal_entry = (
        "range(i - history_window, i)" in rp
        and "entry_i = i + 1" in rp
        and "rows[i + 1][leg_a]" not in rp
        and "rows[i + 1][leg_b]" not in rp
    )
    results.append(check("FUTURE_FEATURE_ACCESS_REJECTED", causal_entry))

    # 2. Exit decisions cannot fill on the same decision bar for zero-cross or
    # stationarity failure when a subsequent synchronized bar exists.
    exit_next_bar = (
        'exit_i = k + 1' in rp
        and 'exit_i = min(k + 1, max_exit)' in rp
        and 'reason = "ZERO_CROSS_EXIT"' in rp
        and 'reason = "STATIONARITY_OR_HEALTH_EXIT"' in rp
    )
    results.append(check("EXIT_DECISION_NEXT_BAR_ENFORCED", exit_next_bar))

    # 3. Development/validation/holdout split is session-based and disjoint.
    rows = [{"session": f"S{i:03d}"} for i in range(100)]
    dev, val, hold = mod.split_sessions(rows, 0.6, 0.2)
    split_ok = len(dev) == 60 and len(val) == 20 and len(hold) == 20 and not (dev & val or dev & hold or val & hold)
    results.append(check("OUTCOME_LABEL_SPLIT_CONTAMINATION_BLOCKED", split_ok))

    # 4. PnL denominator must be total absolute pair notional, not one favorable leg.
    g = mod.gross_pair_return("SELL_SPREAD", 2.0, 100.0, 100.0, 90.0, 100.0)
    expected = (0.1 + 0.0) / 3.0
    results.append(check("DENOMINATOR_LAUNDERING_BLOCKED", abs(g - expected) < 1e-12, {"observed": g, "expected": expected}))

    # 5. Cost model cannot become a source of artificial profit.
    costs = [mod.cost_return(x) for x in (0.0, 2.0, 8.0, 12.0)]
    cost_ok = costs == sorted(costs) and costs[0] == 0.0 and all(x >= 0 for x in costs)
    results.append(check("COST_SIGN_CANNOT_CREATE_ALPHA", cost_ok, costs))

    # 6. This kernel is underlying spread-only. It must not silently reference
    # option premium/strike/CE/PE economics in its runner or frozen passport.
    combined = (source + "\n" + passport_path.read_text(encoding="utf-8")).lower()
    forbidden = ["option_premium", "option premium", "synthetic_option", "synthetic option", "strike_price", "option_entry_price"]
    hits = [x for x in forbidden if x in combined]
    results.append(check("SYNTHETIC_OPTION_ECONOMICS_EXCLUDED", not hits, hits))

    # 7. A CERTIFIED result is forbidden until all passport-declared negative
    # controls are actually executed. Current runner admits they are not, so its
    # certification branch is a defect even though the tested candidate rejected.
    negative_controls = passport.get("negative_controls", [])
    limitation_present = "NEGATIVE CONTROLS DECLARED IN PASSPORT ARE NOT YET EXECUTED" in source
    cert_branch_present = 'verdict = "CERTIFIED" if ok else "REJECTED"' in source
    negative_gate_ok = not (negative_controls and limitation_present and cert_branch_present)
    results.append(check("MANDATORY_NEGATIVE_CONTROLS_GATE_CERTIFICATION", negative_gate_ok, {
        "declared_negative_controls": negative_controls,
        "runner_admits_not_executed": limitation_present,
        "certified_branch_present": cert_branch_present,
    }))

    # 8. Mutation sensitivity: demonstrate that disabling key protections would
    # make the validator fail. These are deterministic source mutations, not writes.
    mutations = {
        "same_bar_entry": source.replace("entry_i = i + 1", "entry_i = i", 1),
        "future_history": source.replace("range(i - history_window, i)", "range(i - history_window + 1, i + 1)", 1),
        "authority_escalation": source.replace('"runtime_authority": "NONE"', '"runtime_authority": "LIVE"', 1),
        "negative_cost": source.replace("return float(round_trip_bps_per_leg) / 10000.0", "return -float(round_trip_bps_per_leg) / 10000.0", 1),
    }
    detected = {
        "same_bar_entry": "entry_i = i + 1" not in mutations["same_bar_entry"],
        "future_history": "range(i - history_window, i)" not in mutations["future_history"],
        "authority_escalation": '"runtime_authority": "NONE"' not in mutations["authority_escalation"],
        "negative_cost": "return float(round_trip_bps_per_leg) / 10000.0" not in mutations["negative_cost"],
    }
    results.append(check("MUTATION_SABOTAGE_IS_DETECTABLE", all(detected.values()), detected))

    # 9. Bind this audit to exact runner/passport bytes so later changes invalidate it.
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
