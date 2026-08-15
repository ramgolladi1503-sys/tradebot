from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
import json
import math
import uuid

from .contracts import CanonicalEvent, canonical_json, parse_timestamp
from .publisher import FilePublisher
from .storage import atomic_write_json


SPEC_VERSION = "CAS_A1_FROZEN_PROSPECTIVE_V1"
EXPECTATION_INTERCEPT = 15.5350561749
EXPECTATION_SLOPE = 2.9081599522
EXPECTED_CONSTITUENT_COUNT = 49

BROKER_WRITE_AUTHORITY = False
ORDER_AUTHORITY = False
PAPER_AUTHORIZED = False
LIVE_AUTHORIZED = False

FROZEN_SPEC_PAYLOAD = {
    "spec_version": SPEC_VERSION,
    "expectation_intercept": EXPECTATION_INTERCEPT,
    "expectation_slope": EXPECTATION_SLOPE,
    "constituent_window_start": "15:10:00",
    "constituent_window_end": "15:14:59",
    "index_reference_time": "15:14:00",
    "cas_finalization_not_before": "15:28:00",
    "target_start": "15:29:00",
    "target_end": "15:39:00",
    "prediction_rule": "SIGN_OF_REALIZED_SURPRISE",
    "refit_authorized": False,
    "threshold_search_authorized": False,
}
FROZEN_SPEC_SHA256 = sha256(canonical_json(FROZEN_SPEC_PAYLOAD).encode("utf-8")).hexdigest()


class CasA1ContractError(ValueError):
    pass


class CasA1EvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConstituentMark:
    instrument_key: str
    price_1510: float
    price_1514: float
    source_event_ids: tuple[str, ...] = ()

    @property
    def return_bps(self) -> float:
        return (self.price_1514 / self.price_1510 - 1.0) * 10000.0


