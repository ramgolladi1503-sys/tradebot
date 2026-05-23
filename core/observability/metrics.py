from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Mapping

DEFAULT_OBSERVABILITY_METRICS = (
    "tradebot_feed_age_ms",
    "tradebot_feed_stale_total",
    "tradebot_candidates_generated_total",
    "tradebot_candidates_ranked_total",
    "tradebot_candidates_blocked_total",
    "tradebot_fallback_candidates_total",
    "tradebot_fallback_executable_total",
    "tradebot_strategy_latency_ms",
    "tradebot_scoring_latency_ms",
    "tradebot_ranking_latency_ms",
    "tradebot_dashboard_write_latency_ms",
    "tradebot_paper_order_attempt_total",
    "tradebot_live_order_attempt_total",
)

_COUNTER_SUFFIX = "_total"
_DEFAULT_HELP = "Tradebot observability metric"


class ObservabilityMetricError(ValueError):
    """Raised when metric updates would produce invalid Prometheus output."""


@dataclass(frozen=True)
class MetricSample:
    name: str
    value: float
    labels: Mapping[str, str] = field(default_factory=dict)

    def line(self) -> str:
        label_text = _format_labels(self.labels)
        return f"{self.name}{label_text} {_format_value(self.value)}"


@dataclass
class ObservabilityMetricsRegistry:
    """Small stdlib Prometheus text registry for Tradebot observability.

    The registry is in-memory and read-only from Tradebot's trading perspective.
    It does not scrape runtime state, call brokers, alter candidates, or place
    orders. Future runtime wiring can update this registry from safe boundaries.
    """

    allowed_metrics: tuple[str, ...] = DEFAULT_OBSERVABILITY_METRICS
    _samples: dict[tuple[str, tuple[tuple[str, str], ...]], MetricSample] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for name in self.allowed_metrics:
            self._validate_name(name)
        self.set_gauge("tradebot_fallback_executable_total", 0)

    def set_gauge(self, name: str, value: int | float, labels: Mapping[str, object] | None = None) -> MetricSample:
        metric_value = _coerce_value(value)
        sample = MetricSample(name=name, value=metric_value, labels=_normalize_labels(labels))
        self._set(sample)
        return sample

    def increment_counter(self, name: str, amount: int | float = 1, labels: Mapping[str, object] | None = None) -> MetricSample:
        if not name.endswith(_COUNTER_SUFFIX):
            raise ObservabilityMetricError("counter_name_must_end_with_total")
        increment = _coerce_value(amount)
        if increment < 0:
            raise ObservabilityMetricError("counter_increment_must_be_non_negative")
        key = self._key(name, labels)
        current = self._samples.get(key)
        value = increment if current is None else current.value + increment
        sample = MetricSample(name=name, value=value, labels=_normalize_labels(labels))
        self._samples[key] = sample
        return sample

    def observe_latency_ms(self, name: str, value_ms: int | float, labels: Mapping[str, object] | None = None) -> MetricSample:
        if not name.endswith("_latency_ms") and not name.endswith("_age_ms"):
            raise ObservabilityMetricError("latency_metric_name_must_end_with_ms")
        return self.set_gauge(name, value_ms, labels=labels)

    def get_value(self, name: str, labels: Mapping[str, object] | None = None) -> float:
        sample = self._samples.get(self._key(name, labels))
        return 0.0 if sample is None else sample.value

    def samples(self) -> list[MetricSample]:
        return [self._samples[key] for key in sorted(self._samples)]

    def render_prometheus(self) -> str:
        lines: list[str] = []
        for name in self.allowed_metrics:
            lines.append(f"# HELP {name} {_DEFAULT_HELP}")
            lines.append(f"# TYPE {name} {_metric_type(name)}")
            for sample in self._samples_for(name):
                lines.append(sample.line())
        return "\n".join(lines) + "\n"

    def assert_safety(self) -> None:
        if self.get_value("tradebot_fallback_executable_total") != 0:
            raise ObservabilityMetricError("fallback_executable_metric_must_remain_zero")

    def _set(self, sample: MetricSample) -> None:
        self._validate_name(sample.name)
        self._samples[self._key(sample.name, sample.labels)] = sample

    def _key(self, name: str, labels: Mapping[str, object] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        self._validate_name(name)
        normalized = _normalize_labels(labels)
        return name, tuple(sorted(normalized.items()))

    def _samples_for(self, name: str) -> list[MetricSample]:
        return [sample for sample in self.samples() if sample.name == name]

    def _validate_name(self, name: str) -> None:
        if name not in self.allowed_metrics:
            raise ObservabilityMetricError(f"metric_not_allowed:{name}")


def build_default_metrics_registry() -> ObservabilityMetricsRegistry:
    return ObservabilityMetricsRegistry()


def _metric_type(name: str) -> str:
    return "counter" if name.endswith(_COUNTER_SUFFIX) else "gauge"


def _normalize_labels(labels: Mapping[str, object] | None) -> dict[str, str]:
    if not labels:
        return {}
    normalized: dict[str, str] = {}
    for key, value in labels.items():
        key_text = str(key).strip()
        if not key_text or not key_text.replace("_", "").isalnum():
            raise ObservabilityMetricError("invalid_label_name")
        normalized[key_text] = str(value)
    return normalized


def _format_labels(labels: Mapping[str, str]) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{_escape_label(value)}"' for key, value in sorted(labels.items()))
    return "{" + rendered + "}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _coerce_value(value: int | float) -> float:
    metric_value = float(value)
    if not isfinite(metric_value):
        raise ObservabilityMetricError("metric_value_must_be_finite")
    return metric_value


def _format_value(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return repr(value)


__all__ = [
    "DEFAULT_OBSERVABILITY_METRICS",
    "MetricSample",
    "ObservabilityMetricError",
    "ObservabilityMetricsRegistry",
    "build_default_metrics_registry",
]
