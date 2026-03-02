from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactVM:
    desk_id: str
    status: str
    path: Path | None = None
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthGateVM(ArtifactVM):
    pass


@dataclass(frozen=True)
class EventsVM:
    desk_id: str
    status: str
    path: Path | None = None
    message: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ExecutionVM(ArtifactVM):
    pass


@dataclass(frozen=True)
class ReconVM(ArtifactVM):
    pass


@dataclass(frozen=True)
class FeedVM(ArtifactVM):
    pass


@dataclass(frozen=True)
class DepthVM:
    desk_id: str
    status: str
    db_path: Path | None = None
    message: str | None = None
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskVM(ArtifactVM):
    pass


@dataclass(frozen=True)
class GeminiVM(ArtifactVM):
    provider: str | None = None
    model: str | None = None

