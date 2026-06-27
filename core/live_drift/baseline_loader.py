from typing import Dict, Optional
from core.live_drift.drift_models import CertifiedBaseline


class BaselineLoader:
    """Loads certified expectations."""
    
    def __init__(self):
        self._baselines: Dict[str, CertifiedBaseline] = {}
        
    def load_baseline(self, baseline: CertifiedBaseline) -> None:
        self._baselines[baseline.strategy_id] = baseline
        
    def get_baseline(self, strategy_id: str) -> Optional[CertifiedBaseline]:
        return self._baselines.get(strategy_id)
