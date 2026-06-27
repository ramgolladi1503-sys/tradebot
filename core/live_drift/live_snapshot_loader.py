from typing import Dict, Optional
from core.live_drift.drift_models import LiveSnapshot


class LiveSnapshotLoader:
    """Loads current paper/live evidence observations."""
    
    def __init__(self):
        self._snapshots: Dict[str, LiveSnapshot] = {}
        
    def load_snapshot(self, snapshot: LiveSnapshot) -> None:
        self._snapshots[snapshot.strategy_id] = snapshot
        
    def get_snapshot(self, strategy_id: str) -> Optional[LiveSnapshot]:
        return self._snapshots.get(strategy_id)
