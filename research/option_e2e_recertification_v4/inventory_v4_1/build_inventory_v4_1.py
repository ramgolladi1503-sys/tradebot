from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "research" / "option_e2e_recertification_v4" / "inventory_v4_1"
DOC_PATH = REPO_ROOT / "docs" / "agent_reviews" / "option_e2e_historical_inventory_v4_1.md"

NON_STRATEGY_IDS = {
    "BANKNIFTY_INTRADAY",
    "NIFTY_INTRADAY",
    "SENSEX_INTRADAY",
    "_INIT_",
    "_UTILS",
    "POSITION_SIZER",
    "RISK_MANAGER",
    "TRADE_BUILDER",
    "TEST_STRAT",
    "PRO_DECISION_ADAPTER",
    "SOFT_SIGNAL",
}

FAMILY_PATTERNS: dict[str, list[str]] = {
    "RESIDUAL_MEAN_REVERSION": ["residual mean", "residual_mean", "residual-mean", "mean-reversion regeneration"],
    "OPENING_STATE_MOMENTUM": ["opening-state", "opening state", "opening_state"],
    "CONSTITUENT_LEAD_LAG_WEIGHTED": ["lead-lag", "lead lag", "weighted"],
    "CONSTITUENT_BREADTH_UNWEIGHTED": ["breadth", "unweighted"],
    "RSI2": ["rsi2", "rsi 2"],
    "ORB_RETEST_DRIVE": ["opening_range_retest", "opening range retest", "orb", "opening drive"],
    "VWAP_VARIANTS": ["vwap"],
    "COMPRESSION": ["compression"],
    "TREND": ["trend_pullback", "volatility_trend", "trend"],
    "MRE": ["mean_reversion_extension", "mre"],
    "EXHAUSTION": ["exhaustion"],
    "HTF": ["htf", "higher time frame"],
    "CANDIDATE_INTENT": ["candidateintent", "candidate intent"],
    "ZERO_HERO": ["zero_hero", "zero hero", "zero-hero"],
    "ML_DISCOVERY": ["ml_strategy_discovery", "ml strategy discovery"],
    "GOVERNED_FIVE_MINUTE_DISCOVERY": ["five-minute governed", "five-minute-governed", "governed five-minute", "five_minute_governed"],
}

VERDICT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:CERTIFIED|RECERTIFIED|REJECTED|BLOCKED|FAILED|READY|VERIFIED|VALIDATED|FOUND|CLOSED|UNPROVEN|PROVEN)[A-Z0-9_]*)\b"
)


@dataclass(frozen=True)
class SourceHit:
    path: str
    sha256: str | None
    families: tuple[str, ...]
    verdicts: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, proc.stdout.strip()


def _read_text(path: Path, limit: int = 1_000_000) -> str:
    try:
        data = path.read_bytes()[:limit]
    except OSError:
        return ""
    return data.decode("utf-8", errors="ignore")


def _families_for_text(text: str) -> list[str]:
    folded = text.lower()
    found = []
    for family, patterns in FAMILY_PATTERNS.items():
        if any(pattern in folded for pattern in patterns):
            found.append(family)
    return sorted(found)


def _verdicts_for_text(text: str) -> list[str]:
    skip = {"CERTIFIED", "RECERTIFIED", "REJECTED", "BLOCKED", "FAILED", "READY", "VERIFIED", "VALIDATED"}
    verdicts = sorted({match.group(1) for match in VERDICT_RE.finditer(text) if match.group(1) not in skip})
    return verdicts[:50]


