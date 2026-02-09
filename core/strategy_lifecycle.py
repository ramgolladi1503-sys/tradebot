import json
import time
from pathlib import Path
from typing import Dict, Any

from config import config as cfg

STATES = ["RESEARCH", "PAPER", "PILOT", "LIVE", "QUARANTINE", "RETIRED"]


class StrategyLifecycle:
    def __init__(self, path: str | None = None):
        self.path = Path(path or getattr(cfg, "STRATEGY_LIFECYCLE_PATH", "logs/strategy_lifecycle.json"))
        self.state = {}
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text())
                self.state = raw.get("strategies", {}) or {}
        except Exception:
            self.state = {}

    def _save(self):
        try:
            self.path.parent.mkdir(exist_ok=True)
            payload = {"strategies": self.state, "updated_at": time.time()}
            self.path.write_text(json.dumps(payload, indent=2))
        except Exception:
            pass

    def get_state(self, strategy_id: str) -> str:
        if not strategy_id:
            return "RESEARCH"
        entry = self.state.get(strategy_id)
        if isinstance(entry, dict):
            return entry.get("state") or getattr(cfg, "STRATEGY_LIFECYCLE_DEFAULT_STATE", "PAPER")
        if isinstance(entry, str):
            return entry
        return getattr(cfg, "STRATEGY_LIFECYCLE_DEFAULT_STATE", "PAPER")

    def set_state(self, strategy_id: str, state: str, reason: str | None = None, meta: Dict[str, Any] | None = None):
        if state not in STATES:
            raise ValueError(f"Invalid lifecycle state: {state}")
        if not strategy_id:
            raise ValueError("strategy_id required")
        self.state[strategy_id] = {
            "state": state,
            "reason": reason,
            "meta": meta or {},
            "updated_at": time.time(),
        }
        self._save()

    def can_allocate(self, strategy_id: str, mode: str = "MAIN") -> tuple[bool, str]:
        state = self.get_state(strategy_id)
        if state in ("QUARANTINE", "RETIRED"):
            return False, f"lifecycle_{state.lower()}"
        if state == "RESEARCH" and not getattr(cfg, "ALLOW_RESEARCH_STRATEGIES", False):
            return False, "lifecycle_research"
        if getattr(cfg, "LIVE_PILOT_MODE", False):
            if mode == "MAIN" and state not in ("PILOT", "LIVE"):
                return False, "lifecycle_not_pilot_or_live"
            if mode != "MAIN" and state not in ("PAPER", "PILOT", "LIVE"):
                return False, "lifecycle_not_paper_or_live"
        return True, "ok"

    def snapshot(self):
        return self.state
