from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research.strategy_outcomes.contract import canonical_json_hash


def write_json_artifact(path: Path, payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return canonical_json_hash(payload)
