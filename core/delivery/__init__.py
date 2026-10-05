"""Deterministic, offline delivery governance primitives.

This package records caller-supplied evidence. It does not authenticate actors,
query CI, or authorize repository merges, deployments, or trading actions.
"""

from .models import Defect, Evidence, WorkItem
from .orchestrator import DeliveryOrchestrator, GovernanceError

__all__ = ["Defect", "DeliveryOrchestrator", "Evidence", "GovernanceError", "WorkItem"]
