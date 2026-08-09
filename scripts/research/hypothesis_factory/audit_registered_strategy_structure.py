#!/usr/bin/env python3
"""Audit registered strategy implementations for structural integrity.

This audit answers a different question from profitability: does the implementation
faithfully and safely represent the strategy contract it claims to implement?
It is read-only and never grants runtime or broker authority.

The audit is sparse-checkout safe. Strategy registry/source files are read from the
current Git commit with `git show HEAD:<path>` when they are not materialized locally.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
DEFAULT_REQUIRED_EVIDENCE = ("market_state", "regime_state", "feed_health_truth", "quote_truth")


@dataclass(frozen=True)
class RegistrySpec:
    strategy_id: str
    name: str
    family: str
    module_path: str
    callable_name: str
    required_evidence_keys: tuple[str, ...]


def git_show(root: Path, repo_path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{repo_path}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def read_repo_text(root: Path, repo_path: str) -> str | None:
    local = root / repo_path
    if local.exists():
        return local.read_text(encoding="utf-8")
    return git_show(root, repo_path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dotted_repo_path(dotted: str) -> str:
    return "/".join(dotted.split(".")) + ".py"


def _literal(node: ast.AST, default: Any = None) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return default


def _const_tuple_from_module(tree: ast.Module, name: str) -> tuple[str, ...] | None:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[ast.AST] = []
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
                value = node.value
            else:
                targets = [node.target]
                value = node.value
            if any(isinstance(t, ast.Name) and t.id == name for t in targets) and value is not None:
                raw = _literal(value, None)
                if isinstance(raw, (list, tuple)) and all(isinstance(x, str) for x in raw):
                    return tuple(raw)
    return None


def _resolve_string_tuple(node: ast.AST, tree: ast.Module) -> tuple[str, ...] | None:
    raw = _literal(node, None)
    if isinstance(raw, (list, tuple)) and all(isinstance(x, str) for x in raw):
        return tuple(raw)
    if isinstance(node, ast.Name):
        if node.id == "_DEFAULT_REQUIRED_EVIDENCE_KEYS":
            return _const_tuple_from_module(tree, node.id) or DEFAULT_REQUIRED_EVIDENCE
        return _const_tuple_from_module(tree, node.id)
    return None


def load_registry_specs(root: Path) -> tuple[RegistrySpec, ...]:
    source = read_repo_text(root, "core/strategy_spec.py")
    if source is None:
        raise ValueError("strategy_registry_source_missing:core/strategy_spec.py")
    tree = ast.parse(source)
    build: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_default_strategy_specs":
            build = node
            break
    if build is None:
        raise ValueError("strategy_registry_builder_missing")

    calls: list[ast.Call] = []
    for node in ast.walk(build):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "StrategySpec":
            calls.append(node)

    specs: list[RegistrySpec] = []
    for call in calls:
        if len(call.args) < 5:
            continue
        strategy_id = _literal(call.args[0])
        name = _literal(call.args[1])
        family_node = call.args[2]
        family = family_node.id.removeprefix("FAMILY_") if isinstance(family_node, ast.Name) else str(_literal(family_node, ""))
        module_path = _literal(call.args[3])
        callable_name = _literal(call.args[4])
        required: tuple[str, ...] = _const_tuple_from_module(tree, "_DEFAULT_REQUIRED_EVIDENCE_KEYS") or DEFAULT_REQUIRED_EVIDENCE
        for kw in call.keywords:
            if kw.arg == "required_evidence_keys":
                resolved = _resolve_string_tuple(kw.value, tree)
                if resolved is not None:
                    required = resolved
        if all(isinstance(x, str) and x for x in (strategy_id, name, family, module_path, callable_name)):
            specs.append(RegistrySpec(strategy_id, name, family, module_path, callable_name, required))
    if not specs:
        raise ValueError("strategy_registry_empty_or_unparseable")
    return tuple(specs)


def ast_facts(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    calls: set[str] = set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                parts=[]; cur: Any = fn
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr); cur=cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                calls.add(".".join(reversed(parts)))
        elif isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return {"functions": sorted(funcs), "calls": sorted(calls), "imports": sorted(imports)}


def marker_present(text: str, markers: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(m.lower() in low for m in markers)


def audit_spec(root: Path, spec: RegistrySpec) -> dict[str, Any]:
    repo_path = dotted_repo_path(spec.module_path)
    findings: list[dict[str, str]] = []
    source = read_repo_text(root, repo_path)
    if source is None:
        return {
            "strategy_id": spec.strategy_id, "name": spec.name, "family": spec.family,
            "module_path": spec.module_path, "callable_name": spec.callable_name,
            "source_path": repo_path,
            "verdict": "NOT_IMPLEMENTING_CLAIMED_STRATEGY",
            "findings": [{"severity":"CRITICAL","code":"MODULE_MISSING","detail":repo_path}],
            "runtime_authority":"NONE", "broker_actions_allowed":False,
        }
    facts = ast_facts(source)
    if spec.callable_name not in facts["functions"]:
        findings.append({"severity":"CRITICAL","code":"CALLABLE_MISSING","detail":spec.callable_name})

    bad_calls = sorted(c for c in facts["calls"] if any(tok in c.lower() for tok in FORBIDDEN_CALL_TOKENS))
    if bad_calls:
        findings.append({"severity":"CRITICAL","code":"BROKER_OR_ORDER_CALL_PRESENT","detail":",".join(bad_calls)})

    for key in spec.required_evidence_keys:
        markers = SEMANTIC_MARKERS.get(key)
        if markers and not marker_present(source, markers):
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
        "source_path": repo_path,
        "source_sha256": sha256_text(source),
        "required_evidence_keys": list(spec.required_evidence_keys),
        "verdict": verdict,
        "findings": findings,
        "ast": facts,
        "runtime_authority":"NONE",
        "broker_actions_allowed":False,
    }


def run(repo_root: Path) -> dict[str, Any]:
    specs = load_registry_specs(repo_root)
    rows = [audit_spec(repo_root, s) for s in specs]
    counts: dict[str,int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"],0)+1
    return {
        "schema_version":"tradebot-strategy-structural-audit-v3",
        "status":"STRUCTURAL_AUDIT_COMPLETE_STATIC_PHASE",
        "registry_source":"HEAD:core/strategy_spec.py",
        "sparse_checkout_safe":True,
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
