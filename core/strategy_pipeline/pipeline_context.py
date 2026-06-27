from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class PipelineContext:
    strategy_id: Optional[str] = None
    force_refresh: bool = False
    run_all: bool = False
    dry_run: bool = False
    
    # In-memory passing of structured artifacts
    artifacts: Dict[str, Any] = field(default_factory=dict)
    
    # Locations
    reports_dir: str = "docs/strategy_pipeline"
    
    def get_artifact(self, key: str) -> Optional[Any]:
        return self.artifacts.get(key)
        
    def set_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value
