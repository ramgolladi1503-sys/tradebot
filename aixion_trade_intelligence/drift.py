from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence


def _finite_list(values: Sequence[float], *, name: str) -> list[float]:
    rows = [float(value) for value in values]
    if not rows or any(not math.isfinite(value) for value in rows):
        raise ValueError(f"{name}_invalid")
    return rows


def _histogram(values: Sequence[float], edges: Sequence[float]) -> list[int]:
    if len(edges) < 2 or list(edges) != sorted(edges) or len(set(edges)) != len(edges):
        raise ValueError("histogram_edges_invalid")
    counts = [0] * (len(edges) - 1)
    for value in values:
        placed = False
        for index, (lower, upper) in enumerate(zip(edges, edges[1:])):
            if lower <= value < upper or (index == len(counts) - 1 and value == upper):
                counts[index] += 1
                placed = True
                break
        if not placed:
            raise ValueError("value_outside_histogram_edges")
    return counts


def population_stability_index(reference: Sequence[float], current: Sequence[float], *, bin_edges: Sequence[float], smoothing: float) -> float:
    ref = _finite_list(reference, name="reference")
    cur = _finite_list(current, name="current")
    smooth = float(smoothing)
    if not math.isfinite(smooth) or smooth <= 0:
        raise ValueError("smoothing_must_be_positive")
    ref_counts = _histogram(ref, bin_edges)
    cur_counts = _histogram(cur, bin_edges)
    bins = len(ref_counts)
    ref_total = len(ref) + smooth * bins
    cur_total = len(cur) + smooth * bins
    psi = 0.0
    for ref_count, cur_count in zip(ref_counts, cur_counts):
        ref_pct = (ref_count + smooth) / ref_total
        cur_pct = (cur_count + smooth) / cur_total
        psi += (cur_pct - ref_pct) * math.log(cur_pct / ref_pct)
    return psi


def ks_statistic(reference: Sequence[float], current: Sequence[float]) -> float:
    ref = sorted(_finite_list(reference, name="reference"))
    cur = sorted(_finite_list(current, name="current"))
    points = sorted(set(ref + cur))
    ref_index = 0
    cur_index = 0
    maximum = 0.0
    for point in points:
        while ref_index < len(ref) and ref[ref_index] <= point:
            ref_index += 1
        while cur_index < len(cur) and cur[cur_index] <= point:
            cur_index += 1
        maximum = max(maximum, abs(ref_index / len(ref) - cur_index / len(cur)))
    return maximum


def jensen_shannon_divergence(reference: Sequence[float], current: Sequence[float], *, bin_edges: Sequence[float], smoothing: float) -> float:
    ref = _finite_list(reference, name="reference")
    cur = _finite_list(current, name="current")
    smooth = float(smoothing)
    if not math.isfinite(smooth) or smooth <= 0:
        raise ValueError("smoothing_must_be_positive")
    ref_counts = _histogram(ref, bin_edges)
    cur_counts = _histogram(cur, bin_edges)
    bins = len(ref_counts)
    p = [(count + smooth) / (len(ref) + smooth * bins) for count in ref_counts]
    q = [(count + smooth) / (len(cur) + smooth * bins) for count in cur_counts]
    m = [(left + right) / 2.0 for left, right in zip(p, q)]
    def kl(left: Sequence[float], right: Sequence[float]) -> float:
        return sum(a * math.log(a / b) for a, b in zip(left, right))
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


@dataclass(frozen=True)
class OODScore:
    feature_zscores: dict[str, float]
    squared_distance: float
    dimension_count: int
    def to_record(self) -> dict[str, object]:
        return {"feature_zscores": dict(self.feature_zscores), "squared_distance": self.squared_distance, "dimension_count": self.dimension_count}


def diagonal_zscore_ood(observation: Mapping[str, float], *, reference_means: Mapping[str, float], reference_stddevs: Mapping[str, float]) -> OODScore:
    keys = set(observation)
    if keys != set(reference_means) or keys != set(reference_stddevs) or not keys:
        raise ValueError("ood_feature_sets_must_match")
    zscores: dict[str, float] = {}
    for key in sorted(keys):
        value = float(observation[key])
        mean = float(reference_means[key])
        std = float(reference_stddevs[key])
        if not all(math.isfinite(item) for item in (value, mean, std)) or std <= 0:
            raise ValueError(f"ood_reference_invalid={key}")
        zscores[key] = (value - mean) / std
    return OODScore(zscores, sum(value * value for value in zscores.values()), len(zscores))


@dataclass(frozen=True)
class CUSUMPoint:
    index: int
    positive: float
    negative: float
    positive_alarm: bool
    negative_alarm: bool


def cusum_change_points(values: Sequence[float], *, reference_mean: float, allowance: float, threshold: float) -> list[CUSUMPoint]:
    rows = _finite_list(values, name="cusum_values")
    mean = float(reference_mean)
    drift = float(allowance)
    limit = float(threshold)
    if not all(math.isfinite(item) for item in (mean, drift, limit)):
        raise ValueError("cusum_parameters_not_finite")
    if drift < 0 or limit <= 0:
        raise ValueError("cusum_parameters_invalid")
    positive = 0.0
    negative = 0.0
    points: list[CUSUMPoint] = []
    for index, value in enumerate(rows):
        positive = max(0.0, positive + value - mean - drift)
        negative = min(0.0, negative + value - mean + drift)
        positive_alarm = positive > limit
        negative_alarm = abs(negative) > limit
        points.append(CUSUMPoint(index, positive, negative, positive_alarm, negative_alarm))
        if positive_alarm: positive = 0.0
        if negative_alarm: negative = 0.0
    return points