@dataclass(frozen=True, slots=True)
class CasA1Observation:
    session_id: str
    session_date: str
    index_instrument: str
    futures_instrument: str
    constituent_marks: tuple[ConstituentMark, ...]
    nifty_1514: float
    nifty_1514_available_time: datetime
    final_cas_index: float
    final_cas_available_time: datetime
    future_1529: float
    future_1529_available_time: datetime
    future_1539: float
    future_1539_available_time: datetime
    source_provider: str
    source_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CasA1Result:
    spec_version: str
    spec_sha256: str
    session_id: str
    session_date: str
    constituent_count: int
    equal_weight_return_1510_1514_bps: float
    expected_cas_adjustment_bps: float
    nifty_1514: float
    final_cas_index: float
    final_cas_available_time: str
    realized_cas_adjustment_bps: float
    auction_surprise_bps: float
    prediction: str
    future_1529: float
    future_1539: float
    future_1529_1539_bps: float
    actual_sign: str
    correct: bool | None
    broker_write_authority: bool = BROKER_WRITE_AUTHORITY
    order_authority: bool = ORDER_AUTHORITY
    paper_authorized: bool = PAPER_AUTHORIZED
    live_authorized: bool = LIVE_AUTHORIZED
    historical_edge_supported: bool = False
    out_of_sample_supported: bool = False
    execution_viable: bool = False
    prospective_supported: bool = False
    structural_edge_certified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CasA1Blocked:
    status: str
    session_id: str
    session_date: str
    blockers: tuple[str, ...]
    spec_version: str = SPEC_VERSION
    spec_sha256: str = FROZEN_SPEC_SHA256
    broker_write_authority: bool = BROKER_WRITE_AUTHORITY
    order_authority: bool = ORDER_AUTHORITY
    paper_authorized: bool = PAPER_AUTHORIZED
    live_authorized: bool = LIVE_AUTHORIZED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite_positive(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CasA1EvidenceError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise CasA1EvidenceError(f"{field_name} must be finite and positive")
    return number


def _ist_clock(dt: datetime) -> tuple[int, int, int]:
    from zoneinfo import ZoneInfo

    local = parse_timestamp(dt, field_name="timestamp").astimezone(ZoneInfo("Asia/Kolkata"))
    return local.hour, local.minute, local.second


def _session_date_of(dt: datetime) -> str:
    from zoneinfo import ZoneInfo

    return parse_timestamp(dt, field_name="timestamp").astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()


def validate_frozen_contract(contract: Mapping[str, Any]) -> None:
    raw = contract.get("cas_a1") if isinstance(contract, Mapping) else None
    if not isinstance(raw, Mapping):
        raise CasA1ContractError("analytics_contract.cas_a1 is required")
    if raw.get("enabled") is not True:
        raise CasA1ContractError("cas_a1.enabled must be true")

    expected = dict(FROZEN_SPEC_PAYLOAD)
    for key, value in expected.items():
        if raw.get(key) != value:
            raise CasA1ContractError(
                f"CAS-A1 frozen contract drift for {key}: expected {value!r}, got {raw.get(key)!r}"
            )

    if raw.get("spec_sha256") not in (None, "", FROZEN_SPEC_SHA256):
        raise CasA1ContractError("CAS-A1 frozen spec_sha256 mismatch")

    constituents = raw.get("frozen_constituents")
    if not isinstance(constituents, list) or len(constituents) != EXPECTED_CONSTITUENT_COUNT:
        raise CasA1ContractError(
            f"CAS-A1 requires exactly {EXPECTED_CONSTITUENT_COUNT} frozen constituent instrument keys"
        )
    normalized = [str(value or "").strip() for value in constituents]
    if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
        raise CasA1ContractError("frozen_constituents must contain unique non-empty instrument keys")


def _validate_observation(observation: CasA1Observation, contract: Mapping[str, Any]) -> None:
    validate_frozen_contract(contract)
    raw = contract["cas_a1"]
    expected_constituents = tuple(str(x).strip() for x in raw["frozen_constituents"])
    observed = tuple(mark.instrument_key for mark in observation.constituent_marks)

    blockers: list[str] = []
    if len(observed) != EXPECTED_CONSTITUENT_COUNT:
        blockers.append("FROZEN_CONSTITUENT_COUNT_MISMATCH")
    if set(observed) != set(expected_constituents):
        missing = sorted(set(expected_constituents) - set(observed))
        extra = sorted(set(observed) - set(expected_constituents))
        blockers.append(f"FROZEN_CONSTITUENT_IDENTITY_MISMATCH missing={missing} extra={extra}")
    if observation.session_date != observation.session_id and observation.session_date not in observation.session_id:
        blockers.append("SESSION_ID_DATE_MISMATCH")
    if not observation.index_instrument:
        blockers.append("MISSING_INDEX_INSTRUMENT")
    if not observation.futures_instrument:
        blockers.append("MISSING_FUTURES_INSTRUMENT")
    if not observation.source_provider:
        blockers.append("MISSING_SOURCE_PROVIDER")

    for mark in observation.constituent_marks:
        _finite_positive(mark.price_1510, f"{mark.instrument_key}.price_1510")
        _finite_positive(mark.price_1514, f"{mark.instrument_key}.price_1514")

    for field_name in ("nifty_1514", "final_cas_index", "future_1529", "future_1539"):
        _finite_positive(getattr(observation, field_name), field_name)

    times = {
        "nifty_1514_available_time": observation.nifty_1514_available_time,
        "final_cas_available_time": observation.final_cas_available_time,
        "future_1529_available_time": observation.future_1529_available_time,
        "future_1539_available_time": observation.future_1539_available_time,
    }
    for name, dt in times.items():
        if _session_date_of(dt) != observation.session_date:
            blockers.append(f"CROSS_SESSION_TIMESTAMP:{name}")

    if _ist_clock(observation.final_cas_available_time) < (15, 28, 0):
        blockers.append("FINAL_CAS_AVAILABLE_BEFORE_FROZEN_CAUSAL_BOUNDARY")
    if _ist_clock(observation.future_1529_available_time) < (15, 29, 0):
        blockers.append("FUTURE_1529_AVAILABLE_TOO_EARLY")
    if _ist_clock(observation.future_1539_available_time) < (15, 39, 0):
        blockers.append("FUTURE_1539_AVAILABLE_TOO_EARLY")
    if observation.future_1539_available_time < observation.future_1529_available_time:
        blockers.append("NON_MONOTONIC_FUTURES_TIMESTAMPS")

    if blockers:
        raise CasA1EvidenceError("; ".join(blockers))


def evaluate_cas_a1(observation: CasA1Observation, contract: Mapping[str, Any]) -> CasA1Result:
    _validate_observation(observation, contract)

    ew_bps = sum(mark.return_bps for mark in observation.constituent_marks) / len(observation.constituent_marks)
    expected = EXPECTATION_INTERCEPT + EXPECTATION_SLOPE * ew_bps
    realized = (observation.final_cas_index / observation.nifty_1514 - 1.0) * 10000.0
    surprise = realized - expected
    prediction = "UP" if surprise > 0 else ("DOWN" if surprise < 0 else "NO_PREDICTION")
    future_return = (observation.future_1539 / observation.future_1529 - 1.0) * 10000.0
    actual_sign = "UP" if future_return > 0 else ("DOWN" if future_return < 0 else "FLAT")
    correct = None if prediction == "NO_PREDICTION" or actual_sign == "FLAT" else prediction == actual_sign

    return CasA1Result(
        spec_version=SPEC_VERSION,
        spec_sha256=FROZEN_SPEC_SHA256,
        session_id=observation.session_id,
        session_date=observation.session_date,
        constituent_count=len(observation.constituent_marks),
        equal_weight_return_1510_1514_bps=ew_bps,
        expected_cas_adjustment_bps=expected,
        nifty_1514=observation.nifty_1514,
        final_cas_index=observation.final_cas_index,
        final_cas_available_time=parse_timestamp(
            observation.final_cas_available_time, field_name="final_cas_available_time"
        ).isoformat().replace("+00:00", "Z"),
        realized_cas_adjustment_bps=realized,
        auction_surprise_bps=surprise,
        prediction=prediction,
        future_1529=observation.future_1529,
        future_1539=observation.future_1539,
        future_1529_1539_bps=future_return,
        actual_sign=actual_sign,
        correct=correct,
    )


def _event(
    *,
    event_type: str,
    observation: CasA1Observation,
    producer_sequence: int,
    available_time: datetime,
    payload: Mapping[str, Any],
    parent_event_ids: Sequence[str] = (),
) -> CanonicalEvent:
    stable_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{observation.session_id}:{SPEC_VERSION}:{event_type}",
    )
    now = datetime.now(timezone.utc)
    available = parse_timestamp(available_time, field_name="available_time")
    if now < available:
        now = available
    return CanonicalEvent(
        event_id=str(stable_id),
        event_type=event_type,
        session_id=observation.session_id,
        run_id=observation.session_id,
        trace_id=observation.session_id,
        parent_event_ids=tuple(parent_event_ids),
        producer_id="cas-a1-prospective-analytics",
        producer_sequence=producer_sequence,
        source_component="aixion_trade_intelligence.cas_a1",
        source_provider=observation.source_provider,
        event_time=available,
        source_time=available,
        receive_time=available,
        available_time=available,
        parse_time=now,
        persist_time=now,
        instrument_key=observation.index_instrument,
        underlying="NIFTY",
        model_id="CAS_A1_AUCTION_SURPRISE",
        model_version=SPEC_VERSION,
        data_quality_state="PROSPECTIVE_RESEARCH_OBSERVED",
        authority_class="RESEARCH_ONLY_NO_EXECUTION_AUTHORITY",
        payload=dict(payload),
    )


