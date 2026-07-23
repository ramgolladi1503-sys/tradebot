from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def _new_run_id() -> str:
    return uuid4().hex


@dataclass
class PipelineContext:
    strategy_id: Optional[str] = None
    run_id: str = field(default_factory=_new_run_id)
    execution_mode: str = "RESEARCH"
    force_refresh: bool = False
    run_all: bool = False
    dry_run: bool = False
    include_drift: bool = False
    require_verified_results: bool = True
    base_commit: Optional[str] = None

    # In-memory passing of structured artifacts.
    artifacts: Dict[str, Any] = field(default_factory=dict)

    # Exact, caller-selected inputs and CLI args. No "latest file" discovery.
    engine_inputs: Dict[str, List[str]] = field(default_factory=dict)
    engine_input_hashes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    engine_args: Dict[str, List[str]] = field(default_factory=dict)
    cache_manifests: Dict[str, str] = field(default_factory=dict)

    # Locations.
    reports_dir: str = "docs/strategy_pipeline"
    allowed_output_roots: Tuple[str, ...] = (
        "docs/strategy_pipeline",
        "docs/research_registry",
        "docs/strategy_truth",
        "docs/statistical_validation",
        "docs/strategy_certification",
        "docs/live_drift",
        "runtime/outcome_evidence",
        "runtime/strategy_pipeline",
    )

    def get_artifact(self, key: str) -> Optional[Any]:
        return self.artifacts.get(key)

    def set_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value
