from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


_SCHEMA_VERSION = "all_strategy_option_campaign_universe_v1"
_ID_PATTERN = re.compile(r"[^A-Z0-9]+")
_SUPPORT_FILES = {
    "__init__.py",
    "_utils.py",
    "trade_builder.py",
    "position_sizer.py",
    "risk_manager.py",
    "soft_signal.py",
}


def _normalise_id(value: object) -> str:
    text = str(value or "").strip().upper()
    return _ID_PATTERN.sub("_", text).strip("_")


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json_root_must_be_object:{path}")
    return payload


def _repo_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _extract_declared_ids(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key).casefold()
            if key_text in {
                "strategy_id",
                "hypothesis_id",
                "canonical_strategy_id",
                "family_id",
                "entity_id",
            }:
                candidate = _normalise_id(value)
                if candidate:
                    found.add(candidate)
            found.update(_extract_declared_ids(value))
    elif isinstance(node, list):
        for value in node:
            found.update(_extract_declared_ids(value))
    return found


def _discover_strategy_files(root: Path) -> list[str]:
    strategy_root = root / "strategies"
    if not strategy_root.exists():
        raise ValueError(f"missing_strategy_root:{strategy_root}")
    return sorted(
        _repo_relative(root, path)
        for path in strategy_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _discover_frozen_hypothesis_files(root: Path) -> list[str]:
    research_root = root / "research"
    patterns = (
        "hypothesis_frozen.json",
        "frozen_hypothesis*.json",
        "*hypothesis_contract*.json",
        "FINAL_DECISION.md",
    )
    found: set[str] = set()
    for pattern in patterns:
        for path in research_root.rglob(pattern):
            if "__pycache__" in path.parts:
                continue
            found.add(_repo_relative(root, path))
    return sorted(found)


@dataclass(frozen=True)
class CampaignUniverseEntry:
    entity_id: str
    canonical_entity_id: str
    entity_class: str
    source_kind: str
    source_path: str | None
    callable_name: str | None
    strategy_kind: str | None
    certification_supported: bool | None
    authority_lane: bool
    option_campaign_action: str
    adapter_status: str
    inclusion_reason: str
    blocked_reason: str | None
    alias_of: str | None
    research_only: bool = True
    allowed_for_live_execution: bool = False


@dataclass(frozen=True)
class CampaignUniverse:
    entries: tuple[CampaignUniverseEntry, ...]
    summary: dict[str, object]


def _canonical_action(entry: dict[str, Any]) -> tuple[str, str, str]:
    strategy_id = _normalise_id(entry.get("strategy_id"))
    strategy_kind = str(entry.get("strategy_kind") or "")
    supported = bool(entry.get("certification_supported"))
    exists = bool(entry.get("module_exists_at_foundation"))

    if strategy_id == "NO_TRADE_CHOP":
        return (
            "RUN_NO_TRADE_FILTER_AUDIT",
            "NO_TRADE_FILTER_ADAPTER_REQUIRED",
            "No-trade filters must be measured as rejection coverage, not profit factor.",
        )
    if strategy_kind in {"helper_module", "test_fixture"}:
        return (
            "EXCLUDE_SUPPORT_ENTITY",
            "NOT_APPLICABLE",
            "Support or fixture modules are inventoried but are not standalone strategies.",
        )
    if strategy_kind in {"aggregate_engine", "deferred"}:
        return (
            "DEFER_UNTIL_CHILD_CAMPAIGNS_COMPLETE",
            "AGGREGATE_ADAPTER_DEFERRED",
            "Aggregate and ensemble owners run only after child strategies have comparable analytics.",
        )
    if not exists:
        return (
            "BLOCK_MISSING_IMPLEMENTATION",
            "IMPLEMENTATION_REQUIRED",
            "The declared strategy implementation is absent from the current checkout.",
        )
    if supported:
        status = (
            "IMPLEMENTED"
            if strategy_id == "COMPRESSION_BREAKOUT"
            else "ADAPTER_REQUIRED"
        )
        return (
            "RUN_CE_PE_CANDLE_CAMPAIGN",
            status,
            "Canonical strategy is eligible for the common CE/PE candle-economics protocol.",
        )
    return (
        "REVIEW_NONCERTIFIABLE_ENTITY",
        "MANUAL_CLASSIFICATION_REQUIRED",
        "The registry does not currently support certification for this entity.",
    )


def build_campaign_universe(repo_root: Path | None = None) -> CampaignUniverse:
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    registry_path = (
        root
        / "research/option_e2e_recertification_v4/inventory/"
        "canonical_strategy_registry_v4.json"
    )
    alias_path = (
        root
        / "research/option_e2e_recertification_v4/inventory/alias_graph_v4.json"
    )
    priority_path = (
        root
        / "research/option_e2e_recertification_v4/"
        "all_strategy_authority_closure_v1/priority_summary.json"
    )
    historical_path = (
        root
        / "research/option_e2e_recertification_v4/inventory_v4_1/"
        "historical_strategy_inventory_v4_1.json"
    )

    registry = _load_json(registry_path)
    alias_graph = _load_json(alias_path)
    priorities = _load_json(priority_path)
    historical = _load_json(historical_path)

    entries: list[CampaignUniverseEntry] = []
    covered_ids: set[str] = set()
    registry_paths: set[str] = set()

    authority_ids = {
        _normalise_id(value)
        for value in list(priorities.get("ordered_strategy_ids") or [])
        if _normalise_id(value)
    }

    for row in list(registry.get("entries") or []):
        if not isinstance(row, dict):
            raise ValueError("invalid_registry_entry")
        strategy_id = _normalise_id(row.get("strategy_id"))
        if not strategy_id:
            raise ValueError("registry_entry_missing_strategy_id")
        source_path = str(row.get("module_path") or "") or None
        if source_path:
            registry_paths.add(source_path)
        action, adapter_status, reason = _canonical_action(row)
        blocked_reason = str(row.get("blocked_reason") or "") or None
        entity_class = (
            "CANONICAL_STRATEGY"
            if action in {"RUN_CE_PE_CANDLE_CAMPAIGN", "RUN_NO_TRADE_FILTER_AUDIT"}
            else "CANONICAL_NONRUNNABLE_ENTITY"
        )
        entries.append(
            CampaignUniverseEntry(
                entity_id=strategy_id,
                canonical_entity_id=strategy_id,
                entity_class=entity_class,
                source_kind="CANONICAL_REGISTRY",
                source_path=source_path,
                callable_name=str(row.get("callable_name") or "") or None,
                strategy_kind=str(row.get("strategy_kind") or "") or None,
                certification_supported=(
                    bool(row.get("certification_supported"))
                    if "certification_supported" in row
                    else None
                ),
                authority_lane=strategy_id in authority_ids,
                option_campaign_action=action,
                adapter_status=adapter_status,
                inclusion_reason=reason,
                blocked_reason=blocked_reason,
                alias_of=None,
            )
        )
        covered_ids.add(strategy_id)

    for authority_id in sorted(authority_ids - covered_ids):
        entries.append(
            CampaignUniverseEntry(
                entity_id=authority_id,
                canonical_entity_id=authority_id,
                entity_class="FROZEN_RESEARCH_HYPOTHESIS",
                source_kind="AUTHORITY_PRIORITY_LANE",
                source_path=None,
                callable_name=None,
                strategy_kind="research_hypothesis",
                certification_supported=None,
                authority_lane=True,
                option_campaign_action="RUN_IF_FROZEN_SIGNAL_ADAPTER_EXISTS",
                adapter_status="FROZEN_SIGNAL_ADAPTER_REQUIRED",
                inclusion_reason=(
                    "The merged all-strategy authority campaign treats this as a distinct "
                    "strategy or hypothesis lane, so it cannot be omitted from analytics."
                ),
                blocked_reason="Frozen causal signal adapter and option-price coverage must be bound.",
                alias_of=None,
            )
        )
        covered_ids.add(authority_id)

    alias_ids: set[str] = set()
    for edge in list(alias_graph.get("edges") or []):
        if not isinstance(edge, dict):
            raise ValueError("invalid_alias_edge")
        alias = _normalise_id(edge.get("alias"))
        canonical = _normalise_id(edge.get("canonical_strategy_id"))
        if not alias or not canonical:
            raise ValueError("alias_edge_missing_identity")
        alias_ids.add(alias)
        entries.append(
            CampaignUniverseEntry(
                entity_id=alias,
                canonical_entity_id=canonical,
                entity_class="ALIAS",
                source_kind="ALIAS_GRAPH",
                source_path=None,
                callable_name=None,
                strategy_kind="alias",
                certification_supported=None,
                authority_lane=canonical in authority_ids,
                option_campaign_action="COLLAPSE_INTO_CANONICAL_RUN",
                adapter_status="NOT_APPLICABLE",
                inclusion_reason=str(edge.get("evidence") or "Alias graph binding."),
                blocked_reason=None,
                alias_of=canonical,
            )
        )

    strategy_files = _discover_strategy_files(root)
    unclassified_strategy_files: list[str] = []
    for path in strategy_files:
        if path in registry_paths:
            continue
        name = Path(path).name
        if name in _SUPPORT_FILES or name.startswith("test_"):
            entries.append(
                CampaignUniverseEntry(
                    entity_id=_normalise_id(Path(path).stem),
                    canonical_entity_id=_normalise_id(Path(path).stem),
                    entity_class="DISCOVERED_SUPPORT_FILE",
                    source_kind="FILESYSTEM_DISCOVERY",
                    source_path=path,
                    callable_name=None,
                    strategy_kind="support_file",
                    certification_supported=False,
                    authority_lane=False,
                    option_campaign_action="EXCLUDE_SUPPORT_ENTITY",
                    adapter_status="NOT_APPLICABLE",
                    inclusion_reason="Discovered strategy-tree support file explicitly classified.",
                    blocked_reason=None,
                    alias_of=None,
                )
            )
        else:
            unclassified_strategy_files.append(path)
            entries.append(
                CampaignUniverseEntry(
                    entity_id=_normalise_id(Path(path).stem),
                    canonical_entity_id=_normalise_id(Path(path).stem),
                    entity_class="UNCLASSIFIED_STRATEGY_FILE",
                    source_kind="FILESYSTEM_DISCOVERY",
                    source_path=path,
                    callable_name=None,
                    strategy_kind=None,
                    certification_supported=None,
                    authority_lane=False,
                    option_campaign_action="BLOCK_PENDING_CLASSIFICATION",
                    adapter_status="CLASSIFICATION_REQUIRED",
                    inclusion_reason="A Python file exists under strategies/ but is absent from the canonical registry.",
                    blocked_reason="Must be classified before campaign publication.",
                    alias_of=None,
                )
            )

    historical_declared_ids = _extract_declared_ids(historical)
    uncovered_historical_ids = sorted(
        historical_declared_ids - covered_ids - alias_ids
    )
    for entity_id in uncovered_historical_ids:
        entries.append(
            CampaignUniverseEntry(
                entity_id=entity_id,
                canonical_entity_id=entity_id,
                entity_class="HISTORICAL_UNCLASSIFIED_ENTITY",
                source_kind="HISTORICAL_INVENTORY_V4_1",
                source_path=(
                    "research/option_e2e_recertification_v4/inventory_v4_1/"
                    "historical_strategy_inventory_v4_1.json"
                ),
                callable_name=None,
                strategy_kind=None,
                certification_supported=None,
                authority_lane=False,
                option_campaign_action="BLOCK_PENDING_CLASSIFICATION",
                adapter_status="CLASSIFICATION_REQUIRED",
                inclusion_reason="Historical inventory declares an entity not covered by registry, authority lanes, or aliases.",
                blocked_reason="Must be classified before analytics publication.",
                alias_of=None,
            )
        )

    frozen_hypothesis_files = _discover_frozen_hypothesis_files(root)
    rows = sorted(
        entries,
        key=lambda item: (
            item.canonical_entity_id,
            item.entity_class,
            item.entity_id,
            item.source_path or "",
        ),
    )

    duplicate_ids = sorted(
        entity_id
        for entity_id in {row.entity_id for row in rows}
        if sum(1 for row in rows if row.entity_id == entity_id) > 1
        and entity_id not in alias_ids
    )
    actions: dict[str, int] = {}
    adapter_statuses: dict[str, int] = {}
    for row in rows:
        actions[row.option_campaign_action] = actions.get(row.option_campaign_action, 0) + 1
        adapter_statuses[row.adapter_status] = adapter_statuses.get(row.adapter_status, 0) + 1

    hard_gaps = sorted(
        set(unclassified_strategy_files)
        | {f"historical_id:{value}" for value in uncovered_historical_ids}
        | {f"duplicate_id:{value}" for value in duplicate_ids}
    )
    summary_without_hash: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "strategy_file_count": len(strategy_files),
        "canonical_registry_entry_count": len(list(registry.get("entries") or [])),
        "authority_lane_count": len(authority_ids),
        "alias_count": len(list(alias_graph.get("edges") or [])),
        "historical_inventory_entity_count_claim": int(
            dict(historical.get("counts") or {}).get("entities_total", 0)
        ),
        "historical_inventory_strategy_count_claim": int(
            dict(historical.get("counts") or {}).get("strategies_counted", 0)
        ),
        "historical_declared_id_count": len(historical_declared_ids),
        "frozen_hypothesis_file_count": len(frozen_hypothesis_files),
        "frozen_hypothesis_files": frozen_hypothesis_files,
        "universe_row_count": len(rows),
        "action_counts": dict(sorted(actions.items())),
        "adapter_status_counts": dict(sorted(adapter_statuses.items())),
        "hard_gap_count": len(hard_gaps),
        "hard_gaps": hard_gaps,
        "coverage_complete": len(hard_gaps) == 0,
        "publication_rule": (
            "Every canonical strategy, authority hypothesis lane, alias, and discovered "
            "strategy-tree file must receive an explicit campaign action."
        ),
        "profit_factor_rule": (
            "Profit factor is reported only for entries that produce causal CE/PE trades; "
            "no-trade filters, helpers, aliases, blocked hypotheses, and aggregate engines "
            "remain visible with non-PF statuses."
        ),
        "research_only": True,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }
    summary = dict(summary_without_hash)
    summary["semantic_hash"] = _canonical_hash(
        {
            "summary": summary_without_hash,
            "entries": [asdict(row) for row in rows],
        }
    )
    return CampaignUniverse(entries=tuple(rows), summary=summary)


def write_campaign_universe(
    universe: CampaignUniverse,
    output_dir: Path,
) -> dict[str, str]:
    output = output_dir.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output_directory_not_empty:{output}")
    output.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": _SCHEMA_VERSION,
        "summary": universe.summary,
        "entries": [asdict(row) for row in universe.entries],
    }
    json_text = json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"
    json_path = output / "all_strategy_option_campaign_universe.json"
    json_path.write_text(json_text, encoding="utf-8")

    csv_path = output / "all_strategy_option_campaign_universe.csv"
    fieldnames = list(asdict(universe.entries[0]).keys()) if universe.entries else []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            for row in universe.entries:
                writer.writerow(asdict(row))

    summary_path = output / "all_strategy_option_campaign_summary.json"
    summary_text = json.dumps(
        universe.summary,
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
    ) + "\n"
    summary_path.write_text(summary_text, encoding="utf-8")

    hashes: dict[str, str] = {}
    for path in (json_path, csv_path, summary_path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[path.name] = digest
        path.with_suffix(path.suffix + ".sha256").write_text(
            f"{digest}  {path.name}\n",
            encoding="utf-8",
        )
    return hashes
