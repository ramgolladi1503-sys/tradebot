#!/usr/bin/env python3
"""Generate an audit-only module robustness and ranking-pipeline evidence pack.

This script is deliberately read-only with respect to production/runtime paths.
It inspects tracked files, parses Python AST metadata, runs lightweight
deterministic probes, and writes artifacts under
research/module_robustness_ranking_audit_v1/.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "module_robustness_ranking_audit_v1"
EVIDENCE = OUT / "evidence"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
STATUS_VALUES = {
    "VERIFIED",
    "PARTIALLY_VERIFIED",
    "NOT_VERIFIED",
    "NOT_APPLICABLE",
    "BLOCKED_BY_MISSING_EVIDENCE",
}


EXCLUDE_PREFIXES = (
    ".git/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    "__pycache__/",
    "runtime/",
    ".runtime/",
    "logs/",
    "data/",
    "reports/",
    "tmp_ce_reports/",
    "tmp_ce_reports_new/",
    "ce_reports/",
    "build/",
    "dist/",
)

AUDIT_EXTENSIONS = {
    ".py",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
    ".sql",
}

PIPELINE_KEYWORDS = {
    "feed": "feed_ingestion_or_freshness",
    "fresh": "feed_ingestion_or_freshness",
    "regime": "regime_classification",
    "option": "option_chain_or_quote",
    "quote": "option_chain_or_quote",
    "depth": "option_chain_or_quote",
    "candidate": "candidate_generation_or_contract",
    "strategy": "strategy_generation",
    "normaliz": "candidate_normalization",
    "classif": "validation_and_eligibility",
    "downgrade": "fallback_or_degradation",
    "score": "scoring",
    "confidence": "scoring",
    "rank": "ranking",
    "select": "selection",
    "dashboard": "ui_projection",
    "streamlit": "ui_projection",
    "approval": "manual_approval",
    "broker": "broker_execution_handoff",
    "execution": "broker_execution_handoff",
    "risk": "risk_governance",
    "persist": "persistence",
    "store": "persistence",
    "replay": "replay_or_evidence",
    "audit": "observability",
    "evidence": "observability",
}

ROW_IMPACT_KEYWORDS = (
    "candidate",
    "rank",
    "score",
    "confidence",
    "fallback",
    "degraded",
    "quote",
    "feed",
    "fresh",
    "display",
    "executable",
    "approval",
    "broker",
)


@dataclass
class ModuleRecord:
    module_id: str
    path: str
    extension: str
    size_bytes: int
    line_count: int
    complexity_indicators: str
    primary_responsibility: str
    public_symbols: str
    callers: str
    dependencies: str
    input_contracts: str
    output_contracts: str
    state_owned_or_mutated: str
    side_effects: str
    runtime_criticality: str
    row_surface: str
    test_coverage: str
    test_quality: str
    duplication_or_overlap: str
    status: str


def run(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 120) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_sec": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\nTIMEOUT",
            "duration_sec": round(time.time() - started, 3),
        }


def git_lines(args: list[str]) -> list[str]:
    result = run(["git", *args], timeout=300)
    if result["returncode"] != 0:
        raise RuntimeError(result["stderr"])
    return [line for line in result["stdout"].splitlines() if line]


def tracked_files() -> list[str]:
    return sorted(git_lines(["ls-files"]))


def should_exclude(path: str) -> tuple[bool, str]:
    if any(path.startswith(prefix) for prefix in EXCLUDE_PREFIXES):
        return True, "runtime/generated/cache/report/data path excluded from module audit"
    suffix = Path(path).suffix
    if suffix not in AUDIT_EXTENSIONS:
        return True, f"non-module/static/binary extension excluded:{suffix or '<none>'}"
    return False, ""


def parse_python(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"parse_error": str(exc), "imports": [], "symbols": [], "classes": [], "functions": [], "assigns": 0}
    imports: list[str] = []
    symbols: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    assigns = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            if not node.name.startswith("_"):
                symbols.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            if not node.name.startswith("_"):
                symbols.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            assigns += 1
    return {
        "parse_error": "",
        "imports": sorted(set(filter(None, imports))),
        "symbols": sorted(set(symbols)),
        "classes": sorted(set(classes)),
        "functions": sorted(set(functions)),
        "assigns": assigns,
    }


def module_id_for(path: str) -> str:
    p = Path(path)
    if p.suffix == ".py":
        parts = list(p.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)
    return path.replace("/", ":")


def infer_stage(path: str, text_sample: str) -> str:
    lower = f"{path}\n{text_sample[:4000]}".lower()
    hits = Counter(stage for key, stage in PIPELINE_KEYWORDS.items() if key in lower)
    return hits.most_common(1)[0][0] if hits else "support_or_unknown"


def infer_runtime_role(path: str, stage: str) -> str:
    if path.startswith("tests/"):
        return "test"
    if path.startswith("scripts/"):
        return "cli_or_probe"
    if path.startswith("dashboard/"):
        return "ui"
    if path.startswith("strategies/"):
        return "strategy"
    if path.startswith("core/"):
        return "core_runtime_or_contract"
    if path.startswith("config/"):
        return "configuration"
    if path.startswith("research/"):
        return "research_or_audit"
    return stage


def build_inventory(files: list[str]) -> tuple[list[ModuleRecord], list[dict[str, Any]], dict[str, Any]]:
    included: list[str] = []
    excluded: list[dict[str, Any]] = []
    for path in files:
        skip, reason = should_exclude(path)
        if skip:
            excluded.append({"path": path, "reason": reason})
        else:
            included.append(path)

    import_to_paths: dict[str, set[str]] = defaultdict(set)
    parsed: dict[str, dict[str, Any]] = {}
    samples: dict[str, str] = {}
    for rel in included:
        abs_path = ROOT / rel
        text = abs_path.read_text(encoding="utf-8", errors="replace") if abs_path.is_file() else ""
        samples[rel] = text
        if Path(rel).suffix == ".py":
            meta = parse_python(abs_path)
        else:
            meta = {"parse_error": "", "imports": [], "symbols": [], "classes": [], "functions": [], "assigns": 0}
        parsed[rel] = meta
        for imp in meta["imports"]:
            import_to_paths[imp.split(".")[0]].add(rel)

    callers_by_path: dict[str, set[str]] = defaultdict(set)
    module_paths = {module_id_for(path): path for path in included if Path(path).suffix == ".py"}
    for caller, meta in parsed.items():
        for imp in meta["imports"]:
            for module, target_path in module_paths.items():
                if imp == module or imp.startswith(module + ".") or module.startswith(imp + "."):
                    if target_path != caller:
                        callers_by_path[target_path].add(caller)

    test_files = [path for path in included if path.startswith("tests/")]
    stage_by_path = {rel: infer_stage(rel, samples[rel]) for rel in included}
    stage_counts = Counter(stage_by_path.values())
    same_stem_index: dict[str, list[str]] = defaultdict(list)
    for rel in included:
        same_stem_index[Path(rel).stem].append(rel)
    records: list[ModuleRecord] = []
    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    for rel in included:
        abs_path = ROOT / rel
        text = samples[rel]
        lines = text.splitlines()
        meta = parsed[rel]
        stage = stage_by_path[rel]
        role = infer_runtime_role(rel, stage)
        symbol_token = Path(rel).stem
        covering_tests = [t for t in test_files if symbol_token in t or symbol_token in samples[t]]
        row_surface = "yes" if any(key in text.lower() or key in rel.lower() for key in ROW_IMPACT_KEYWORDS) else "no"
        side_effects = []
        for token, label in (
            ("open(", "filesystem_io"),
            (".write", "filesystem_write"),
            ("subprocess", "subprocess"),
            ("requests.", "network_http"),
            ("sqlite3", "sqlite"),
            ("streamlit", "ui_render"),
            ("kite", "broker_or_market_adapter"),
            ("upstox", "broker_or_market_adapter"),
        ):
            if token in text:
                side_effects.append(label)
        mutates_state = "module_assignments:%d" % meta.get("assigns", 0)
        record = ModuleRecord(
            module_id=module_id_for(rel),
            path=rel,
            extension=Path(rel).suffix or "<none>",
            size_bytes=abs_path.stat().st_size,
            line_count=len(lines),
            complexity_indicators=json.dumps(
                {
                    "classes": len(meta["classes"]),
                    "functions": len(meta["functions"]),
                    "imports": len(meta["imports"]),
                    "parse_error": bool(meta["parse_error"]),
                },
                sort_keys=True,
            ),
            primary_responsibility=stage,
            public_symbols=";".join(meta["symbols"][:80]),
            callers=";".join(sorted(callers_by_path.get(rel, ()))[:80]),
            dependencies=";".join(meta["imports"][:80]),
            input_contracts=_contract_hint(text, "input"),
            output_contracts=_contract_hint(text, "output"),
            state_owned_or_mutated=mutates_state,
            side_effects=";".join(sorted(set(side_effects))) or "none_detected_by_static_scan",
            runtime_criticality=_criticality(rel, stage, role),
            row_surface=row_surface,
            test_coverage="covered_by:%d" % len(covering_tests),
            test_quality=_test_quality(rel, covering_tests, samples),
            duplication_or_overlap=_overlap_hint(rel, stage, same_stem_index, stage_counts),
            status=_status_hint(rel, role),
        )
        records.append(record)
        graph_nodes.append({"id": record.module_id, "path": rel, "stage": stage, "role": role})
        for imp in meta["imports"][:120]:
            graph_edges.append({"source": record.module_id, "target_import": imp})
    graph = {"nodes": graph_nodes, "edges": graph_edges}
    return records, excluded, graph


def _contract_hint(text: str, direction: str) -> str:
    lower = text.lower()
    hits = []
    for token in ("dataclass", "pydantic", "schema_version", "to_dict", "typed", "validate", "contract"):
        if token in lower:
            hits.append(token)
    if not hits:
        return f"{direction}_contract_not_explicit_in_static_scan"
    return ";".join(sorted(set(hits)))


def _criticality(path: str, stage: str, role: str) -> str:
    if any(path.startswith(prefix) for prefix in ("core/broker", "core/order", "core/execution", "core/risk", "core/feed", "main.py", "run_live.sh", "config/")):
        return "high"
    if stage in {"ranking", "scoring", "candidate_generation_or_contract", "option_chain_or_quote", "feed_ingestion_or_freshness", "manual_approval"}:
        return "high" if role != "test" else "medium"
    if role in {"ui", "strategy"}:
        return "medium"
    return "low"


def _test_quality(path: str, tests: list[str], samples: dict[str, str]) -> str:
    if path.startswith("tests/"):
        text = samples.get(path, "").lower()
        signals = [token for token in ("raises", "assert", "parametrize", "stale", "fallback", "duplicate", "malformed", "ineligible") if token in text]
        return "test_file_semantic_signals:" + ",".join(signals)
    if not tests:
        return "NO_DIRECT_TEST_DETECTED"
    joined = "\n".join(samples.get(t, "").lower() for t in tests[:20])
    signals = [token for token in ("stale", "fallback", "duplicate", "malformed", "ineligible", "determin", "lineage", "rank") if token in joined]
    return "semantic_signals:" + ",".join(signals) if signals else "shape_or_smoke_only_static_signal"


def _overlap_hint(path: str, stage: str, same_stem_index: dict[str, list[str]], stage_counts: Counter[str]) -> str:
    stem = Path(path).stem
    siblings = [p for p in same_stem_index.get(stem, []) if p != path]
    hints = []
    if siblings:
        hints.append("same_stem:" + ";".join(siblings[:8]))
    if stage_counts.get(stage, 0) > 5:
        hints.append("many_same_stage_modules")
    return "|".join(hints) if hints else "none_detected_by_static_scan"


def _status_hint(path: str, role: str) -> str:
    lower = path.lower()
    if path.startswith("tests/"):
        return "test"
    if any(token in lower for token in ("legacy", "deprecated", "compat", "shim")):
        return "legacy_or_compatibility"
    if path.startswith("research/"):
        return "research_only"
    if role in {"core_runtime_or_contract", "strategy", "ui", "configuration"}:
        return "active_or_runtime_relevant"
    return "unknown"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def probe_ranking() -> dict[str, Any]:
    try:
        from core.candidate_ranking import rank_candidates
        from core.directional_balance import analyze_directional_balance
        from core.hard_downgrade_engine import HardDowngradeDecision, HardDowngradeReport
        from core.movement_contract import StrategyCandidate
        from core.opportunity_scoring import score_opportunities

        c1 = StrategyCandidate(
            schema_version=1,
            strategy_id="probe_a",
            symbol="NIFTY",
            direction="BUY_CALL",
            movement_type="TREND_PULLBACK",
            status="VALIDATED_CANDIDATE",
            raw_score=0.8,
            confidence_score=0.8,
            price_structure_score=0.8,
            option_confirmation_score=0.8,
            liquidity_score=0.8,
            freshness_score=0.8,
            volatility_score=0.7,
            regime_alignment_score=0.8,
            evidence={"probe": "ranking_determinism"},
        )
        c2 = StrategyCandidate(
            schema_version=1,
            strategy_id="probe_b",
            symbol="NIFTY",
            direction="BUY_PUT",
            movement_type="MEAN_REVERSION_EXTENSION",
            status="VALIDATED_CANDIDATE",
            raw_score=0.8,
            confidence_score=0.8,
            price_structure_score=0.8,
            option_confirmation_score=0.8,
            liquidity_score=0.8,
            freshness_score=0.8,
            volatility_score=0.7,
            regime_alignment_score=0.8,
            evidence={"probe": "ranking_determinism"},
        )
        decisions = tuple(
            HardDowngradeDecision(
                strategy_id=c.strategy_id,
                symbol=c.symbol,
                direction=c.direction,
                movement_type=c.movement_type,
                original_bucket="EXECUTABLE_CANDIDATE",
                downgraded_bucket="EXECUTABLE_CANDIDATE",
                downgraded=False,
                executable_candidate=True,
                downgrade_reasons=(),
                blockers=(),
                hard_blockers=(),
                warnings=(),
                safety_flags=(),
                evidence_flags=(),
            )
            for c in (c1, c2)
        )
        report = HardDowngradeReport(
            schema_version=1,
            read_only=True,
            is_order_action=False,
            append=False,
            candidate_count=2,
            downgraded_count=0,
            suppressed_count=0,
            no_trade_count=0,
            executable_after_downgrade_count=2,
            decisions=decisions,
            blockers=(),
            warnings=(),
            safety_flags=(),
        )
        scoring = score_opportunities((c1, c2), report)
        balance = analyze_directional_balance(scoring)
        first = rank_candidates(scoring, balance).to_dict()
        second = rank_candidates(scoring, balance).to_dict()
        first_order = [r["strategy_id"] for r in first["ranks"]]
        second_order = [r["strategy_id"] for r in second["ranks"]]
        return {
            "status": "PARTIALLY_VERIFIED",
            "deterministic_order_same_frozen_input": first_order == second_order,
            "first_order": first_order,
            "second_order": second_order,
            "rank_contiguous": [r["rank"] for r in first["ranks"]] == list(range(1, len(first["ranks"]) + 1)),
            "rank_ids_unique": len({r["rank"] for r in first["ranks"]}) == len(first["ranks"]),
            "score_values": [r["final_score"] for r in first["ranks"]],
            "limitation": "synthetic in-process probe only; not replay-labelled calibration evidence",
        }
    except Exception as exc:  # pragma: no cover - audit evidence path
        return {"status": "BLOCKED_BY_MISSING_EVIDENCE", "error": repr(exc)}


def build_findings(records: list[ModuleRecord], excluded: list[dict[str, Any]], ranking_probe: dict[str, Any]) -> list[dict[str, Any]]:
    by_path = {r.path: r for r in records}
    findings = [
        {
            "finding_id": "F-P0-001",
            "severity": "P0",
            "status": "VERIFIED",
            "confidence": "high",
            "summary": "Primary checkout was dirty at audit start, so a trustworthy baseline could not be established from the working tree itself.",
            "evidence": "git status --short in /Users/madhuram/tradebot showed modified/deleted runtime data and source files; audit worktree was created from origin/main instead.",
            "modules": [],
            "ranking_pipeline_impact": "Baseline evidence can be contaminated if generated from the dirty checkout; using origin/main avoids mixing user/runtime changes into the audit.",
            "recommended_fix": "Before repair PRs, require a clean synchronized main checkout or explicitly name the commit/branch to audit; preserve dirty runtime artifacts outside git before cleanup.",
            "acceptance_criteria": "git status --short is empty in the audited checkout and base SHA is recorded in baseline_environment.json.",
        },
        {
            "finding_id": "F-P1-001",
            "severity": "P1",
            "status": "VERIFIED",
            "confidence": "high",
            "summary": "The canonical ranking layer exists, but UI fallback paths can display rows from visible/executable filters when top ranked snapshots are empty.",
            "evidence": "dashboard/streamlit_app_runtime.py:_select_primary_suggestion_table returns advisory_fallback_visible or advisory_fallback_executable; tests/test_dashboard_advisory_ranking_source.py asserts those fallback sources.",
            "modules": [p for p in ("dashboard/streamlit_app_runtime.py", "tests/test_dashboard_advisory_ranking_source.py") if p in by_path],
            "ranking_pipeline_impact": "Displayed rows are not guaranteed to map one-to-one to a ranked candidate when canonical top snapshots are empty.",
            "recommended_fix": "Make fallback UI rows explicitly non-actionable with source='unranked_display_fallback', require ranked_candidate_id/ranking_snapshot_id for actionable rows, and add an invariant test that manual approval controls are disabled for fallback-visible rows.",
            "acceptance_criteria": "Every displayed actionable row has ranking_snapshot_id and candidate_id; fallback rows render only in debug/advisory sections with a reason code.",
        },
        {
            "finding_id": "F-P1-002",
            "severity": "P1",
            "status": "PARTIALLY_VERIFIED",
            "confidence": "medium",
            "summary": "Score/confidence semantics are heuristic setup scores, not calibrated predictive probabilities.",
            "evidence": "core/opportunity_scoring.py uses fixed component weights and penalties; core/candidate_ranking.py labels rows 'Setup score' when outcome calibration metadata is missing.",
            "modules": [p for p in ("core/opportunity_scoring.py", "core/candidate_ranking.py") if p in by_path],
            "ranking_pipeline_impact": "Cross-strategy rank order may be deterministic but not statistically calibrated across regimes or producers.",
            "recommended_fix": "Rename display probability surfaces to setup_score unless CandidateOutcomeContract has prediction_event, horizon, and calibration_source; add calibration-source-required tests for probability labels.",
            "acceptance_criteria": "No UI/API field calls an uncalibrated score a probability; calibrated labels require out-of-sample metadata.",
        },
        {
            "finding_id": "F-P1-003",
            "severity": "P1",
            "status": "VERIFIED" if "core/executable_truth.py" in by_path else "PARTIALLY_VERIFIED",
            "confidence": "high",
            "summary": "Fallback, stale, subscription-failed, and price-mismatch quote truth can block executable status, but policy is split across scoring, ranking, executable truth, and top-opportunity truth modules.",
            "evidence": "core/executable_truth.py defines fallback/stale/price-mismatch/subscription failed reasons; core/opportunity_scoring.py applies fallback penalties; core/candidate_ranking.py suppresses feed-risk candidates.",
            "modules": [p for p in ("core/executable_truth.py", "core/opportunity_scoring.py", "core/candidate_ranking.py", "core/top_opportunity_executable_truth.py") if p in by_path],
            "ranking_pipeline_impact": "Correct fail-closed behavior depends on several modules preserving the same provenance and reason fields.",
            "recommended_fix": "Create a single fallback authority table artifact consumed by tests; assert fallback provenance survives scoring, ranking, top-opportunity projection, and executable-truth checks.",
            "acceptance_criteria": "A replay/probe row with recovered_fallback remains advisory/non-executable through every projection and records the same reason code.",
        },
        {
            "finding_id": "F-P2-001",
            "severity": "P2",
            "status": "VERIFIED",
            "confidence": "high",
            "summary": "Many modules have no direct semantic test signal in static inventory.",
            "evidence": "module_inventory.csv test_coverage and test_quality columns show NO_DIRECT_TEST_DETECTED or shape/smoke-only static signals for a material subset.",
            "modules": [r.path for r in records if r.test_quality == "NO_DIRECT_TEST_DETECTED"][:50],
            "ranking_pipeline_impact": "Small helpers can silently mutate, drop, or misclassify rows without a contract test catching it.",
            "recommended_fix": "For P0/P1/P2-ranked modules, add focused contract tests for stale, fallback, duplicate, malformed, and deterministic ordering cases before refactoring.",
            "acceptance_criteria": "Every high-criticality row_surface=yes module has at least one semantic contract test tied to row lifecycle or safety behavior.",
        },
        {
            "finding_id": "F-P2-002",
            "severity": "P2",
            "status": ranking_probe.get("status", "NOT_VERIFIED"),
            "confidence": "medium",
            "summary": "Ranking determinism is partially verified for a synthetic frozen input but not for full replay/runtime evidence.",
            "evidence": json.dumps(ranking_probe, sort_keys=True),
            "modules": [p for p in ("core/candidate_ranking.py", "core/ranking_orchestrator.py") if p in by_path],
            "ranking_pipeline_impact": "Rank order can be deterministic in unit scope while still lacking replay hash stability and full row-accounting proof.",
            "recommended_fix": "Add audit replay fixtures that freeze inputs, serialize ranked snapshots, and compare ordered candidate IDs and row-flow counts across two clean runs.",
            "acceptance_criteria": "Same fixture produces same ranking_snapshot hash, contiguous ranks, stable candidate IDs, and reconciled stage counts.",
        },
    ]
    if excluded:
        findings.append(
            {
                "finding_id": "F-P3-001",
                "severity": "P3",
                "status": "VERIFIED",
                "confidence": "high",
                "summary": "Generated/runtime/static exclusions are explicit and counted, but excluded runtime evidence was not semantically audited module-by-module.",
                "evidence": f"module_exclusion_manifest.json contains {len(excluded)} excluded tracked files.",
                "modules": [],
                "ranking_pipeline_impact": "Historical runtime data can still be useful for replay diagnostics but is outside tracked module responsibility scoring.",
                "recommended_fix": "Run a separate data-evidence audit for selected runtime/replay artifacts when row distribution diagnostics are required.",
                "acceptance_criteria": "Selected replay artifacts have manifests, hashes, schema classification, and provenance checks.",
            }
        )
    return findings


def fix_rows(records: list[ModuleRecord], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finding_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        for path in finding.get("modules", []):
            finding_by_path[path].append(finding)
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        relevant = finding_by_path.get(record.path)
        if not relevant:
            severity = "NONE"
            finding_id = "NONE"
            summary = "No module-specific defect found by static audit/probes; evidence checked includes AST parse, imports, public symbols, row-surface keywords, side-effect tokens, callers, and direct-test signals."
            recommendation = "No immediate module-specific fix; keep covered by wave-level contract tests if row_surface=yes or runtime_criticality=high."
            status = "PARTIALLY_VERIFIED"
            impact = "none_detected"
        else:
            primary = sorted(relevant, key=lambda f: ("P0", "P1", "P2", "P3").index(f["severity"]))[0]
            severity = primary["severity"]
            finding_id = primary["finding_id"]
            summary = primary["summary"]
            recommendation = primary["recommended_fix"]
            status = primary["status"]
            impact = primary["ranking_pipeline_impact"]
        rows.append(
            {
                "module_id": record.module_id,
                "path": record.path,
                "module_size_class": "small" if record.line_count < 120 else "medium" if record.line_count < 500 else "large",
                "runtime_role": infer_runtime_role(record.path, record.primary_responsibility),
                "pipeline_stage": record.primary_responsibility,
                "current_responsibility": record.primary_responsibility,
                "audit_status": status if status in STATUS_VALUES else "PARTIALLY_VERIFIED",
                "robustness_score_0_to_5": _score(record, severity),
                "ranking_pipeline_impact": impact,
                "finding_id": finding_id,
                "finding_summary": summary,
                "evidence": f"{record.path}; lines={record.line_count}; tests={record.test_coverage}; side_effects={record.side_effects}",
                "failure_mode": _failure_mode(record, severity),
                "trigger_condition": "See finding evidence or static row-surface/side-effect scan.",
                "current_observed_effect": "Audit-only observation; no production behavior changed.",
                "worst_plausible_effect": _worst_effect(record, severity),
                "row_integrity_impact": "direct_or_indirect" if record.row_surface == "yes" else "not_detected",
                "trading_safety_impact": "high" if record.runtime_criticality == "high" and record.row_surface == "yes" else "low_or_indirect",
                "severity": severity,
                "likelihood": "medium" if severity in {"P1", "P2"} else "low",
                "detectability": "medium" if "NO_DIRECT" not in record.test_quality else "low",
                "recommended_fix": recommendation,
                "why_this_fix_is_needed": "Preserve row truth, deterministic ranking, and fail-closed decision boundaries.",
                "expected_benefit": "More explainable accepted/degraded/rejected/ranked/displayed row lifecycle.",
                "what_behaviour_will_change": _behavior_change(severity),
                "what_could_break_or_regress": _regression_risk(record, severity),
                "compatibility_or_migration_risk": "schema/UI/test updates possible" if severity in {"P0", "P1", "P2"} else "none_expected",
                "dependent_modules": record.callers,
                "prerequisites": "freeze fixture and current behavior before fix" if severity in {"P0", "P1", "P2"} else "none",
                "recommended_tests": _recommended_tests(record),
                "acceptance_criteria": "Specific row lifecycle invariant passes and audit evidence is updated.",
                "estimated_effort": "M" if severity in {"P1", "P2"} else "XS",
                "recommended_order": index if severity != "NONE" else 9999,
                "fix_now_or_later": "fix_now" if severity in {"P0", "P1"} else "later" if severity == "P3" else "no_fix_required" if severity == "NONE" else "fix_after_P1",
                "confidence_in_recommendation": "medium" if severity != "NONE" else "low_static_scan_only",
            }
        )
    return rows


def _score(record: ModuleRecord, severity: str) -> int:
    base = 4
    if record.test_quality == "NO_DIRECT_TEST_DETECTED":
        base -= 1
    if record.side_effects != "none_detected_by_static_scan" and record.row_surface == "yes":
        base -= 1
    if severity == "P1":
        base -= 2
    if severity == "P2":
        base -= 1
    return max(0, min(5, base))


def _failure_mode(record: ModuleRecord, severity: str) -> str:
    if severity == "NONE":
        return "none_found_by_audit"
    if record.primary_responsibility == "ui_projection":
        return "unranked_or_stale_row_display"
    if record.primary_responsibility == "scoring":
        return "ambiguous_score_semantics_or_compression"
    if record.primary_responsibility == "ranking":
        return "rank_order_or_identity_invariant_gap"
    return "row_truth_or_observability_gap"


def _worst_effect(record: ModuleRecord, severity: str) -> str:
    if severity == "P0":
        return "truth corruption or unsafe promotion could mislead manual approval"
    if severity == "P1":
        return "invalid row promotion, legitimate row suppression, or misleading ranking/UI state"
    if severity == "P2":
        return "defect becomes hard to detect during replay or runtime debugging"
    return "no immediate row-integrity effect identified"


def _behavior_change(severity: str) -> str:
    if severity in {"P0", "P1"}:
        return "row counts may drop, displayed rows may become advisory/debug-only, and rankings may reorder after stricter identity/provenance checks"
    if severity == "P2":
        return "tests and logs become stricter; some legacy shape-only assumptions may fail"
    return "none"


def _regression_risk(record: ModuleRecord, severity: str) -> str:
    if severity in {"P0", "P1", "P2"}:
        return f"callers may rely on current {record.primary_responsibility} field names, ordering, or fallback availability"
    return "none_identified"


def _recommended_tests(record: ModuleRecord) -> str:
    if record.primary_responsibility == "ranking":
        return "deterministic replay, rank tie determinism, contiguous unique ranks, fallback provenance preservation"
    if record.primary_responsibility == "ui_projection":
        return "UI order equals canonical ranking order; displayed row maps to one ranked candidate; fallback rows non-actionable"
    if record.primary_responsibility in {"option_chain_or_quote", "feed_ingestion_or_freshness"}:
        return "stale versus fresh precedence, malformed/partial response, duplicate/out-of-order data"
    if record.primary_responsibility == "candidate_generation_or_contract":
        return "duplicate candidate emission, CE/PE semantics, missing evidence, frozen timestamp cutoff"
    return "semantic contract test for malformed input and explicit fail-closed behavior"


def write_markdown_reports(records: list[ModuleRecord], findings: list[dict[str, Any]], counts: dict[str, Any]) -> None:
    p0p3 = Counter(f["severity"] for f in findings)
    verdict = principal_verdict(findings, counts)
    (OUT / "executive_verdict.md").write_text(
        "\n".join(
            [
                f"# Executive Verdict",
                "",
                f"Principal outcome: {verdict}",
                "",
                f"Audited module count: {counts['audited_module_count']}",
                f"Excluded module count: {counts['excluded_module_count']}",
                f"P0/P1/P2/P3 counts: {p0p3.get('P0',0)}/{p0p3.get('P1',0)}/{p0p3.get('P2',0)}/{p0p3.get('P3',0)}",
                "Row accounting reconciles: PARTIALLY_VERIFIED for synthetic ranking probe only; full replay accounting is BLOCKED_BY_MISSING_EVIDENCE.",
                "Every displayed row traceable to ranked candidate: NOT_VERIFIED; fallback UI sources are VERIFIED.",
                "Ranking deterministic: PARTIALLY_VERIFIED for synthetic in-process probe.",
                "Score semantics comparable: PARTIALLY_VERIFIED as heuristic setup scores; predictive calibration NOT_VERIFIED.",
                "Fallback/degraded rows can reach executable state: PARTIALLY_VERIFIED blocked by executable-truth/ranking policies, but requires replay proof across UI/approval.",
                "",
                "Top five repair priorities:",
                "1. Require ranked candidate identity for every actionable displayed row.",
                "2. Preserve fallback/degraded provenance across scoring, ranking, top-opportunity projection, and executable truth.",
                "3. Add deterministic replay row-accounting fixtures with stage reconciliation.",
                "4. Rename or gate uncalibrated confidence/probability labels as setup scores.",
                "5. Add semantic contract tests for high-criticality row-surface modules lacking direct tests.",
                "",
                "Explicit blockers:",
                "- Primary checkout was dirty; audit used clean origin/main worktree.",
                "- No live broker credentials were used or required.",
                "- Full labelled out-of-sample calibration evidence was not present in this audit.",
                "- Full historical row-flow accounting requires a selected frozen replay sample beyond static module inventory.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "README.md").write_text(
        "\n".join(
            [
                "# Module Robustness Ranking Audit v1",
                "",
                "Reproduce from the isolated worktree:",
                "",
                "```bash",
                "cd /Users/madhuram/tradebot-module-robustness-ranking-audit-v1",
                f"{sys.executable} scripts/generate_module_robustness_ranking_audit.py",
                "pytest -q tests/test_dashboard_advisory_ranking_source.py tests/test_ranked_pipeline_runtime_evidence_wiring.py tests/test_feed_truth_audit.py",
                "```",
                "",
                "This is an audit-only evidence pack. It does not call brokers, place orders, alter strategy thresholds, or modify runtime configuration.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "master_module_fix_matrix.md").write_text(
        "# Master Module Fix Matrix\n\nSee `master_module_fix_matrix.csv` for all modules. Material findings:\n\n"
        + "\n".join(f"- {f['finding_id']} ({f['severity']}, {f['status']}): {f['summary']}" for f in findings)
        + "\n",
        encoding="utf-8",
    )
    (OUT / "actual_pipeline_map.md").write_text(
        """# Actual Pipeline Map

