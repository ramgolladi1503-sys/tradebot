from __future__ import annotations

from pathlib import Path
from typing import Any

from research.opening_range_retest_outcomes_v2.oracle import audit_artifacts, verify_sidecar

__all__ = ["audit_outputs", "verify_sidecar"]


def audit_outputs(
    *,
    contract: dict[str, Any],
    ledger: dict[str, Any],
    summary: dict[str, Any],
    overlap: dict[str, Any],
    controls: dict[str, Any] | None,
    paths: dict[str, Path],
    artifact_dir: Path,
    source_project_root: Path,
) -> dict[str, Any]:
    return audit_artifacts(
        artifact_dir=artifact_dir,
        source_root=source_project_root,
        contract=contract,
        ledger=ledger,
        summary=summary,
        overlap=overlap,
        controls=controls,
        paths=paths,
    )
