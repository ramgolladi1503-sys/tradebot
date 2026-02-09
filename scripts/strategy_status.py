import json
from pathlib import Path

from core.strategy_lifecycle import StrategyLifecycle


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def main():
    lifecycle = StrategyLifecycle()
    decay_path = Path("logs/strategy_decay_probs.json")
    decay = _load_json(decay_path) if decay_path.exists() else {}

    print("Strategy\tstate\tdecay_prob\treason")
    for strat, entry in (lifecycle.snapshot() or {}).items():
        if isinstance(entry, dict):
            state = entry.get("state")
            reason = entry.get("reason")
        else:
            state = entry
            reason = None
        prob = decay.get(strat)
        if isinstance(prob, dict):
            prob = prob.get("decay_probability")
        print(f"{strat}\t{state}\t{prob}\t{reason}")


if __name__ == "__main__":
    main()
