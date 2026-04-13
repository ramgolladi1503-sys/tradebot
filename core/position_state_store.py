from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.position_state_engine import PositionState, position_state_from_dict, position_state_to_dict


def save_position_state(path: str | Path, state: PositionState) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = position_state_to_dict(state)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    tmp.replace(target)


def load_position_state(path: str | Path) -> PositionState | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return position_state_from_dict(payload)
    except Exception:
        return None


def load_position_state_dict(path: str | Path) -> dict[str, Any] | None:
    state = load_position_state(path)
    if state is None:
        return None
    return position_state_to_dict(state)

