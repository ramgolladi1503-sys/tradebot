from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .ranking_diagnostics import CandidateScoreObservation, analyze_score_separation


def _canonical_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BaselineSource:
    path: str
    sha256: str
    row_count: int
    cycle_count: int

    def to_record(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class RankingBaseline:
    schema_version: str
    metric_names: tuple[str, ...]
    ranking_metrics: dict[str, tuple[float, ...]]
    cycle_reports: tuple[dict[str, object], ...]
    sources: tuple[BaselineSource, ...]
    baseline_id: str

    def to_record(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_names": list(self.metric_names),
            "ranking_metrics": {key: list(values) for key, values in self.ranking_metrics.items()},
            "cycle_reports": [dict(row) for row in self.cycle_reports],
            "sources": [source.to_record() for source in self.sources],
            "cycle_count": len(self.cycle_reports),
            "baseline_id": self.baseline_id,
        }


def _read_jsonl(path: Path) -> tuple[list[Mapping[str, object]], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows: list[Mapping[str, object]] = []
    for line_number, raw_line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        text = raw_line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"baseline_invalid_jsonl path={path} line={line_number}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"baseline_jsonl_row_not_object path={path} line={line_number}")
        rows.append(payload)
    if not rows:
        raise ValueError(f"baseline_source_empty path={path}")
    return rows, digest


def _group_cycles(path: Path, rows: Sequence[Mapping[str, object]]) -> dict[str, list[CandidateScoreObservation]]:
    latest_by_cycle: dict[str, dict[str, CandidateScoreObservation]] = {}
    for row in rows:
        score_value = row.get("final_score") if row.get("final_score") is not None else row.get("score")
        if score_value is None or not bool(row.get("rankable")):
            continue
        observation = CandidateScoreObservation.from_mapping(row)
        unique_cycle_id = f"{path.as_posix()}::{observation.cycle_id}"
        normalized = CandidateScoreObservation(
            candidate_id=observation.candidate_id,
            cycle_id=unique_cycle_id,
            score=observation.score,
            rankable=observation.rankable,
            executable=observation.executable,
            direction=observation.direction,
            fallback_used=observation.fallback_used,
            recovered_fallback=observation.recovered_fallback,
            stale_quote=observation.stale_quote,
            outcome_value=observation.outcome_value,
        )
        latest_by_cycle.setdefault(unique_cycle_id, {})[normalized.candidate_id] = normalized
    if not latest_by_cycle:
        raise ValueError(f"baseline_source_has_no_rankable_scored_cycles path={path}")
    return {
        cycle_id: list(candidate_map.values())
        for cycle_id, candidate_map in latest_by_cycle.items()
    }


def build_ranking_baseline(
    paths: Iterable[str | Path],
    *,
    metric_names: Sequence[str],
) -> RankingBaseline:
    sources_paths = tuple(Path(path).expanduser() for path in paths)
    if not sources_paths:
        raise ValueError("baseline_paths_empty")
    metrics = tuple(dict.fromkeys(str(name).strip() for name in metric_names if str(name).strip()))
    if not metrics:
        raise ValueError("baseline_metric_names_empty")
    ranking_metrics: dict[str, list[float]] = {metric: [] for metric in metrics}
    cycle_reports: list[dict[str, object]] = []
    sources: list[BaselineSource] = []
    for path in sorted(sources_paths, key=lambda item: item.as_posix()):
        if not path.is_file():
            raise ValueError(f"baseline_source_not_file path={path}")
        rows, digest = _read_jsonl(path)
        cycles = _group_cycles(path, rows)
        for cycle_id in sorted(cycles):
            report = analyze_score_separation(cycles[cycle_id])
            record = report.to_record()
            metric_record: dict[str, float] = {}
            for metric in metrics:
                value = record.get(metric)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError(f"baseline_metric_not_numeric={metric}")
                numeric = float(value)
                ranking_metrics[metric].append(numeric)
                metric_record[metric] = numeric
            cycle_reports.append(
                {
                    "cycle_id": cycle_id,
                    "source_path": path.as_posix(),
                    "metrics": metric_record,
                }
            )
        sources.append(BaselineSource(path.as_posix(), digest, len(rows), len(cycles)))
    canonical = {
        "schema_version": "1.0.0",
        "metric_names": list(metrics),
        "ranking_metrics": ranking_metrics,
        "cycle_reports": cycle_reports,
        "sources": [source.to_record() for source in sources],
    }
    baseline_id = _canonical_hash(canonical)
    return RankingBaseline(
        schema_version="1.0.0",
        metric_names=metrics,
        ranking_metrics={key: tuple(values) for key, values in ranking_metrics.items()},
        cycle_reports=tuple(cycle_reports),
        sources=tuple(sources),
        baseline_id=baseline_id,
    )
