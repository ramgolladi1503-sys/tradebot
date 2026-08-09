#!/usr/bin/env python3
"""Audit registered strategy implementations for structural integrity.

This audit answers a different question from profitability: does the implementation
faithfully and safely represent the strategy contract it claims to implement?
It is read-only and never grants runtime or broker authority.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.strategy_spec import build_default_strategy_specs

FORBIDDEN_CALL_TOKENS = {
    "place_order", "submit_order", "cancel_order", "modify_order", "exit_order",
    "broker_api", "kite.place_order", "upstox.place_order",
}

SEMANTIC_MARKERS: dict[str, tuple[str, ...]] = {
    "vwap_state": ("vwap",),
    "trend_confirmation": ("trend",),
    "session_state": ("session", "opening"),
    "structure_state": ("structure", "support", "resistance", "orb_"),
    "anchor_state": ("anchor", "support", "resistance", "vwap"),
    "retracement_state": ("pullback", "retrace", "retracement"),
    "mean_reversion_anchor": ("vwap", "mean", "anchor", "support", "resistance"),
    "oscillator_confirmation": ("oscillator", "rsi", "zscore", "z_score", "stoch"),
    "cross_asset_health": ("cross_asset", "pair", "spread"),
    "spread_truth": ("spread",),
    "beta_truth": ("beta",),
    "cointegration_truth": ("cointegration", "coint"),
    "leg_freshness_a": ("fresh", "timestamp", "age"),
    "leg_freshness_b": ("fresh", "timestamp", "age"),
}

TEMPORAL_POLICIES: dict[str, tuple[str, ...]] = {
    "opening_range_retest": ("completed_bar_history", "breakout", "retest", "continuation"),
    "trend_pullback": ("completed_bar_history", "pullback", "trigger"),
    "compression_breakout": ("completed_bar_history", "compression", "breakout"),
    "vwap_reclaim": ("completed_bar_history", "reclaim", "hold"),
    "failed_breakout_trap": ("completed_bar_history", "breakout", "trap"),
}

META_FAMILIES = {"ENSEMBLE", "PRO_STRATEGY"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_path(root: Path, dotted: str) -> Path:
    return root.joinpath(*dotted.split(".")).with_suffix(".py")


def ast_facts(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    calls: set[str] = set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name): calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                parts=[]; cur: Any = fn
                while isinstance(cur, ast.Attribute): parts.append(cur.attr); cur=cur.value
                if isinstance(cur, ast.Name): parts.append(cur.id)
                calls.add(".".join(reversed(parts)))
        elif isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return {"functions": sorted(funcs), "calls": sorted(calls), "imports": sorted(imports)}


def marker_present(text: str, markers: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in markers)


def audit_spec(root: Path, spec: Any) -> dict[str, Any]:
    path = module_path(root, spec.module_path)
    findings: list[dict[str, str]] = []
    if not path.exists():
        return {
            "strategy_id": spec.strategy_id, "name": spec.name, "family": spec.family,
            "module_path": spec.module_path, "callable_name": spec.callable_name,
            "verdict": "NOT_IMPLEMENTING_CLAIMED_STRATEGY",
            "findings": [{"severity":"CRITICAL","code":"MODULE_MISSING","detail":str(path)}],
            "runtime_authority":"NONE", "broker_actions_allowed":False,
        }
    source = path.read_text(encoding="utf-8")
    facts = ast_facts(source)
    if spec.callable_name not in facts["functions"]:
        findings.append({"severity":"CRITICAL","code":"CALLABLE_MISSING","detail":spec.callable_name})

    bad_calls = sorted(c for c in facts["calls"] if any(tok in c.lower() for tok in FORBIDDEN_CALL_TOKENS))
    if bad_calls:
        findings.append({"severity":"CRITICAL","code":"BROKER_OR_ORDER_CALL_PRESENT","detail":",".join(bad_calls)})

    semantic_missing=[]
    for key in spec.required_evidence_keys:
        markers = SEMANTIC_MARKERS.get(key)
        if markers and not marker_present(source, markers):
            semantic_missing.append(key)
    for key in semantic_missing:
        findings.append({"severity":"MAJOR","code":"REQUIRED_EVIDENCE_NOT_CONSUMED","detail":key})

    temporal_policy = TEMPORAL_POLICIES.get(spec.strategy_id)
    if temporal_policy:
        for marker in temporal_policy:
            if marker.lower() not in source.lower():
                findings.append({"severity":"MAJOR","code":"TEMPORAL_CONTRACT_MARKER_MISSING","detail":marker})

    if spec.family in META_FAMILIES:
        verdict = "STRUCTURALLY_VALID_WITH_LIMITATIONS" if not any(f["severity"]=="CRITICAL" for f in findings) else "STRUCTURAL_REPAIR_REQUIRED"
    elif any(f["severity"]=="CRITICAL" for f in findings):
        verdict = "NOT_IMPLEMENTING_CLAIMED_STRATEGY"
    elif any(f["severity"]=="MAJOR" for f in findings):
        verdict = "STRUCTURAL_REPAIR_REQUIRED"
    elif temporal_policy:
        verdict = "STRUCTURALLY_VALID_WITH_LIMITATIONS"
        findings.append({"severity":"INFO","code":"BEHAVIORAL_CAUSALITY_PROBE_REQUIRED","detail":"static contract passed; native adversarial probe still required"})
    else:
        verdict = "UNKNOWN"
        findings.append({"severity":"INFO","code":"BEHAVIORAL_INTENT_PROBE_REQUIRED","detail":"generic static audit cannot prove intent fidelity"})

    return {
        "strategy_id": spec.strategy_id,
        "name": spec.name,
        "family": spec.family,
        "module_path": spec.module_path,
        "callable_name": spec.callable_name,
        "source_path": str(path),
        "source_sha256": sha256(path),
        "required_evidence_keys": list(spec.required_evidence_keys),
        "verdict": verdict,
        "findings": findings,
        "ast": facts,
        "runtime_authority":"NONE",
        "broker_actions_allowed":False,
    }


def run(repo_root: Path) -> dict[str, Any]:
    specs = build_default_strategy_specs()
    rows = [audit_spec(repo_root, s) for s in specs]
    counts: dict[str,int] = {}
    for r in rows: counts[r["verdict"]] = counts.get(r["verdict"],0)+1
    return {
        "schema_version":"tradebot-strategy-structural-audit-v1",
        "status":"STRUCTURAL_AUDIT_COMPLETE_STATIC_PHASE",
        "registered_strategy_count":len(specs),
        "verdict_counts":counts,
        "strategies":rows,
        "profitability_evaluated":False,
        "certification":"NOT_CERTIFIED",
        "runtime_authority":"NONE",
        "broker_actions_allowed":False,
    }


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--output", default="research/hypotheses/strategy_structural_audit/registered_strategy_structural_audit.json")
    a=p.parse_args(argv)
    root=Path(a.repo_root).resolve(); result=run(root)
    out=root/a.output; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "registered_strategy_count":result["registered_strategy_count"],
        "verdict_counts":result["verdict_counts"],
        "output":str(out),
        "runtime_authority":"NONE"
    },indent=2,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