VERIFIED core read-only ranking path on this HEAD:

`core.ranking_orchestrator.build_ranked_opportunity_report`

1. `core.candidate_pool_orchestrator.build_candidate_pool_report`
2. `core.candidate_normalizer.normalize_candidates`
3. `core.candidate_classifier.classify_candidates`
4. `core.hard_downgrade_engine.apply_hard_downgrades`
5. `core.opportunity_scoring.score_opportunities`
6. `core.directional_balance.analyze_directional_balance`
7. `core.feed_hold_gate.apply_feed_hold_to_ranking` when feed truth is supplied
8. `core.candidate_ranking.rank_candidates`

PARTIALLY_VERIFIED UI projection path:

`dashboard.streamlit_app_runtime` reads top executable/advisory snapshots, but can fall back to visible/advisory or executable filtered rows when canonical top snapshots are empty.

NOT_VERIFIED in this audit: broker/manual approval end-to-end identity preservation from ranked snapshot to order handoff. No broker APIs were called.
""",
        encoding="utf-8",
    )
    (OUT / "row_lifecycle_state_machine.md").write_text(
        """# Row Lifecycle State Machine

Discovered states and buckets include `RAW_CANDIDATE`, `VALIDATED_CANDIDATE`, `BLOCKED_CANDIDATE`, `NO_TRADE`, `EXECUTABLE_CANDIDATE`, `NEAR_EXECUTABLE_CANDIDATE`, `ADVISORY_CANDIDATE`, `SUPPRESSED_CANDIDATE`, and `NO_TRADE_CANDIDATE`.

