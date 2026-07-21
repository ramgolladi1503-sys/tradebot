from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .contracts import (
    CandidateStrategySpec,
    DiscoveryObservation,
    SafetyEnvelope,
    semantic_hash,
)


@dataclass(frozen=True)
class AuditReport:
    verdict: str
    failures: tuple[str, ...]
    observations: int = 0
    sessions: int = 0
    feature_names: tuple[str, ...] = ()
    evidence_hash: str = ""
    safety: SafetyEnvelope = field(default_factory=SafetyEnvelope)

    def validate(self) -> None:
        self.safety.validate()
        if self.verdict not in {"PASS", "FAIL"}:
            raise ValueError("audit verdict must be PASS or FAIL")
        if self.verdict == "PASS" and self.failures:
            raise ValueError("PASS audit cannot contain failures")
        if self.verdict == "FAIL" and not self.failures:
            raise ValueError("FAIL audit must contain failures")


def audit_observations(
    observations: Iterable[DiscoveryObservation],
) -> AuditReport:
    materialized = list(observations)
    failures: list[str] = []
    schemas: set[tuple[str, ...]] = set()
    ids: set[str] = set()
    sessions: set[str] = set()

    for index, observation in enumerate(materialized):
        try:
            observation.validate()
        except Exception as exc:
            failures.append(
                f"observation[{index}] {type(exc).__name__}: {exc}"
            )
            continue
        if observation.observation_id in ids:
            failures.append(
                f"duplicate observation_id: {observation.observation_id}"
            )
        ids.add(observation.observation_id)
        sessions.add(observation.session_id)
        schemas.add(tuple(sorted(observation.features)))
    if not materialized:
        failures.append("no observations supplied")
    if len(schemas) > 1:
        failures.append(
            f"inconsistent feature schemas: {sorted(schemas)!r}"
        )

    report = AuditReport(
        verdict="FAIL" if failures else "PASS",
        failures=tuple(failures),
        observations=len(materialized),
        sessions=len(sessions),
        feature_names=next(iter(schemas), ()),
        evidence_hash=(
            semantic_hash(materialized)
            if materialized and not failures
            else ""
        ),
    )
    report.validate()
    return report


def audit_candidate(
    candidate: CandidateStrategySpec,
    *,
    development_sessions: Sequence[str],
    validation_sessions: Sequence[str],
    holdout_sessions: Sequence[str],
    holdout_consumed_during_discovery: bool = False,
) -> AuditReport:
    failures: list[str] = []
    try:
        candidate.validate()
    except Exception as exc:
        failures.append(f"candidate {type(exc).__name__}: {exc}")

    partitions = [
        tuple(development_sessions),
        tuple(validation_sessions),
        tuple(holdout_sessions),
    ]
    names = ("development", "validation", "holdout")
    for name, partition in zip(names, partitions):
        if not partition:
            failures.append(f"{name} partition is empty")
        if tuple(sorted(partition)) != partition:
            failures.append(f"{name} partition is not chronological")
    sets = [set(partition) for partition in partitions]
    if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
        failures.append("dataset partitions overlap")
    combined = partitions[0] + partitions[1] + partitions[2]
    if combined and tuple(sorted(combined)) != combined:
        failures.append(
            "dataset partitions are not globally chronological"
        )
    if holdout_consumed_during_discovery:
        failures.append("locked holdout was consumed during discovery")

    report = AuditReport(
        verdict="FAIL" if failures else "PASS",
        failures=tuple(failures),
        evidence_hash=(
            semantic_hash(
                {"candidate": candidate, "partitions": partitions}
            )
            if not failures
            else ""
        ),
    )
    report.validate()
    return report
