from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Mapping, Sequence


def _finite(value: object, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_not_numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name}_not_finite")
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
class CandidateScoreObservation:
    candidate_id: str
    cycle_id: str
    score: float
    rankable: bool
    executable: bool
    direction: str
    fallback_used: bool = False
    recovered_fallback: bool = False
    stale_quote: bool = False
    outcome_value: float | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.cycle_id.strip():
            raise ValueError("score_observation_identity_missing")
        object.__setattr__(self, "score", _finite(self.score, name="score"))
        direction = self.direction.strip().upper() or "UNKNOWN"
        object.__setattr__(self, "direction", direction)
        if self.outcome_value is not None:
            object.__setattr__(self, "outcome_value", _finite(self.outcome_value, name="outcome_value"))
        if self.executable and (self.fallback_used or self.recovered_fallback or self.stale_quote):
            raise ValueError("degraded_score_observation_must_not_be_executable")

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "CandidateScoreObservation":
        candidate_id = str(row.get("candidate_id") or row.get("trade_id") or "").strip()
        cycle_id = str(row.get("cycle_id") or "").strip()
        score_value = row.get("final_score") if row.get("final_score") is not None else row.get("score")
        if score_value is None:
            raise ValueError("score_observation_score_missing")
        outcome = row.get("outcome_value")
        return cls(
            candidate_id=candidate_id,
            cycle_id=cycle_id,
            score=_finite(score_value, name="score"),
            rankable=bool(row.get("rankable")),
            executable=bool(row.get("executable")),
            direction=str(row.get("direction") or row.get("option_type") or row.get("side") or "UNKNOWN"),
            fallback_used=bool(row.get("fallback_used")),
            recovered_fallback=bool(row.get("recovered_fallback")),
            stale_quote=bool(row.get("stale_quote")),
            outcome_value=_finite(outcome, name="outcome_value") if outcome is not None else None,
        )


@dataclass(frozen=True)
class ScoreSeparationReport:
    cycle_id: str
    candidate_count: int
    rankable_count: int
    executable_count: int
    unique_score_count: int
    score_min: float
    score_p10: float
    score_p25: float
    score_median: float
    score_p75: float
    score_p90: float
    score_max: float
    score_mean: float
    score_stddev: float
    score_range: float
    score_iqr: float
    top1_score: float
    top2_score: float | None
    top1_minus_top2: float | None
    top1_minus_median: float
    tie_rate: float
    executable_rate: float
    fallback_contamination_rate: float
    stale_quote_rate: float
    direction_counts: dict[str, int]
    winner_share: float
    score_concentration_hhi: float
    outcome_pairwise_concordance: float | None
    outcome_pairs_evaluated: int

    def to_record(self) -> dict[str, object]:
        return {
            "cycle_id": self.cycle_id,
            "candidate_count": self.candidate_count,
            "rankable_count": self.rankable_count,
            "executable_count": self.executable_count,
            "unique_score_count": self.unique_score_count,
            "score_min": self.score_min,
            "score_p10": self.score_p10,
            "score_p25": self.score_p25,
            "score_median": self.score_median,
            "score_p75": self.score_p75,
            "score_p90": self.score_p90,
            "score_max": self.score_max,
            "score_mean": self.score_mean,
            "score_stddev": self.score_stddev,
            "score_range": self.score_range,
            "score_iqr": self.score_iqr,
            "top1_score": self.top1_score,
            "top2_score": self.top2_score,
            "top1_minus_top2": self.top1_minus_top2,
            "top1_minus_median": self.top1_minus_median,
            "tie_rate": self.tie_rate,
            "executable_rate": self.executable_rate,
            "fallback_contamination_rate": self.fallback_contamination_rate,
            "stale_quote_rate": self.stale_quote_rate,
            "direction_counts": dict(self.direction_counts),
            "winner_share": self.winner_share,
            "score_concentration_hhi": self.score_concentration_hhi,
            "outcome_pairwise_concordance": self.outcome_pairwise_concordance,
            "outcome_pairs_evaluated": self.outcome_pairs_evaluated,
        }


def _outcome_concordance(rows: Sequence[CandidateScoreObservation]) -> tuple[float | None, int]:
    eligible = [row for row in rows if row.outcome_value is not None]
    concordant = 0
    discordant = 0
    for left, right in combinations(eligible, 2):
        score_delta = left.score - right.score
        outcome_delta = float(left.outcome_value) - float(right.outcome_value)
        if score_delta == 0.0 or outcome_delta == 0.0:
            continue
        if score_delta * outcome_delta > 0.0:
            concordant += 1
        else:
            discordant += 1
    evaluated = concordant + discordant
    if evaluated == 0:
        return None, 0
    return concordant / evaluated, evaluated


