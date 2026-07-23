from __future__ import annotations

from pathlib import Path

from core.strategy_pipeline.pipeline_models import EngineType


class ArtifactLocator:
    """Resolves exact, run-scoped pipeline artifacts.

    It deliberately does not scan for "the latest" file and does not treat a
    generic Markdown report as a valid cache entry.
    """

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir).resolve()

    def result_manifest_path(
        self,
        engine: EngineType,
        strategy_id: str,
        run_id: str,
    ) -> Path:
        return (
            self.base_dir
            / "runtime"
            / "strategy_pipeline"
            / strategy_id
            / run_id
            / f"{engine.value.lower()}.result.json"
        )

    def locate_engine_result_manifest(
        self,
        engine: EngineType,
        strategy_id: str,
        run_id: str,
    ) -> Path | None:
        path = self.result_manifest_path(engine, strategy_id, run_id)
        return path if path.is_file() else None
