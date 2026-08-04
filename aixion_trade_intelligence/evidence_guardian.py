from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence


def _aware(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _finite_nonnegative(value: object, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_not_numeric") from exc
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name}_invalid")
    return result


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile_values_empty")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("quantile_probability_out_of_range")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


@dataclass(frozen=True)
class SourceContinuityCheckpoint:
    source_name: str
    observed_events: int
    first_sequence: int | None
    last_sequence: int | None
    sequence_gap_events: int
    duplicate_events: int
    malformed_events: int
    latest_source_time: datetime | None
    latest_receive_time: datetime | None
    latest_persist_time: datetime | None
    observed_event_types: tuple[str, ...]
    required_event_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_name.strip():
            raise ValueError("continuity_source_name_missing")
        for name in ("observed_events", "sequence_gap_events", "duplicate_events", "malformed_events"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name}_negative")
            object.__setattr__(self, name, value)
        if (self.first_sequence is None) != (self.last_sequence is None):
            raise ValueError("continuity_sequence_bounds_must_be_paired")
        if self.first_sequence is not None and self.last_sequence is not None:
            if self.first_sequence < 0 or self.last_sequence < self.first_sequence:
                raise ValueError("continuity_sequence_bounds_invalid")
        for name in ("latest_source_time", "latest_receive_time", "latest_persist_time"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _aware(value, name=name))
        if self.latest_source_time and self.latest_receive_time and self.latest_receive_time < self.latest_source_time:
            raise ValueError("receive_time_before_source_time")
        if self.latest_receive_time and self.latest_persist_time and self.latest_persist_time < self.latest_receive_time:
            raise ValueError("persist_time_before_receive_time")
        observed = tuple(sorted({value.strip().upper() for value in self.observed_event_types if value.strip()}))
        required = tuple(sorted({value.strip().upper() for value in self.required_event_types if value.strip()}))
        object.__setattr__(self, "observed_event_types", observed)
        object.__setattr__(self, "required_event_types", required)

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "SourceContinuityCheckpoint":
        def parse_time(name: str) -> datetime | None:
            value = row.get(name)
            if value in (None, ""):
                return None
            if isinstance(value, datetime):
                return _aware(value, name=name)
            text = str(value).strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError as exc:
                raise ValueError(f"{name}_invalid") from exc
            return _aware(parsed, name=name)

        return cls(
            source_name=str(row.get("source_name") or ""),
            observed_events=int(row.get("observed_events") or 0),
            first_sequence=int(row["first_sequence"]) if row.get("first_sequence") is not None else None,
            last_sequence=int(row["last_sequence"]) if row.get("last_sequence") is not None else None,
            sequence_gap_events=int(row.get("sequence_gap_events") or 0),
            duplicate_events=int(row.get("duplicate_events") or 0),
            malformed_events=int(row.get("malformed_events") or 0),
            latest_source_time=parse_time("latest_source_time"),
            latest_receive_time=parse_time("latest_receive_time"),
            latest_persist_time=parse_time("latest_persist_time"),
            observed_event_types=tuple(str(value) for value in (row.get("observed_event_types") or ())),
            required_event_types=tuple(str(value) for value in (row.get("required_event_types") or ())),
        )


@dataclass(frozen=True)
class SourceContinuityReport:
    source_name: str
    observed_events: int
    inferred_sequence_span: int | None
    coverage_ratio: float | None
    sequence_loss_rate: float
    duplicate_rate: float
    malformed_rate: float
    source_age_seconds: float | None
    source_to_receive_ms: float | None
    receive_to_persist_ms: float | None
    missing_required_event_types: tuple[str, ...]
    integrity_valid: bool

    def to_record(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "observed_events": self.observed_events,
            "inferred_sequence_span": self.inferred_sequence_span,
            "coverage_ratio": self.coverage_ratio,
            "sequence_loss_rate": self.sequence_loss_rate,
            "duplicate_rate": self.duplicate_rate,
            "malformed_rate": self.malformed_rate,
            "source_age_seconds": self.source_age_seconds,
            "source_to_receive_ms": self.source_to_receive_ms,
            "receive_to_persist_ms": self.receive_to_persist_ms,
            "missing_required_event_types": list(self.missing_required_event_types),
            "integrity_valid": self.integrity_valid,
        }


def build_source_continuity_report(
    checkpoint: SourceContinuityCheckpoint,
    *,
    evaluation_time: datetime,
) -> SourceContinuityReport:
    now = _aware(evaluation_time, name="evaluation_time")
    span: int | None = None
    coverage: float | None = None
    if checkpoint.first_sequence is not None and checkpoint.last_sequence is not None:
        span = checkpoint.last_sequence - checkpoint.first_sequence + 1
        if span <= 0:
            raise ValueError("continuity_sequence_span_nonpositive")
        coverage = min(1.0, checkpoint.observed_events / span)
    denominator = checkpoint.observed_events + checkpoint.sequence_gap_events
    sequence_loss_rate = checkpoint.sequence_gap_events / denominator if denominator else 0.0
    duplicate_rate = checkpoint.duplicate_events / checkpoint.observed_events if checkpoint.observed_events else 0.0
    malformed_rate = checkpoint.malformed_events / checkpoint.observed_events if checkpoint.observed_events else 0.0
    source_age = None
    if checkpoint.latest_source_time is not None:
        source_age = (now - checkpoint.latest_source_time).total_seconds()
        if source_age < 0:
            raise ValueError("continuity_source_time_in_future")
    source_to_receive = None
    if checkpoint.latest_source_time is not None and checkpoint.latest_receive_time is not None:
        source_to_receive = (checkpoint.latest_receive_time - checkpoint.latest_source_time).total_seconds() * 1000.0
    receive_to_persist = None
    if checkpoint.latest_receive_time is not None and checkpoint.latest_persist_time is not None:
        receive_to_persist = (checkpoint.latest_persist_time - checkpoint.latest_receive_time).total_seconds() * 1000.0
    missing = tuple(sorted(set(checkpoint.required_event_types) - set(checkpoint.observed_event_types)))
    integrity_valid = (
        checkpoint.sequence_gap_events == 0
        and checkpoint.malformed_events == 0
        and not missing
        and checkpoint.observed_events > 0
    )
    return SourceContinuityReport(
        source_name=checkpoint.source_name,
        observed_events=checkpoint.observed_events,
        inferred_sequence_span=span,
        coverage_ratio=coverage,
        sequence_loss_rate=sequence_loss_rate,
        duplicate_rate=duplicate_rate,
        malformed_rate=malformed_rate,
        source_age_seconds=source_age,
        source_to_receive_ms=source_to_receive,
        receive_to_persist_ms=receive_to_persist,
        missing_required_event_types=missing,
        integrity_valid=integrity_valid,
    )


@dataclass(frozen=True)
class EmpiricalContinuityFinding:
    source_name: str
    metric: str
    value: float
    reference_count: int
    upper_bound: float | None
    verdict: str

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def evaluate_continuity_against_baseline(
    report: SourceContinuityReport,
    *,
    reference_metrics: Mapping[str, Sequence[float]],
    policy: Mapping[str, object],
) -> tuple[EmpiricalContinuityFinding, ...]:
    minimum_reference_sessions = int(policy.get("minimum_reference_sessions") or 0)
    metric_rules = policy.get("metrics")
    if minimum_reference_sessions <= 0:
        raise ValueError("continuity_minimum_reference_sessions_must_be_positive")
    if not isinstance(metric_rules, Mapping) or not metric_rules:
        raise ValueError("continuity_metric_rules_missing")
    record = report.to_record()
    findings: list[EmpiricalContinuityFinding] = []
    for metric, raw_rule in sorted(metric_rules.items()):
        if not isinstance(raw_rule, Mapping):
            raise ValueError(f"continuity_rule_invalid={metric}")
        value = record.get(metric)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"continuity_metric_not_numeric={metric}")
        references = [_finite_nonnegative(item, name=f"continuity_reference_{metric}") for item in reference_metrics.get(metric, ())]
        if len(references) < minimum_reference_sessions:
            findings.append(
                EmpiricalContinuityFinding(
                    report.source_name,
                    metric,
                    float(value),
                    len(references),
                    None,
                    "INSUFFICIENT_REFERENCE_EVIDENCE",
                )
            )
            continue
        upper_probability = raw_rule.get("upper_quantile")
        if upper_probability is None:
            raise ValueError(f"continuity_rule_missing_upper_quantile={metric}")
        probability = _finite_nonnegative(upper_probability, name=f"continuity_upper_quantile_{metric}")
        if probability > 1.0:
            raise ValueError(f"continuity_upper_quantile_out_of_range={metric}")
        upper_bound = _quantile(references, probability)
        verdict = "OUTSIDE_EMPIRICAL_BASELINE" if float(value) > upper_bound else "WITHIN_EMPIRICAL_BASELINE"
        findings.append(
            EmpiricalContinuityFinding(
                report.source_name,
                metric,
                float(value),
                len(references),
                upper_bound,
                verdict,
            )
        )
    return tuple(findings)


