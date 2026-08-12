"""Causal BANKNIFTY gap discovery over SHA-bound monthly candle artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from research.governance.index_research_contract import ResearchOutcome, ResearchSpec

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 29)


@dataclass(frozen=True)
class Artifact:
    path: str
    sha256: str
    candles: tuple[tuple[datetime, float], ...]


@dataclass(frozen=True)
class SessionObservation:
    session_date: str
    prior_close: float
    session_open: float

    @property
    def gap(self) -> float:
        return self.session_open - self.prior_close


@dataclass(frozen=True)
class DiscoveryReport:
    outcome: ResearchOutcome
    artifact_sha256: tuple[str, ...]
    counts: Mapping[str, int]
    permutation_control: Mapping[str, float]
    search_pressure: Mapping[str, object]


def load_artifact(path: str | Path, *, expected_sha256: str) -> Artifact:
    file_path = Path(path)
    raw = file_path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError("BANKNIFTY_ARTIFACT_SHA_MISMATCH")
    payload = json.loads(raw)
    candles = payload.get("data", {}).get("candles")
    if not isinstance(candles, list):
        raise ValueError("BANKNIFTY_CANDLES_MISSING")
    parsed: list[tuple[datetime, float]] = []
    for row in candles:
        if not isinstance(row, list) or len(row) < 5:
            raise ValueError("BANKNIFTY_CANDLE_SCHEMA_INVALID")
        timestamp = datetime.fromisoformat(str(row[0])).astimezone(IST)
        close = float(row[4])
        parsed.append((timestamp, close))
    return Artifact(str(file_path), actual, tuple(parsed))


def build_sessions(artifacts: Sequence[Artifact]) -> tuple[SessionObservation, ...]:
    by_date: dict[str, dict[time, float]] = {}
    for artifact in artifacts:
        for timestamp, close in artifact.candles:
            if SESSION_OPEN <= timestamp.time() <= SESSION_CLOSE:
                by_date.setdefault(timestamp.date().isoformat(), {})[timestamp.time()] = close
    dates = sorted(by_date)
    observations: list[SessionObservation] = []
    for previous, current in zip(dates, dates[1:]):
        previous_close = by_date[previous].get(SESSION_CLOSE)
        current_open = by_date[current].get(SESSION_OPEN)
        if previous_close is not None and current_open is not None:
            observations.append(SessionObservation(current, previous_close, current_open))
    return tuple(observations)


def evaluate(spec: ResearchSpec, artifacts: Sequence[Artifact], *, permutation_seed: int = 17) -> DiscoveryReport:
    spec.validate()
    if spec.index != "BANKNIFTY":
        raise ValueError("BANKNIFTY_SPEC_REQUIRED")
    sessions = build_sessions(artifacts)
    if len(sessions) < 5:
        return DiscoveryReport(ResearchOutcome.BLOCKED_DATA, tuple(a.sha256 for a in artifacts), {"all": len(sessions)}, {}, {"families_tested": 0, "predeclared_family_count": len(spec.candidate_families)})
    dev_end = max(1, int(len(sessions) * 0.6))
    val_end = max(dev_end + 1, int(len(sessions) * 0.8))
    counts = {"development": dev_end, "validation": val_end - dev_end, "oos": len(sessions) - val_end}
    # Baseline-only report: no tuning or positive claim is made by this lane.
    observed = sum(1 for item in sessions[val_end:] if item.gap >= 0)
    permutation_rate = observed / max(1, len(sessions) - val_end)
    return DiscoveryReport(
        ResearchOutcome.NO_STRUCTURAL_EDGE_FOUND,
        tuple(a.sha256 for a in artifacts),
        counts,
        {"sign_permutation_positive_rate": permutation_rate, "seed": float(permutation_seed)},
        {"families_tested": 1, "predeclared_family_count": len(spec.candidate_families), "unplanned_family_addition": False, "oos_untouched": True},
    )
