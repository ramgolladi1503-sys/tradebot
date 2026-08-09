#!/usr/bin/env python3
"""Terminal structural-integrity gate for the registered TradeBot strategy set.

This gate is intentionally independent of profitability. It binds every audit to
one exact Git HEAD, checks registry/source alignment, direct broker side effects,
declared evidence consumption, and a per-strategy structural policy. There are no
UNKNOWN or WITH_LIMITATIONS success states.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FORBIDDEN_CALL_TOKENS = {
    "place_order", "submit_order", "cancel_order", "modify_order", "exit_order",
    "kite.place_order", "upstox.place_order",
}
DEFAULT_REQUIRED_EVIDENCE = ("market_state", "regime_state", "feed_health_truth", "quote_truth")
PASS_VERDICTS = {"STRUCTURALLY_VALID", "SUPPORT_COMPONENT_VALID"}
SUPPORT_COMPONENT_IDS = {"option_pressure_confirmation", "no_trade_chop"}

SEMANTIC_MARKERS: dict[str, tuple[str, ...]] = {
    "vwap_state": ("vwap",),
    "trend_confirmation": ("trend_confirmation", "trend_score", "trend_direction"),
    "session_state": ("session", "opening", "minutes_since_open", "minutes_to_close", "time_of_day"),
    "structure_state": ("structure", "support", "resistance", "orb", "open_price", "completed_bar_history"),
    "anchor_state": ("anchor", "support", "resistance", "vwap"),
    "retracement_state": ("pullback", "retrace", "retracement"),
    "mean_reversion_anchor": ("mean_reversion_anchor", "vwap", "anchor"),
    "oscillator_confirmation": ("oscillator_confirmation", "rsi", "zscore", "z_score", "stoch"),
    "cross_asset_health": ("cross_asset_health", "cross_assets", "confirming_assets"),
    "spread_truth": ("spread_truth", "spread_z", "current_spread"),
    "beta_truth": ("beta_truth", "hedge_ratio", "kalman"),
    "cointegration_truth": ("cointegration_truth", "adfuller", "adf_pvalue"),
    "leg_freshness_a": ("leg_a_age_sec", "leg_freshness_a"),
    "leg_freshness_b": ("leg_b_age_sec", "leg_freshness_b"),
    "compression_state": ("compression", "completed_range_width_pct", "atr_short", "atr_long"),
    "trap_state": ("trap_state", "trap_risk", "break_extreme", "reentry_close"),
    "volatility_state": ("volatility_state", "atr_short", "atr_long", "volatility_expansion"),
    "momentum_state": ("momentum", "directional_score", "trend_up", "trend_down", "volume_z"),
    "reclaim_state": ("reclaim", "hold", "temporal_evidence"),
    "event_state": ("event_state", "event_active"),
    "atr_state": ("atr", "atr_short", "atr_long"),
    "signal_quality": ("signal_quality", "score", "confidence"),
    "candidate_truth": ("candidate_truth", "contract_valid"),
    "family_truth": ("family_truth", "family"),
}

# Every registry entry must have a policy. Each inner tuple is an OR group; all
# groups must be satisfied. Markers are lexical, not raw substrings.
STRATEGY_POLICIES: dict[str, tuple[tuple[str, ...], ...]] = {
    "ensemble": (("child_signals",), ("source_sha256",), ("structural_status",), ("contract_valid",), ("freshness_valid",)),
    "vwap_orb": (("trend_confirmation",), ("cumulative_volume_delta",), ("vpin_toxicity",), ("dealer_gamma_exposure",)),
    "nifty_intraday": (("_allowed_regimes",), ("regime_not_declared_by_strategy_spec",), ("vwap",)),
    "banknifty_intraday": (("_allowed_regimes",), ("regime_not_declared_by_strategy_spec",), ("vwap",)),
    "sensex_intraday": (("_allowed_regimes",), ("regime_not_declared_by_strategy_spec",), ("vwap",)),
    "zero_hero_expiry": (("generate_signal",), ("zero_hero_strategy",), ("next_expiry",)),
    "pairs_arbitrage": (("leg_a_age_sec",), ("leg_b_age_sec",), ("adfuller",), ("cointegration_truth_unavailable",), ("hedge_ratio",), ("spread_truth",)),
    "opening_range_retest": (("completed_bar_history",), ("breakout",), ("retest",), ("continuation",)),
    "trend_pullback": (("completed_bar_history",), ("pullback",), ("trigger", "resumption")),
    "mean_reversion_extension": (("oscillator_confirmation",), ("rsi", "zscore", "z_score"), ("vwap",)),
    "opening_drive": (("minutes_since_open",), ("open_price",), ("vwap",)),
    "compression_breakout": (("completed_bar_history",), ("compression_window", "completed_range_width_pct"), ("breakout",)),
    "failed_breakout_trap": (("completed_bar_history",), ("failed_break_reentry",), ("break_extreme",), ("reentry_close",)),
    "exhaustion_reversal": (("volatility_state",), ("trap_state",), ("ce_premium_change",), ("pe_premium_change",), ("volume_z",)),
    "late_day_momentum": (("minutes_since_open",), ("minutes_to_close",), ("trend_up",), ("trend_down",)),
    "vwap_reclaim_rejection": (("completed_bar_history",), ("establishment",), ("reclaim",), ("hold",)),
    "option_pressure_confirmation": (("does not emit standalone", "downstream_owned", "downstream-owned"), ("return",)),
    "event_volatility_expansion": (("event_state",), ("volatility_state",), ("atr_short",), ("atr_long",), ("volume_z",)),
    "no_trade_chop": (("assess_no_trade",), ("no_trade",), ("direction",)),
    "volatility_trend": (("cross_assets",), ("cross_asset_health",), ("confirming_assets",), ("atr",)),
    "pro_strategy": (("pro_child_signals",), ("source_sha256",), ("structural_status",), ("contract_valid",), ("freshness_valid",), ("family_truth",)),
}

FORBIDDEN_BY_STRATEGY: dict[str, tuple[str, ...]] = {
    "nifty_intraday": ("soft_signal",),
    "banknifty_intraday": ("soft_signal",),
    "sensex_intraday": ("soft_signal",),
    "pairs_arbitrage": ("mock stationary", "adf_pvalue 0.04"),
    "ensemble": ("trend_vwap_signal", "mean_reversion_signal", "orb_breakout_signal", "event_breakout_signal"),
    "pro_strategy": ("VolatilityExpansionStrategy", "LiquidityImbalanceStrategy", "VWAPMeanReversionStrategy", "OptionsFlowStrategy"),
}


@dataclass(frozen=True)
class RegistrySpec:
    strategy_id: str
    name: str
    family: str
    module_path: str
    callable_name: str
    required_evidence_keys: tuple[str, ...]


def git_show(root: Path, repo_path: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{repo_path}"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.stdout if proc.returncode == 0 else None


def read_repo_text(root: Path, repo_path: str) -> str | None:
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
            targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
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
        return _const_tuple_from_module(tree, node.id)
    return None


def load_registry_specs(root: Path) -> tuple[RegistrySpec, ...]:
    source = read_repo_text(root, "core/strategy_spec.py")
    if source is None:
        raise ValueError("strategy_registry_source_missing:core/strategy_spec.py")
    tree = ast.parse(source)
    build = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "build_default_strategy_specs"), None)
    if build is None:
        raise ValueError("strategy_registry_builder_missing")
    specs: list[RegistrySpec] = []
    default_required = _const_tuple_from_module(tree, "_DEFAULT_REQUIRED_EVIDENCE_KEYS") or DEFAULT_REQUIRED_EVIDENCE
    for call in (n for n in ast.walk(build) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "StrategySpec"):
        if len(call.args) < 5:
            continue
        strategy_id = _literal(call.args[0]); name = _literal(call.args[1])
        family_node = call.args[2]
        family = family_node.id.removeprefix("FAMILY_") if isinstance(family_node, ast.Name) else str(_literal(family_node, ""))
        module_path = _literal(call.args[3]); callable_name = _literal(call.args[4])
        required = default_required
        for kw in call.keywords:
            if kw.arg == "required_evidence_keys":
                resolved = _resolve_string_tuple(kw.value, tree)
                if resolved is None:
                    raise ValueError(f"required_evidence_unparseable:{strategy_id}")
                required = resolved
        if all(isinstance(x, str) and x for x in (strategy_id, name, family, module_path, callable_name)):
            specs.append(RegistrySpec(strategy_id, name, family, module_path, callable_name, required))
    if not specs:
        raise ValueError("strategy_registry_empty_or_unparseable")
    return tuple(specs)


def _attribute_path(node: ast.AST) -> str | None:
    parts: list[str] = []; cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr); cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id); return ".".join(reversed(parts))
    return None


def ast_facts(source: str) -> dict[str, Any]:
    tree = ast.parse(source)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    calls: set[str] = set(); imports: set[str] = set(); names: set[str] = set(); attributes: set[str] = set(); strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name): names.add(node.id)
        elif isinstance(node, ast.Attribute):
            path = _attribute_path(node)
            if path: attributes.add(path)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str): strings.add(node.value)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name): calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                path = _attribute_path(node.func)
                if path: calls.add(path)
        elif isinstance(node, ast.Import): imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: imports.add(node.module)
    return {"functions": sorted(funcs), "classes": sorted(classes), "calls": sorted(calls), "imports": sorted(imports), "names": sorted(names), "attributes": sorted(attributes), "string_literals": sorted(strings)}


def _lexical_parts(value: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[^a-z0-9]+", value.lower()) if part)


def _contains_lexical_marker(value: str, marker: str) -> bool:
    vp = _lexical_parts(value); mp = _lexical_parts(marker)
    if not mp or len(mp) > len(vp): return False
    w = len(mp)
    return any(vp[i:i+w] == mp for i in range(len(vp)-w+1))


def _semantic_tokens(facts: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(x) for field in ("names", "attributes", "calls", "string_literals") for x in facts.get(field, ()))


def semantic_evidence_consumed(facts: dict[str, Any], markers: tuple[str, ...]) -> bool:
    return any(_contains_lexical_marker(token, marker) for token in _semantic_tokens(facts) for marker in markers)


def _policy_group_present(facts: dict[str, Any], group: tuple[str, ...]) -> bool:
    return semantic_evidence_consumed(facts, group)


def audit_spec(root: Path, spec: RegistrySpec) -> dict[str, Any]:
    repo_path = dotted_repo_path(spec.module_path)
    source = read_repo_text(root, repo_path)
    findings: list[dict[str, str]] = []
    if source is None:
        return {"strategy_id":spec.strategy_id,"name":spec.name,"family":spec.family,"module_path":spec.module_path,"callable_name":spec.callable_name,"source_path":repo_path,"verdict":"NOT_IMPLEMENTING_CLAIMED_STRATEGY","findings":[{"severity":"CRITICAL","code":"MODULE_MISSING","detail":repo_path}],"runtime_authority":"NONE","broker_actions_allowed":False}
    facts = ast_facts(source)
    if spec.callable_name not in facts["functions"] and spec.callable_name not in facts["classes"]:
        findings.append({"severity":"CRITICAL","code":"CALLABLE_MISSING","detail":spec.callable_name})
    bad_calls = sorted(c for c in facts["calls"] if any(tok in c.lower() for tok in FORBIDDEN_CALL_TOKENS))
    if bad_calls:
        findings.append({"severity":"CRITICAL","code":"BROKER_OR_ORDER_CALL_PRESENT","detail":",".join(bad_calls)})

    # Support components intentionally do not consume alpha evidence themselves.
    if spec.strategy_id not in SUPPORT_COMPONENT_IDS:
        for key in spec.required_evidence_keys:
            markers = SEMANTIC_MARKERS.get(key)
            if markers and not semantic_evidence_consumed(facts, markers):
                findings.append({"severity":"MAJOR","code":"REQUIRED_EVIDENCE_NOT_CONSUMED","detail":key})

    policy = STRATEGY_POLICIES.get(spec.strategy_id)
    if policy is None:
        findings.append({"severity":"CRITICAL","code":"STRUCTURAL_POLICY_MISSING","detail":spec.strategy_id})
    else:
        for group in policy:
            if not _policy_group_present(facts, group):
                findings.append({"severity":"MAJOR","code":"STRUCTURAL_POLICY_MARKER_MISSING","detail":"|".join(group)})

    low_source = source.lower()
    for forbidden in FORBIDDEN_BY_STRATEGY.get(spec.strategy_id, ()):
        if forbidden.lower() in low_source:
            findings.append({"severity":"MAJOR","code":"FORBIDDEN_LEGACY_PATTERN_PRESENT","detail":forbidden})

    if any(f["severity"] == "CRITICAL" for f in findings):
        verdict = "NOT_IMPLEMENTING_CLAIMED_STRATEGY"
    elif any(f["severity"] == "MAJOR" for f in findings):
        verdict = "STRUCTURAL_REPAIR_REQUIRED"
    elif spec.strategy_id in SUPPORT_COMPONENT_IDS:
        verdict = "SUPPORT_COMPONENT_VALID"
    else:
        verdict = "STRUCTURALLY_VALID"
        findings.append({"severity":"INFO","code":"STRUCTURAL_POLICY_PASS","detail":"contract/source policy satisfied at exact HEAD"})

    return {"strategy_id":spec.strategy_id,"name":spec.name,"family":spec.family,"module_path":spec.module_path,"callable_name":spec.callable_name,"source_path":repo_path,"source_sha256":sha256_text(source),"required_evidence_keys":list(spec.required_evidence_keys),"verdict":verdict,"findings":findings,"ast":facts,"runtime_authority":"NONE","broker_actions_allowed":False}


def run(repo_root: Path) -> dict[str, Any]:
    specs = load_registry_specs(repo_root)
    rows = [audit_spec(repo_root, s) for s in specs]
    counts: dict[str,int] = {}
    for row in rows: counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    head = subprocess.run(["git","-C",str(repo_root),"rev-parse","HEAD"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout.strip()
    all_closed = all(row["verdict"] in PASS_VERDICTS for row in rows)
    return {
        "schema_version":"tradebot-strategy-structural-gate-v1",
        "status":"STRUCTURAL_GATE_PASS" if all_closed else "STRUCTURAL_GATE_FAIL",
        "source_commit":head,
        "registry_source":"HEAD:core/strategy_spec.py",
        "registered_strategy_count":len(specs),
        "policy_count":len(STRATEGY_POLICIES),
        "all_structurally_closed":all_closed,
        "verdict_counts":counts,
        "strategies":rows,
        "profitability_evaluated":False,
        "certification":"NOT_CERTIFIED",
        "runtime_authority":"NONE",
        "broker_actions_allowed":False,
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--repo-root",default="."); p.add_argument("--output",default="research/hypotheses/strategy_structural_audit/registered_strategy_structural_audit.json")
    a=p.parse_args(argv); root=Path(a.repo_root).resolve(); result=run(root); out=root/a.output; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"source_commit":result["source_commit"],"registered_strategy_count":result["registered_strategy_count"],"policy_count":result["policy_count"],"all_structurally_closed":result["all_structurally_closed"],"verdict_counts":result["verdict_counts"],"output":str(out),"runtime_authority":"NONE"},indent=2,sort_keys=True))
    return 0 if result["all_structurally_closed"] else 2

if __name__ == "__main__": raise SystemExit(main())
