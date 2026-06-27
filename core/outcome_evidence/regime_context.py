import json
from pathlib import Path
from typing import List
from .evidence_models import RegimeContextEvidence


class RegimeContextLoader:
    """Loads and attaches regime context from regime_monitor.jsonl."""
    
    def __init__(self, source_path: Path):
        self.source_path = Path(source_path)
        self._regimes: List[dict] = []
        self._loaded = False
        
    def _load_if_needed(self):
        if self._loaded:
            return
        if not self.source_path.exists():
            self._loaded = True
            return
            
        with self.source_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    self._regimes.append(data)
                except json.JSONDecodeError:
                    continue
        
        self._regimes.sort(key=lambda r: float(r.get("timestamp_epoch", 0.0)))
        self._loaded = True
        
    def get_context_at(self, timestamp: float) -> RegimeContextEvidence:
        self._load_if_needed()
        if not self._regimes:
            return RegimeContextEvidence()
            
        # Find closest regime snapshot before or at timestamp
        best_match = None
        for regime in reversed(self._regimes):
            t = float(regime.get("timestamp_epoch", 0.0))
            if t <= timestamp:
                best_match = regime
                break
                
        if not best_match:
            return RegimeContextEvidence()
            
        return RegimeContextEvidence(
            trend=best_match.get("trend"),
            range_status=best_match.get("range_status"),
            entropy=best_match.get("entropy"),
            volatility=best_match.get("volatility"),
            iv_bucket=best_match.get("iv_bucket"),
            session_bucket=best_match.get("session_bucket"),
            is_expiry_day=best_match.get("is_expiry_day"),
            liquidity_bucket=best_match.get("liquidity_bucket"),
            spread_bucket=best_match.get("spread_bucket"),
            mip_event_context=best_match.get("mip_event_context")
        )
