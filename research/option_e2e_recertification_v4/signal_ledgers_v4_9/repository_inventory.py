from __future__ import annotations

import json
from pathlib import Path


def load_repository_inventory(repo_root: Path) -> dict[str, object]:
    path = repo_root / "research" / "option_e2e_recertification_v4" / "inventory" / "canonical_strategy_registry_v4.json"
    return json.loads(path.read_text(encoding="utf-8"))