@dataclass(frozen=True)
class EvidenceGuardianSummary:
    source_count: int
    valid_source_count: int
    invalid_source_count: int
    stale_source_count: int
    missing_event_type_count: int
    total_sequence_gap_events: int
    total_duplicate_events: int
    total_malformed_events: int
    observation_authority: str
    blockers: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "source_count": self.source_count,
            "valid_source_count": self.valid_source_count,
            "invalid_source_count": self.invalid_source_count,
            "stale_source_count": self.stale_source_count,
            "missing_event_type_count": self.missing_event_type_count,
            "total_sequence_gap_events": self.total_sequence_gap_events,
            "total_duplicate_events": self.total_duplicate_events,
            "total_malformed_events": self.total_malformed_events,
            "observation_authority": self.observation_authority,
            "blockers": list(self.blockers),
        }


def summarize_evidence_guardian(
    checkpoints: Iterable[SourceContinuityCheckpoint],
    *,
    evaluation_time: datetime,
    freshness_limits_seconds: Mapping[str, float],
) -> EvidenceGuardianSummary:
    rows = list(checkpoints)
    if not rows:
        raise ValueError("evidence_guardian_checkpoints_empty")
    names = [row.source_name for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("evidence_guardian_duplicate_source")
    reports = [build_source_continuity_report(row, evaluation_time=evaluation_time) for row in rows]
    stale_sources: list[str] = []
    missing_freshness: list[str] = []
    for report in reports:
        if report.source_name not in freshness_limits_seconds:
            missing_freshness.append(report.source_name)
            continue
        limit = _finite_nonnegative(freshness_limits_seconds[report.source_name], name=f"freshness_limit_{report.source_name}")
        if report.source_age_seconds is None or report.source_age_seconds > limit:
            stale_sources.append(report.source_name)
    blockers: list[str] = []
    invalid = [report.source_name for report in reports if not report.integrity_valid]
    if invalid:
        blockers.append("SOURCE_INTEGRITY_INVALID:" + ",".join(sorted(invalid)))
    if stale_sources:
        blockers.append("SOURCE_STALE:" + ",".join(sorted(stale_sources)))
    if missing_freshness:
        blockers.append("SOURCE_FRESHNESS_POLICY_MISSING:" + ",".join(sorted(missing_freshness)))
    authority = "READ_ONLY_OBSERVATION_ALLOWED" if not blockers else "READ_ONLY_OBSERVATION_BLOCKED"
    return EvidenceGuardianSummary(
        source_count=len(reports),
        valid_source_count=sum(report.integrity_valid for report in reports),
        invalid_source_count=sum(not report.integrity_valid for report in reports),
        stale_source_count=len(stale_sources),
        missing_event_type_count=sum(len(report.missing_required_event_types) for report in reports),
        total_sequence_gap_events=sum(row.sequence_gap_events for row in rows),
        total_duplicate_events=sum(row.duplicate_events for row in rows),
        total_malformed_events=sum(row.malformed_events for row in rows),
        observation_authority=authority,
        blockers=tuple(blockers),
    )
