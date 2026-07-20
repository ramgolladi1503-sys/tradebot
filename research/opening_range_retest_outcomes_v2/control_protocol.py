from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class MutationSpec:
    control_id: str
    category: str
    mutation_kind: str
    mutation_payload: Mapping[str, object]
    target_function: str


@dataclass(frozen=True)
class RawExecution:
    observed_failures: tuple[str, ...]
    target_invoked: bool
    mutation_applied: bool
    fixture_hash_before: str
    fixture_hash_after: str
    target_output_hash: str


@dataclass(frozen=True)
class ControlExpectation:
    control_id: str
    expected_failures: tuple[str, ...]
