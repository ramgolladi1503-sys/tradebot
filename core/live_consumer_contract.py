"""Explicit read-only consumer topology for one canonical observation session."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping


CANONICAL_CONSUMERS = (
    "regime", "strategies", "cas_v2", "candidate_pool", "option_surface",
    "eligibility", "ranking", "advisory_queue", "ui", "monitoring", "evidence",
)


@dataclass(frozen=True)
class ReadOnlyConsumer:
    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    read_only: bool = True
    execution_capable: bool = False

    def validate(self) -> None:
        if self.name not in CANONICAL_CONSUMERS:
            raise ValueError(f"unknown_live_consumer:{self.name}")
        if not self.inputs or not self.outputs:
            raise ValueError(f"consumer_artifact_contract_missing:{self.name}")
        if self.read_only is not True or self.execution_capable is not False:
            raise ValueError(f"consumer_authority_not_read_only:{self.name}")


def canonical_consumer_registry() -> tuple[ReadOnlyConsumer, ...]:
    """Return the frozen topology; all outputs are artifacts or advisory data."""
    return (
        ReadOnlyConsumer("regime", ("canonical_live_sqlite",), ("regime_artifact",)),
        ReadOnlyConsumer("strategies", ("canonical_live_sqlite", "regime_artifact"), ("candidate_pool",)),
        ReadOnlyConsumer("cas_v2", ("canonical_live_sqlite", "regime_artifact"), ("cas_v2_artifact",)),
        ReadOnlyConsumer("candidate_pool", ("candidate_pool", "cas_v2_artifact"), ("candidate_artifact",)),
        ReadOnlyConsumer("option_surface", ("canonical_live_sqlite", "candidate_artifact"), ("option_surface_artifact",)),
        ReadOnlyConsumer("eligibility", ("candidate_artifact", "option_surface_artifact"), ("eligibility_artifact",)),
        ReadOnlyConsumer("ranking", ("eligibility_artifact",), ("ranking_artifact",)),
        ReadOnlyConsumer("advisory_queue", ("ranking_artifact",), ("advisory_queue",)),
        ReadOnlyConsumer("ui", ("advisory_queue", "monitoring_artifact"), ("ui_read_model",)),
        ReadOnlyConsumer("monitoring", ("canonical_live_sqlite", "consumer_artifacts"), ("monitoring_artifact",)),
        ReadOnlyConsumer("evidence", ("canonical_live_sqlite", "consumer_artifacts"), ("immutable_evidence",)),
    )


def validate_consumer_registry(names: Iterable[str] | None = None) -> tuple[str, ...]:
    registry = canonical_consumer_registry()
    for consumer in registry:
        consumer.validate()
    expected = tuple(CANONICAL_CONSUMERS)
    actual = tuple(names) if names is not None else expected
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise ValueError("live_consumer_registry_incomplete_or_duplicate")
    return expected


def consumer_authority_snapshot() -> Mapping[str, object]:
    validate_consumer_registry()
    return {
        "consumer_registry": list(CANONICAL_CONSUMERS),
        "read_only": True,
        "execution_capable": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
    }


def write_consumer_registry(path: str | Path, *, session_id: str, source_sha: str) -> None:
    """Emit the startup registry; health is proved separately by lifecycle evidence."""
    if not session_id or not source_sha:
        raise ValueError("consumer_registry_identity_missing")
    validate_consumer_registry()
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "source_sha": source_sha,
        "consumers": [
            {
                "id": name,
                "sha": source_sha,
                "mode": "canonical-read-only",
                "execution_capable": False,
                "health": "PENDING",
            }
            for name in CANONICAL_CONSUMERS
        ],
        **consumer_authority_snapshot(),
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