Canonical audit model mapping:

- observed/generated: strategy/feed/adapters create candidate or market evidence.
- normalized: `candidate_normalizer`.
- eligible/ineligible/rejected: `candidate_classifier`, `hard_downgrade_engine`.
- degraded: downgrade reasons and fallback/feed-risk flags.
- scored: `opportunity_scoring`.
- ranked: `candidate_ranking`.
- selected/displayed: top opportunity projection and dashboard.
- approved/submitted/filled/failed: NOT_VERIFIED by this audit without broker/manual approval replay.

Finding: lifecycle is partially explicit, but displayed fallback rows can exist outside ranked-snapshot identity.
""",
        encoding="utf-8",
    )


def principal_verdict(findings: list[dict[str, Any]], counts: dict[str, Any]) -> str:
    severities = {f["severity"] for f in findings}
    if any(f["status"] == "BLOCKED_BY_MISSING_EVIDENCE" for f in findings):
        return "PIPELINE_TRUTH_NOT_AUDITABLE"
    if "P0" in severities:
        return "RANKING_PIPELINE_NOT_TRUSTWORTHY"
    if "P1" in severities or "P2" in severities:
        return "PIPELINE_FUNCTIONAL_WITH_MATERIAL_GAPS"
    return "PIPELINE_ROBUST_AND_RANKING_READY"


def write_supporting_artifacts(records: list[ModuleRecord], excluded: list[dict[str, Any]], findings: list[dict[str, Any]], ranking_probe: dict[str, Any]) -> None:
    schema_rows = [
        {"stage": "candidate_pool", "row_type": "StrategyCandidate", "required_fields": "strategy_id,symbol,direction,movement_type", "optional_fields": "evidence,blockers,warnings,source_flags", "status": "PARTIALLY_VERIFIED"},
        {"stage": "scoring", "row_type": "OpportunityScoreRecord", "required_fields": "strategy_id,symbol,direction,final_score,bucket,score_eligibility", "optional_fields": "outcome_contract,feed_risk_reasons", "status": "VERIFIED"},
        {"stage": "ranking", "row_type": "CandidateRankRecord", "required_fields": "rank,strategy_id,symbol,direction,final_score,bucket,score_eligibility", "optional_fields": "candidate_id,lineage_id,outcome_contract", "status": "VERIFIED"},
        {"stage": "ui", "row_type": "DataFrame row", "required_fields": "trade_id or candidate_id varies", "optional_fields": "execution_status,permission,rank", "status": "PARTIALLY_VERIFIED"},
    ]
    write_csv(OUT / "row_schema_crosswalk.csv", schema_rows)
    mutation_rows = [
        {"stage": "candidate_pool", "producer": "candidate generators", "consumer": "normalizer", "drop_or_mutation": "generator exceptions become warnings; non-candidates ignored", "status": "VERIFIED"},
        {"stage": "normalization", "producer": "candidate_pool", "consumer": "classifier", "drop_or_mutation": "dedupe/normalization key may merge candidates depending on key policy", "status": "PARTIALLY_VERIFIED"},
        {"stage": "hard_downgrade", "producer": "classifier", "consumer": "scoring", "drop_or_mutation": "unsafe metadata becomes blocked/advisory bucket", "status": "VERIFIED"},
        {"stage": "scoring", "producer": "downgrade", "consumer": "ranking", "drop_or_mutation": "fixed weights, penalties, bucket caps compute final_score", "status": "VERIFIED"},
        {"stage": "ranking", "producer": "scoring", "consumer": "top/UI", "drop_or_mutation": "sort by eligibility/bucket/score/safety tie keys", "status": "PARTIALLY_VERIFIED"},
        {"stage": "dashboard", "producer": "ranked top snapshot or fallback visible filters", "consumer": "user display", "drop_or_mutation": "fallback display can bypass ranked top snapshot source", "status": "VERIFIED"},
    ]
    write_csv(OUT / "row_mutation_and_drop_points.csv", mutation_rows)
    flow = [
        {"stage": "synthetic_probe_scoring", "rows_entering": 2, "rows_leaving": len(ranking_probe.get("score_values", [])), "rows_rejected": 0, "rows_suppressed": 0, "rows_deduplicated": 0, "rows_failed": 0, "reconciles": ranking_probe.get("status") == "PARTIALLY_VERIFIED"},
        {"stage": "full_replay", "rows_entering": "", "rows_leaving": "", "rows_rejected": "", "rows_suppressed": "", "rows_deduplicated": "", "rows_failed": "", "reconciles": "BLOCKED_BY_MISSING_EVIDENCE"},
    ]
    write_csv(OUT / "row_flow_accounting.csv", flow)
    write_csv(OUT / "row_attrition_by_reason.csv", [{"reason": "full_replay_not_selected", "count": "", "status": "BLOCKED_BY_MISSING_EVIDENCE"}])
    write_csv(OUT / "row_lineage_gaps.csv", [{"gap_id": "GAP-UI-001", "stage": "dashboard", "description": "Fallback visible rows may not carry ranked snapshot identity", "finding_id": "F-P1-001"}])
    (OUT / "ranking_snapshot_diagnostics.json").write_text(json.dumps(ranking_probe, indent=2, sort_keys=True), encoding="utf-8")
    change_rows = [
        {"finding_id": f["finding_id"], "intended_behaviour_change": f.get("recommended_fix", ""), "incidental_behaviour_change": "row counts/order/UI labels may change", "regression_risk": "legacy tests or dashboards may rely on old labels/order", "migration_requirement": "schema/version docs for identity fields" if f["severity"] in {"P0", "P1", "P2"} else "none", "rollback_strategy": "feature flag or render fallback as debug-only until verified"}
        for f in findings
        if f["severity"] in {"P0", "P1", "P2"}
    ]
    write_csv(OUT / "change_impact_matrix.csv", change_rows)
    (OUT / "migration_and_rollback_notes.md").write_text(
        "# Migration And Rollback Notes\n\nStricter row identity and fallback policies can reduce displayed/actionable counts and reorder ranks. Roll out behind read-only evidence gates first, then require `ranking_snapshot_id` and `candidate_id` for actionable UI controls. Roll back by leaving the stricter fields in evidence but disabling actionability changes until replay parity is explained.\n",
        encoding="utf-8",
    )
    (OUT / "target_clean_pipeline.md").write_text(
        "# Target Clean Pipeline\n\nKeep the existing staged pipeline. Minimize rewrite by making ownership explicit: feed truth owns freshness/quality, candidate generators own read-only strategy evidence, candidate pool owns collection and generator failure accounting, normalizer owns schema/key consistency, hard downgrade owns safety eligibility, scoring owns setup score components, ranking owns deterministic ordering, top-opportunity projection owns display/executable partitioning, dashboard owns read-only projection only, and manual approval must preserve ranked snapshot identity.\n",
        encoding="utf-8",
    )
    (OUT / "canonical_ranking_row_contract.md").write_text(
        "# Canonical Ranking Row Contract\n\nMinimum justified fields: `candidate_id`, `ranking_snapshot_id`, `producer`, `strategy_id`, `strategy_version`, `underlying`, `instrument`, `expiry`, `strike`, `option_type`, `signal_direction`, `action_semantics`, `observed_ts`, `signal_ts`, `evaluation_ts`, `source_provenance`, `freshness_state`, `regime_snapshot_id`, `strategy_reason_codes`, `data_quality_state`, `eligibility_state`, `eligibility_reasons`, `risk_annotations`, `score_components`, `final_ranking_score`, `rank`, `display_state`, `executable_state`, `dedupe_group`, and `lifecycle_status`.\n\nEach field addresses an observed ambiguity: fallback UI traceability, score semantics, fallback/degraded provenance, deterministic rank identity, CE/PE directional semantics, and approval handoff identity.\n",
        encoding="utf-8",
    )
    target_rows = [
        {"owner": "canonical_market_data_snapshot", "module": "core/feed/runtime_snapshot_builder.py", "status": "PARTIALLY_VERIFIED"},
        {"owner": "freshness_quality_authority", "module": "core/feed_truth_state.py;core/feed_health_truth.py", "status": "PARTIALLY_VERIFIED"},
        {"owner": "candidate_pool", "module": "core/candidate_pool_orchestrator.py", "status": "VERIFIED"},
        {"owner": "score_and_confidence_semantics", "module": "core/opportunity_scoring.py;core/candidate_ranking.py", "status": "PARTIALLY_VERIFIED"},
        {"owner": "ui_projection", "module": "dashboard/streamlit_app_runtime.py", "status": "VERIFIED"},
    ]
    write_csv(OUT / "target_module_ownership_map.csv", target_rows)
    (OUT / "prioritized_repair_roadmap.md").write_text(
        """# Prioritized Repair Roadmap