def _module_callable_names(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


def _strategy_id_from_path(path: Path) -> str:
    stem = path.stem
    return re.sub(r"[^A-Za-z0-9]+", "_", stem).upper()


def _classify_strategy_file(path: Path, v4_by_path: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    v4 = v4_by_path.get(rel, {})
    strategy_id = v4.get("strategy_id") or _strategy_id_from_path(path)
    callable_names = _module_callable_names(path)
    text = _read_text(path)
    non_strategy = strategy_id in NON_STRATEGY_IDS or rel.endswith("/__init__.py")
    if "strategy_registry.py" in rel:
        entity_type = "registry"
    elif strategy_id == "ENSEMBLE":
        entity_type = "aggregate_or_deferred_strategy"
    elif strategy_id == "PRO_STRATEGY_ENGINE":
        entity_type = "aggregate_engine"
    elif non_strategy:
        entity_type = "non_strategy_support"
    else:
        entity_type = "strategy"
    return {
        "id": strategy_id,
        "entity_type": entity_type,
        "path": rel,
        "sha256": _sha256(path),
        "callables": callable_names,
        "families": _families_for_text(rel + "\n" + text),
        "v4_strategy_kind": v4.get("strategy_kind"),
        "v4_certification_track": v4.get("certification_track"),
        "counted_as_strategy": entity_type == "strategy",
    }


def _classify_registry_only_entry(entry: dict[str, Any]) -> dict[str, Any]:
    strategy_id = entry["strategy_id"]
    if strategy_id in NON_STRATEGY_IDS or entry.get("strategy_kind") in {"helper_module", "test_fixture"}:
        entity_type = "non_strategy_support"
    elif entry.get("strategy_kind") == "aggregate_engine":
        entity_type = "aggregate_engine"
    elif entry.get("strategy_kind") == "deferred":
        entity_type = "aggregate_or_deferred_strategy"
    else:
        entity_type = "strategy"
    return {
        "id": strategy_id,
        "entity_type": entity_type,
        "path": entry.get("module_path"),
        "sha256": entry.get("source_sha256"),
        "callables": [entry["callable_name"]] if entry.get("callable_name") else [],
        "families": _families_for_text(strategy_id + "\n" + str(entry.get("module_path", ""))),
        "v4_strategy_kind": entry.get("strategy_kind"),
        "v4_certification_track": entry.get("certification_track"),
        "counted_as_strategy": entity_type == "strategy",
        "registry_only": True,
    }


def _iter_evidence_paths() -> list[Path]:
    roots = ["docs", "research", "scripts", "tests"]
    selected: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(part in rel for part in ["/.git/", "__pycache__"]):
                continue
            if rel.startswith("research/option_e2e_recertification_v4/inventory_v4_1/"):
                continue
            if rel == "docs/agent_reviews/option_e2e_historical_inventory_v4_1.md":
                continue
            name = path.name.lower()
            if any(token in name or token in rel.lower() for token in [
                "strategy",
                "orb",
                "vwap",
                "mean_reversion",
                "rsi2",
                "lead_lag",
                "breadth",
                "zero_hero",
                "discovery",
                "option_e2e",
                "candidate",
            ]):
                selected.append(path)
    return sorted(selected)


def _source_hits() -> list[SourceHit]:
    hits = []
    for path in _iter_evidence_paths():
        text = _read_text(path)
        families = tuple(_families_for_text(path.as_posix() + "\n" + text))
        verdicts = tuple(_verdicts_for_text(text))
        if families or verdicts:
            hits.append(SourceHit(path.relative_to(REPO_ROOT).as_posix(), _sha256(path), families, verdicts))
    return hits


def _git_history_hits() -> list[dict[str, str]]:
    code, out = _run([
        "git",
        "log",
        "--all",
        "--date=short",
        "--pretty=format:%H%x09%ad%x09%s",
        "--",
        "strategies",
        "docs",
        "tests",
        "scripts",
        "research",
    ], timeout=60)
    rows = []
    if code != 0:
        return [{"error": out}]
    wanted = re.compile(r"option|strategy|orb|vwap|mean|rsi|lead|breadth|zero|discovery|candidate|verdict|recert", re.I)
    for line in out.splitlines():
        if wanted.search(line):
            sha, date, subject = (line.split("\t", 2) + ["", ""])[:3]
            rows.append({"sha": sha, "date": date, "subject": subject})
    return rows[:300]


def _worktree_hits() -> list[dict[str, str]]:
    code, out = _run(["git", "worktree", "list", "--porcelain"])
    if code != 0:
        return [{"error": out}]
    rows = []
    current: dict[str, str] = {}
    for line in out.splitlines() + [""]:
        if not line:
            if current:
                if any(token in current.get("worktree", "").lower() + current.get("branch", "").lower() for token in [
                    "strategy",
                    "option",
                    "orb",
                    "vwap",
                    "mean",
                    "lead",
                    "discovery",
                ]):
                    rows.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return rows


def _pr_metadata() -> dict[str, Any]:
    code, out = _run(["gh", "pr", "view", "710", "--json", "number,title,state,url,headRefName,baseRefName,commits,files"], timeout=30)
    if code != 0 or not out:
        return {"available": False, "error": out}
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        return {"available": False, "error": str(exc)}
    return {"available": True, **data}


def build_inventory() -> dict[str, Any]:
    v4_path = REPO_ROOT / "research" / "option_e2e_recertification_v4" / "inventory" / "canonical_strategy_registry_v4.json"
    v4_entries = json.loads(v4_path.read_text(encoding="utf-8")).get("entries", [])
    v4_by_path = {entry["module_path"]: entry for entry in v4_entries}
    strategy_files = sorted((REPO_ROOT / "strategies").rglob("*.py"))
    entities = [_classify_strategy_file(path, v4_by_path) for path in strategy_files]
    present_paths = {entity["path"] for entity in entities}
    for entry in v4_entries:
        if entry.get("module_path") not in present_paths:
            entities.append(_classify_registry_only_entry(entry))
    evidence_hits = _source_hits()
    git_history_hits = _git_history_hits()
    worktree_hits = _worktree_hits()
    family_evidence: dict[str, list[dict[str, Any]]] = {family: [] for family in FAMILY_PATTERNS}
    durable_verdicts: dict[str, list[dict[str, str]]] = {}
    for hit in evidence_hits:
        for family in hit.families:
            if len(family_evidence[family]) < 25:
                family_evidence[family].append({"path": hit.path, "sha256": hit.sha256, "verdicts": list(hit.verdicts[:10])})
        for verdict in hit.verdicts:
            durable_verdicts.setdefault(verdict, [])
            if len(durable_verdicts[verdict]) < 10:
                durable_verdicts[verdict].append({"path": hit.path, "sha256": hit.sha256 or ""})
    for row in git_history_hits:
        text = "\n".join(str(value) for value in row.values())
        for family in _families_for_text(text):
            if len(family_evidence[family]) < 25:
                family_evidence[family].append({
                    "path": "git:" + row.get("sha", "unknown"),
                    "sha256": row.get("sha"),
                    "verdicts": ["GIT_HISTORY_MENTION"],
                })
    for row in worktree_hits:
        text = "\n".join(str(value) for value in row.values())
        for family in _families_for_text(text):
            if len(family_evidence[family]) < 25:
                family_evidence[family].append({
                    "path": row.get("worktree", "git-worktree"),
                    "sha256": row.get("HEAD"),
                    "verdicts": ["WORKTREE_MENTION"],
                })

    counts = {
        "strategy_files_scanned": len(strategy_files),
        "entities_total": len(entities),
        "strategies_counted": sum(1 for entity in entities if entity["counted_as_strategy"]),
        "non_strategy_support_count": sum(1 for entity in entities if entity["entity_type"] == "non_strategy_support"),
        "aggregate_or_registry_count": sum(1 for entity in entities if entity["entity_type"] in {"aggregate_engine", "aggregate_or_deferred_strategy", "registry"}),
        "evidence_files_with_family_or_verdict_hits": len(evidence_hits),
        "families_with_evidence": sum(1 for hits in family_evidence.values() if hits),
        "durable_verdict_labels": len(durable_verdicts),
    }
    _, head = _run(["git", "rev-parse", "HEAD"])
    pr_metadata = _pr_metadata()
    return {
        "schema_version": "option_e2e_historical_inventory_v4_1",
        "mode": "OFFLINE_INVENTORY_NO_ECONOMIC_REPLAY",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "source_head": head,
        "entity_type_rules": {
            "strategy": "Counted only for actual strategy modules/generators.",
            "non_strategy_support": "Support/helper/test fixture modules are not counted as strategies.",
            "aggregate_engine": "Orchestrating engine, not a standalone strategy family.",
            "aggregate_or_deferred_strategy": "Composite/deferred strategy surface, not independently certifiable here.",
            "registry": "Registry surface, not a strategy.",
        },
        "excluded_from_strategy_count": sorted(NON_STRATEGY_IDS),
        "counts": counts,
        "entities": entities,
        "family_evidence": family_evidence,
        "durable_verdicts": durable_verdicts,
        "git_history_hits": git_history_hits,
        "worktree_hits": worktree_hits,
        "pr_metadata": pr_metadata,
        "external_evidence_roots": [
            {"path": "docs/agent_reviews", "status": "scanned"},
            {"path": "docs/research", "status": "scanned"},
            {"path": "research", "status": "scanned"},
            {"path": "scripts", "status": "scanned"},
            {"path": "tests", "status": "scanned"},
            {"path": "git log --all", "status": "scanned"},
            {"path": "git worktree list", "status": "scanned"},
            {"path": "gh pr view 710", "status": "available" if pr_metadata.get("available") else "unavailable"},
        ],
    }


def _write_json(path: Path, payload: Any) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_report(inventory: dict[str, Any], inventory_hash: str) -> str:
    counts = inventory["counts"]
    lines = [
        "# Option E2E Historical Inventory v4.1",
        "",
        "decision: HISTORICAL_STRATEGY_INVENTORY_V4_1_REPAIRED",
        "mode: OFFLINE_INVENTORY_NO_ECONOMIC_REPLAY",
        "read_only: true",
        "is_order_action: false",
        "broker_api_called: false",
        "allowed_for_live_execution: false",
        "append: false",
        f"source_head: `{inventory['source_head']}`",
        f"inventory_sha256: `{inventory_hash}`",
        "",
        "## Scope",
        "",
        "This repair inventories historical strategy and strategy-adjacent entities only. It does not run economic replay, broker APIs, resolver logic, replay engine changes, WFA, production files, `core/**`, or `strategies/**` edits.",
        "",
        "## Counts",
        "",
        f"- Strategy files scanned: {counts['strategy_files_scanned']}",
        f"- Entities total: {counts['entities_total']}",
        f"- Counted strategies: {counts['strategies_counted']}",
        f"- Non-strategy support entities excluded from strategy count: {counts['non_strategy_support_count']}",
        f"- Aggregate/registry entities: {counts['aggregate_or_registry_count']}",
        f"- Evidence files with family or verdict hits: {counts['evidence_files_with_family_or_verdict_hits']}",
        f"- Required families with evidence: {counts['families_with_evidence']} / {len(FAMILY_PATTERNS)}",
        f"- Durable verdict labels mapped: {counts['durable_verdict_labels']}",
        "",
        "## Entity Separation",
        "",
        "The following ids are explicitly not counted as strategies: "
        + ", ".join(f"`{item}`" for item in inventory["excluded_from_strategy_count"])
        + ".",
        "",
        "## Counted Strategy Entities",
        "",
    ]
    for entity in inventory["entities"]:
        if entity["counted_as_strategy"]:
            lines.append(f"- `{entity['id']}`: `{entity['path']}`; families={entity['families'] or []}; sha256=`{entity['sha256']}`")
    lines.extend(["", "## Non-Strategy / Aggregate Entities", ""])
    for entity in inventory["entities"]:
        if not entity["counted_as_strategy"]:
            lines.append(f"- `{entity['id']}`: entity_type=`{entity['entity_type']}`; path=`{entity['path']}`; sha256=`{entity['sha256']}`")
    lines.extend(["", "## Required Family Evidence Map", ""])
    for family, hits in inventory["family_evidence"].items():
        lines.append(f"### {family}")
        if not hits:
            lines.append("- `UNKNOWN`: no matching evidence found in scanned roots.")
        for hit in hits[:10]:
            verdicts = ", ".join(f"`{v}`" for v in hit["verdicts"]) if hit["verdicts"] else "`MENTION_ONLY`"
            lines.append(f"- `{hit['path']}`; sha256=`{hit['sha256']}`; verdicts={verdicts}")
        lines.append("")
    lines.extend(["## Durable Verdict Labels", ""])
    for verdict, hits in sorted(inventory["durable_verdicts"].items()):
        lines.append(f"- `{verdict}`: {len(hits)} evidence path(s) retained in JSON sample")
    lines.extend([
        "",
        "## PR Metadata",
        "",
        f"- gh_available: `{inventory['pr_metadata'].get('available')}`",
        f"- pr: `{inventory['pr_metadata'].get('number')}` `{inventory['pr_metadata'].get('title')}`",
        f"- url: {inventory['pr_metadata'].get('url')}",
        f"- commits_seen: `{len(inventory['pr_metadata'].get('commits', [])) if inventory['pr_metadata'].get('available') else 0}`",
        f"- files_seen: `{len(inventory['pr_metadata'].get('files', [])) if inventory['pr_metadata'].get('available') else 0}`",
        "",
        "## Commands",
        "",
        "```bash",
        "python -m research.option_e2e_recertification_v4.inventory_v4_1.build_inventory_v4_1",
        "pytest -q tests/research/option_e2e/test_inventory_v4_1.py",
        "git status --short --branch",
        "```",
        "",
        "## Claim Boundary",
        "",
        "This proves only an offline, hash-addressed historical inventory repair. It does not prove profitability, paper readiness, live readiness, option PnL correctness, broker execution readiness, or Phase 2 integration.",
        "",
    ])
    text = "\n".join(lines)
    DOC_PATH.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory()
    inventory_hash = _write_json(OUT_DIR / "historical_strategy_inventory_v4_1.json", inventory)
    report_hash = _write_report(inventory, inventory_hash)
    manifest = {
        "schema_version": "option_e2e_historical_inventory_v4_1_manifest",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "artifacts": {
            "historical_strategy_inventory_v4_1.json": inventory_hash,
            "docs/agent_reviews/option_e2e_historical_inventory_v4_1.md": report_hash,
        },
        "counts": inventory["counts"],
    }
    manifest_hash = _write_json(OUT_DIR / "manifest_v4_1.json", manifest)
    (OUT_DIR / "manifest_v4_1.json.sha256").write_text(manifest_hash + "\n", encoding="utf-8")
    print(json.dumps({"inventory_sha256": inventory_hash, "report_sha256": report_hash, "manifest_sha256": manifest_hash, "counts": inventory["counts"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