def build_cas_a1_events(observation: CasA1Observation, contract: Mapping[str, Any]) -> tuple[CanonicalEvent, ...]:
    result = evaluate_cas_a1(observation, contract)
    constituent_evidence = tuple(
        dict.fromkeys(
            event_id
            for mark in observation.constituent_marks
            for event_id in mark.source_event_ids
            if event_id
        )
    )

    expectation = _event(
        event_type="CAS_A1_EXPECTATION_FROZEN",
        observation=observation,
        producer_sequence=1,
        available_time=observation.nifty_1514_available_time,
        payload={
            "spec_version": SPEC_VERSION,
            "spec_sha256": FROZEN_SPEC_SHA256,
            "constituent_count": result.constituent_count,
            "equal_weight_return_1510_1514_bps": result.equal_weight_return_1510_1514_bps,
            "expected_cas_adjustment_bps": result.expected_cas_adjustment_bps,
            "refit_authorized": False,
            "threshold_search_authorized": False,
            "source_event_ids": list(constituent_evidence),
        },
    )
    final_price = _event(
        event_type="CAS_FINAL_PRICE_OBSERVED",
        observation=observation,
        producer_sequence=2,
        available_time=observation.final_cas_available_time,
        parent_event_ids=(expectation.event_id,),
        payload={
            "nifty_1514": result.nifty_1514,
            "final_cas_index": result.final_cas_index,
            "realized_cas_adjustment_bps": result.realized_cas_adjustment_bps,
        },
    )
    surprise = _event(
        event_type="CAS_A1_SURPRISE_OBSERVED",
        observation=observation,
        producer_sequence=3,
        available_time=observation.final_cas_available_time,
        parent_event_ids=(expectation.event_id, final_price.event_id),
        payload={
            "expected_cas_adjustment_bps": result.expected_cas_adjustment_bps,
            "realized_cas_adjustment_bps": result.realized_cas_adjustment_bps,
            "auction_surprise_bps": result.auction_surprise_bps,
        },
    )
    prediction = _event(
        event_type="CAS_A1_PREDICTION_FROZEN",
        observation=observation,
        producer_sequence=4,
        available_time=observation.final_cas_available_time,
        parent_event_ids=(surprise.event_id,),
        payload={
            "prediction": result.prediction,
            "prediction_rule": "SIGN_OF_REALIZED_SURPRISE",
            "auction_surprise_bps": result.auction_surprise_bps,
            "target_start": "15:29:00",
            "target_end": "15:39:00",
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        },
    )
    outcome = _event(
        event_type="CAS_A1_OUTCOME_OBSERVED",
        observation=observation,
        producer_sequence=5,
        available_time=observation.future_1539_available_time,
        parent_event_ids=(prediction.event_id,),
        payload={
            "futures_instrument": observation.futures_instrument,
            "future_1529": result.future_1529,
            "future_1539": result.future_1539,
            "future_1529_1539_bps": result.future_1529_1539_bps,
            "actual_sign": result.actual_sign,
            "prediction": result.prediction,
            "correct": result.correct,
            "prospective_supported": False,
            "structural_edge_certified": False,
        },
    )
    return expectation, final_price, surprise, prediction, outcome