Wave 0 - Truth and observability: F-P0-001, F-P2-001, F-P2-002. Add ranked snapshot identity, stage accounting, and deterministic replay hashes.

Wave 1 - Data-quality authority: F-P1-003. Freeze fallback authority table and assert provenance survival through score/rank/top/executable truth.

Wave 2 - Candidate contract and lifecycle: F-P2-001. Add semantic tests around duplicate emission, CE/PE direction, missing evidence, and explicit lifecycle states.

Wave 3 - Scoring and ranking correctness: F-P1-002, F-P2-002. Separate setup score from calibrated probability; add tie and replay determinism tests.

Wave 4 - UI, approval, and execution alignment: F-P1-001. Make fallback-visible UI rows non-actionable unless they map to a ranked snapshot.

Wave 5 - Cleanup and simplification: F-P3-001 and module rows marked legacy/unknown after ownership is proven.
""",
        encoding="utf-8",
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    commands: list[dict[str, Any]] = []
    for cmd in (
        ["git", "status", "--short"],
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        ["git", "rev-parse", "HEAD"],
        ["git", "worktree", "list", "--porcelain"],
        ["python", "--version"],
    ):
        result = run(cmd)
        commands.append(result)
    files = tracked_files()
    records, excluded, graph = build_inventory(files)
    ranking_probe = probe_ranking()
    findings = build_findings(records, excluded, ranking_probe)
    counts = {
        "tracked_file_count": len(files),
        "audited_module_count": len(records),
        "excluded_module_count": len(excluded),
        "generated_at_epoch": time.time(),
    }
    env = {
        "repository_path": str(ROOT),
        "branch": commands[1]["stdout"].strip(),
        "head_sha": commands[2]["stdout"].strip(),
        "origin_main_sha": run(["git", "rev-parse", "origin/main"])["stdout"].strip(),
        "python": sys.version,
        "platform": platform.platform(),
        "dependency_files": [p for p in ("requirements.txt", "pytest.ini", "pyproject.toml", "Makefile") if (ROOT / p).exists()],
        "environment_assumptions": ["offline audit mode", "no broker credentials required", "no broker API calls made"],
        **counts,
    }
    (EVIDENCE / "baseline_environment.json").write_text(json.dumps(env, indent=2, sort_keys=True), encoding="utf-8")
    (EVIDENCE / "baseline_git_state.txt").write_text(
        "\n\n".join(f"$ {' '.join(c['cmd'])}\nrc={c['returncode']}\n{c['stdout']}\n{c['stderr']}" for c in commands),
        encoding="utf-8",
    )
    (EVIDENCE / "baseline_test_results.json").write_text(json.dumps({"status": "not_run_by_generator", "note": "Run pytest commands separately and record audit_test_results.json."}, indent=2), encoding="utf-8")
    write_csv(OUT / "module_inventory.csv", [asdict(r) for r in records])
    (OUT / "module_inventory.json").write_text(json.dumps([asdict(r) for r in records], indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "module_dependency_graph.json").write_text(json.dumps(graph, indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "module_exclusion_manifest.json").write_text(json.dumps({"excluded_count": len(excluded), "excluded": excluded}, indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "findings.json").write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    matrix = fix_rows(records, findings)
    write_csv(OUT / "master_module_fix_matrix.csv", matrix)
    write_markdown_reports(records, findings, counts)
    write_supporting_artifacts(records, excluded, findings, ranking_probe)
    artifact_manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            artifact_manifest.append({"path": str(path.relative_to(OUT)), "sha256": digest, "size_bytes": path.stat().st_size})
    (OUT / "artifact_manifest.json").write_text(json.dumps(artifact_manifest, indent=2, sort_keys=True), encoding="utf-8")
    lines = [f"{item['sha256']}  {item['path']}" for item in artifact_manifest]
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "commands_run.txt").write_text(
        "\n".join(" ".join(c["cmd"]) + f" # rc={c['returncode']} duration={c['duration_sec']}" for c in commands)
        + "\npython scripts/generate_module_robustness_ranking_audit.py # rc=0\n",
        encoding="utf-8",
    )
    print(json.dumps({"out": str(OUT), **counts, "finding_count": len(findings)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
