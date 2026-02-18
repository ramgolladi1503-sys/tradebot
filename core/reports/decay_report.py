import json
from pathlib import Path

from core.paths import logs_dir


def build_decay_report(day: str, out_path: Path) -> Path:
    state_path = logs_dir() / "strategy_decay_state.json"
    prob_path = logs_dir() / "strategy_decay_probs.json"

    decay_state = {}
    decay_prob = {}
    if state_path.exists():
        try:
            obj = json.loads(state_path.read_text())
            decay_state = obj.get("decay_state", {}) or {}
        except Exception:
            decay_state = {}
    if prob_path.exists():
        try:
            decay_prob = json.loads(prob_path.read_text()) or {}
        except Exception:
            decay_prob = {}

    out = {
        "date": day,
        "decay_state": decay_state,
        "decay_prob": decay_prob,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    return out_path
