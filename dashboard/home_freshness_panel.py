from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from core.runtime_snapshot_store import ADVISORY_LATEST_PATH, TOP_OPPORTUNITIES_LATEST_PATH
from dashboard.ui.freshness_panel import (
    collect_latest_artifact_freshness_rows,
    render_latest_artifact_freshness_panel,
)


HOME_FRESHNESS_ARTIFACTS: dict[str, Path] = {
    "advisory_latest": ADVISORY_LATEST_PATH,
    "top_opportunities_latest": TOP_OPPORTUNITIES_LATEST_PATH,
}


def build_home_freshness_artifacts(
    artifacts: Mapping[str, str | Path] | None = None,
) -> dict[str, Path]:
    source = artifacts if artifacts is not None else HOME_FRESHNESS_ARTIFACTS
    return {str(name): Path(path).expanduser() for name, path in source.items()}


def render_home_freshness_panel(
    st_module: Any,
    *,
    artifacts: Mapping[str, str | Path] | None = None,
    reader: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, int]:
    resolved_artifacts = build_home_freshness_artifacts(artifacts)
    kwargs: dict[str, Any] = {}
    if reader is not None:
        kwargs["reader"] = reader
    rows = collect_latest_artifact_freshness_rows(resolved_artifacts, **kwargs)
    return render_latest_artifact_freshness_panel(
        st_module,
        rows,
        title="Home Latest Artifact Freshness",
    )


__all__ = [
    "HOME_FRESHNESS_ARTIFACTS",
    "build_home_freshness_artifacts",
    "render_home_freshness_panel",
]
