"""Fail-closed certification for the supervised read-only MEG shadow system."""

from .meg_shadow_system import (
    CERTIFIED_VERDICT,
    FAILED_VERDICT,
    OFFLINE_PASS_VERDICT,
    PENDING_VERDICT,
    REQUIRED_OFFLINE_GATES,
    assemble_system_certificate,
    build_offline_report,
    validate_offline_report,
)

__all__ = [
    "CERTIFIED_VERDICT",
    "FAILED_VERDICT",
    "OFFLINE_PASS_VERDICT",
    "PENDING_VERDICT",
    "REQUIRED_OFFLINE_GATES",
    "assemble_system_certificate",
    "build_offline_report",
    "validate_offline_report",
]
