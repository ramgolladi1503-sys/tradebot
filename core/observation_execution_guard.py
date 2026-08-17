"""Fail-closed execution boundary for observation-only sessions."""

from __future__ import annotations

import os


class ObservationOnlyExecutionBlocked(RuntimeError):
    """Raised whenever an observation-only process reaches an execution boundary."""

    reason = "OBSERVATION_ONLY_EXECUTION_BLOCKED"

    def __init__(self, boundary: str) -> None:
        self.boundary = str(boundary)
        super().__init__(f"{self.reason}:{self.boundary}")


def _truthy(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def observation_only_enabled() -> bool:
    return _truthy("OBSERVATION_ONLY_MODE")


def assert_execution_allowed(boundary: str) -> None:
    """Reject execution before any routeable or broker state can be mutated."""

    if not observation_only_enabled():
        return
    conflicting = tuple(
        name
        for name in (
            "ALLOW_LIVE_PLACEMENT",
            "LIVE_TRADING_ENABLED",
            "PAPER_TRADING_ENABLED",
            "AUTO_TRADE",
            "AUTO_ORDER",
        )
        if _truthy(name)
    )
    # Observation mode dominates all downstream flags; a conflicting authority
    # is still rejected, never silently normalized into an executable session.
    suffix = ":conflicting_authority=" + ",".join(conflicting) if conflicting else ""
    raise ObservationOnlyExecutionBlocked(f"{boundary}{suffix}")

