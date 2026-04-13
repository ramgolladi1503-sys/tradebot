from __future__ import annotations

import json
from pathlib import Path
from dataclasses import asdict

from core.position_state_engine import PositionState


def save_position_state(path: str, state: PositionState) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def load_position_state(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