def write_prospective_result(
    *,
    result: CasA1Result,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.session_date}_{SPEC_VERSION}.json"
    payload = result.to_dict()
    if path.exists():
        existing = json.loads(path.read_text())
        if canonical_json(existing) != canonical_json(payload):
            raise CasA1EvidenceError("immutable prospective result conflict")
        return path
    atomic_write_json(path, payload)
    return path


def append_events(events_path: Path, events: Sequence[CanonicalEvent]) -> None:
    publisher = FilePublisher(events_path, fsync=True)
    for event in events:
        publisher.publish(event)


def cumulative_summary(prospective_dir: Path) -> dict[str, Any]:
    rows: list[Mapping[str, Any]] = []
    for path in sorted(prospective_dir.glob(f"*_{SPEC_VERSION}.json")):
        raw = json.loads(path.read_text())
        if raw.get("spec_version") == SPEC_VERSION:
            rows.append(raw)
    correct = sum(row.get("correct") is True for row in rows)
    incorrect = sum(row.get("correct") is False for row in rows)
    no_prediction = sum(row.get("correct") is None for row in rows)
    scored = correct + incorrect
    return {
        "spec_version": SPEC_VERSION,
        "spec_sha256": FROZEN_SPEC_SHA256,
        "prospective_sessions": len(rows),
        "scored_sessions": scored,
        "correct": correct,
        "incorrect": incorrect,
        "no_prediction": no_prediction,
        "directional_accuracy": (correct / scored if scored else None),
        "development_sessions": 10,
        "development_alignment": "9/10",
        "development_and_prospective_pooled": False,
        "prospective_supported": False,
        "structural_edge_certified": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