def analyze_score_separation(observations: Iterable[CandidateScoreObservation]) -> ScoreSeparationReport:
    rows = list(observations)
    if not rows:
        raise ValueError("score_observations_empty")
    cycle_ids = {row.cycle_id for row in rows}
    if len(cycle_ids) != 1:
        raise ValueError("score_report_requires_one_cycle")
    identities = [row.candidate_id for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate_candidate_in_score_cycle")
    rankable = [row for row in rows if row.rankable]
    if not rankable:
        raise ValueError("score_report_has_no_rankable_candidates")
    scores = [row.score for row in rankable]
    ordered = sorted(scores, reverse=True)
    mean = sum(scores) / len(scores)
    variance = sum((value - mean) ** 2 for value in scores) / len(scores)
    unique_count = len(set(scores))
    tie_rate = 1.0 - unique_count / len(scores)
    degraded = sum(row.fallback_used or row.recovered_fallback for row in rankable)
    stale = sum(row.stale_quote for row in rankable)
    executable = sum(row.executable for row in rankable)
    minimum = min(scores)
    shifted = [value - minimum for value in scores]
    total_shifted = sum(shifted)
    if total_shifted > 0.0:
        weights = [value / total_shifted for value in shifted]
    else:
        weights = [1.0 / len(scores)] * len(scores)
    winner_share = max(weights)
    hhi = sum(weight * weight for weight in weights)
    concordance, evaluated_pairs = _outcome_concordance(rankable)
    median = _quantile(scores, 0.5)
    return ScoreSeparationReport(
        cycle_id=next(iter(cycle_ids)),
        candidate_count=len(rows),
        rankable_count=len(rankable),
        executable_count=executable,
        unique_score_count=unique_count,
        score_min=minimum,
        score_p10=_quantile(scores, 0.10),
        score_p25=_quantile(scores, 0.25),
        score_median=median,
        score_p75=_quantile(scores, 0.75),
        score_p90=_quantile(scores, 0.90),
        score_max=max(scores),
        score_mean=mean,
        score_stddev=math.sqrt(variance),
        score_range=max(scores) - minimum,
        score_iqr=_quantile(scores, 0.75) - _quantile(scores, 0.25),
        top1_score=ordered[0],
        top2_score=ordered[1] if len(ordered) > 1 else None,
        top1_minus_top2=ordered[0] - ordered[1] if len(ordered) > 1 else None,
        top1_minus_median=ordered[0] - median,
        tie_rate=tie_rate,
        executable_rate=executable / len(rankable),
        fallback_contamination_rate=degraded / len(rankable),
        stale_quote_rate=stale / len(rankable),
        direction_counts=dict(sorted(Counter(row.direction for row in rankable).items())),
        winner_share=winner_share,
        score_concentration_hhi=hhi,
        outcome_pairwise_concordance=concordance,
        outcome_pairs_evaluated=evaluated_pairs,
    )


@dataclass(frozen=True)
class RankingStabilityReport:
    previous_cycle_id: str
    current_cycle_id: str
    previous_count: int
    current_count: int
    common_candidates: int
    candidate_retention_rate: float
    top_k: int
    top_k_overlap_rate: float
    kendall_tau_b: float | None
    rank_pairs_evaluated: int

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def compare_cycle_rankings(
    previous: Sequence[CandidateScoreObservation],
    current: Sequence[CandidateScoreObservation],
    *,
    top_k: int,
) -> RankingStabilityReport:
    if top_k <= 0:
        raise ValueError("top_k_must_be_positive")
    if not previous or not current:
        raise ValueError("ranking_stability_inputs_empty")
    previous_cycles = {row.cycle_id for row in previous}
    current_cycles = {row.cycle_id for row in current}
    if len(previous_cycles) != 1 or len(current_cycles) != 1:
        raise ValueError("ranking_stability_requires_one_cycle_per_side")
    previous_rows = [row for row in previous if row.rankable]
    current_rows = [row for row in current if row.rankable]
    previous_map = {row.candidate_id: row.score for row in previous_rows}
    current_map = {row.candidate_id: row.score for row in current_rows}
    if len(previous_map) != len(previous_rows) or len(current_map) != len(current_rows):
        raise ValueError("ranking_stability_duplicate_candidate")
    common = sorted(set(previous_map) & set(current_map))
    union = set(previous_map) | set(current_map)
    previous_top = {
        candidate_id
        for candidate_id, _ in sorted(previous_map.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    }
    current_top = {
        candidate_id
        for candidate_id, _ in sorted(current_map.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    }
    top_denominator = max(1, min(top_k, len(previous_top), len(current_top)))
    concordant = 0
    discordant = 0
    ties_previous = 0
    ties_current = 0
    for left, right in combinations(common, 2):
        previous_delta = previous_map[left] - previous_map[right]
        current_delta = current_map[left] - current_map[right]
        if previous_delta == 0.0 and current_delta == 0.0:
            continue
        if previous_delta == 0.0:
            ties_previous += 1
        elif current_delta == 0.0:
            ties_current += 1
        elif previous_delta * current_delta > 0.0:
            concordant += 1
        else:
            discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + ties_previous)
        * (concordant + discordant + ties_current)
    )
    tau = None if denominator == 0.0 else (concordant - discordant) / denominator
    return RankingStabilityReport(
        previous_cycle_id=next(iter(previous_cycles)),
        current_cycle_id=next(iter(current_cycles)),
        previous_count=len(previous_rows),
        current_count=len(current_rows),
        common_candidates=len(common),
        candidate_retention_rate=len(common) / len(union) if union else 0.0,
        top_k=top_k,
        top_k_overlap_rate=len(previous_top & current_top) / top_denominator,
        kendall_tau_b=tau,
        rank_pairs_evaluated=concordant + discordant + ties_previous + ties_current,
    )


@dataclass(frozen=True)
class EmpiricalMetricFinding:
    metric: str
    value: float
    reference_count: int
    lower_bound: float | None
    upper_bound: float | None
    verdict: str

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


def evaluate_empirical_score_policy(
    report: ScoreSeparationReport,
    *,
    reference_metrics: Mapping[str, Sequence[float]],
    policy: Mapping[str, object],
) -> tuple[EmpiricalMetricFinding, ...]:
    minimum_reference_sessions = int(policy.get("minimum_reference_sessions") or 0)
    metric_rules = policy.get("metrics")
    if minimum_reference_sessions <= 0:
        raise ValueError("minimum_reference_sessions_must_be_positive")
    if not isinstance(metric_rules, Mapping) or not metric_rules:
        raise ValueError("empirical_score_metric_rules_missing")
    report_record = report.to_record()
    findings: list[EmpiricalMetricFinding] = []
    for metric, raw_rule in sorted(metric_rules.items()):
        if not isinstance(raw_rule, Mapping):
            raise ValueError(f"empirical_score_rule_invalid={metric}")
        if metric not in report_record:
            raise ValueError(f"empirical_score_metric_unknown={metric}")
        current_value = report_record[metric]
        if not isinstance(current_value, (int, float)) or isinstance(current_value, bool):
            raise ValueError(f"empirical_score_metric_not_numeric={metric}")
        references = [_finite(value, name=f"reference_{metric}") for value in reference_metrics.get(metric, ())]
        if len(references) < minimum_reference_sessions:
            findings.append(
                EmpiricalMetricFinding(
                    metric=metric,
                    value=float(current_value),
                    reference_count=len(references),
                    lower_bound=None,
                    upper_bound=None,
                    verdict="INSUFFICIENT_REFERENCE_EVIDENCE",
                )
            )
            continue
        lower_probability = raw_rule.get("lower_quantile")
        upper_probability = raw_rule.get("upper_quantile")
        if lower_probability is None and upper_probability is None:
            raise ValueError(f"empirical_score_rule_has_no_bounds={metric}")
        lower_bound = _quantile(references, _finite(lower_probability, name=f"lower_quantile_{metric}")) if lower_probability is not None else None
        upper_bound = _quantile(references, _finite(upper_probability, name=f"upper_quantile_{metric}")) if upper_probability is not None else None
        below = lower_bound is not None and float(current_value) < lower_bound
        above = upper_bound is not None and float(current_value) > upper_bound
        verdict = "OUTSIDE_EMPIRICAL_BASELINE" if below or above else "WITHIN_EMPIRICAL_BASELINE"
        findings.append(
            EmpiricalMetricFinding(metric, float(current_value), len(references), lower_bound, upper_bound, verdict)
        )
    return tuple(findings)
