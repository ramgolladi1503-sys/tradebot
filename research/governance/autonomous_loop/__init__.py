"""Governed TradeBot autonomous-loop orchestration primitives.

This package is intentionally execution-isolated: it owns research/governance state only
and must not acquire broker, order, paper, or live authority.
"""

from .task_state_machine import TaskState, assert_transition
from .supervisor import AutonomousLoopSupervisor, RegistryError

__all__ = [
    "AutonomousLoopSupervisor",
    "RegistryError",
    "TaskState",
    "assert_transition",
]
