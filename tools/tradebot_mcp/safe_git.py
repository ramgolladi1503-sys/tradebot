from __future__ import annotations

from tools.tradebot_mcp.core import GitAuditService, SafetyError


class SafeGitAuditService(GitAuditService):
    """Git audit service with explicit option-injection rejection for refs."""

    @staticmethod
    def _validate_ref(value: str) -> str:
        if value.startswith("-"):
            raise SafetyError(f"invalid git ref: {value}")
        return GitAuditService._validate_ref(value)
