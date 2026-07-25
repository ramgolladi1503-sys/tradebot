from __future__ import annotations

import json
from pathlib import Path


def load_repository_inventory(repo_root: Path) -> dict[str, object]:
    path = repo_root / "research" / "option_e2e_recertification_v4" / "inventory" / "canonical_strategy_registry_v4.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_alias_graph(repo_root: Path) -> dict[str, object]:
    path = repo_root / "research" / "option_e2e_recertification_v4" / "inventory" / "alias_graph_v4.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_historical_claim_map(repo_root: Path) -> dict[str, object]:
    path = repo_root / "research" / "option_e2e_recertification_v4" / "inventory" / "historical_claim_map_v4.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_historical_strategy_inventory(repo_root: Path) -> dict[str, object]:
    path = repo_root / "research" / "option_e2e_recertification_v4" / "inventory_v4_1" / "historical_strategy_inventory_v4_1.json"
    return json.loads(path.read_text(encoding="utf-8"))
