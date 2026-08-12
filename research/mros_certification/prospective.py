"""Immutable prospective observation ledger contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping


@dataclass(frozen=True)
class ProspectiveLedger:
    entries: tuple[Mapping[str, object], ...] = ()
    frozen_spec_sha: str = ""

    def append(self, prediction: Mapping[str, object]) -> "ProspectiveLedger":
        if prediction.get("spec_sha") != self.frozen_spec_sha:
            raise ValueError("PROSPECTIVE_SPEC_MISMATCH")
        if prediction.get("outcome") is not None:
            raise ValueError("OUTCOME_CONDITIONED_PREDICTION_FORBIDDEN")
        digest = _digest(prediction)
        if any(row.get("prediction_sha") == digest for row in self.entries):
            raise ValueError("PROSPECTIVE_DUPLICATE_PREDICTION")
        row = dict(prediction)
        row["prediction_sha"] = digest
        row["immutable"] = True
        return ProspectiveLedger((*self.entries, row), self.frozen_spec_sha)

    def attach_outcome(self, prediction_sha: str, outcome: Mapping[str, object]) -> "ProspectiveLedger":
        if prediction_sha not in {row.get("prediction_sha") for row in self.entries}:
            raise ValueError("PROSPECTIVE_PREDICTION_NOT_FOUND")
        updated = tuple({**row, "outcome": dict(outcome)} if row.get("prediction_sha") == prediction_sha else row for row in self.entries)
        return ProspectiveLedger(updated, self.frozen_spec_sha)


def _digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
