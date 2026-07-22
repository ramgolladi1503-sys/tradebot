from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PipelineContext:
    strategy_id: Optional[str] = None
    force_refresh: bool = False
    run_all: bool = False
    dry_run: bool = False
    run_id: Optional[str] = None
    base_commit: Optional[str] = None
    paper_only: bool = True

    # In-memory passing of structured artifacts. Engine input paths must be
    # supplied explicitly here; the orchestrator must never guess "latest".
    artifacts: Dict[str, Any] = field(default_factory=dict)

    # Locations
    reports_dir: str = "docs/strategy_pipeline"

    def get_artifact(self, key: str) -> Optional[Any]:
        return self.artifacts.get(key)

    def set_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value
