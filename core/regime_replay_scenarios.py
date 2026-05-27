"""Read-only regime replay scenarios for EDGE-91.

This module replays deterministic market-state snapshots through the existing
MarketState model and verifies expected regime classifications. It does not
rank candidates, select strategies, wire runtime behavior, call brokers, append
events, or create trade/execution intent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.market_state import build_market_state

REGIME_REPLAY_SCHEMA_VERSION = 1
REGIME_REPLAY_SOURCE = "regime_replay_scenarios_v1"

REGIME_REPLAY_PASSED = "REGIME_REPLAY_PASSED"
REGIME_REPLAY_FAILED = "REGIME_REPLAY_FAILED"
REGIME_REPLAY_BLOCKED = "REGIME_REPLAY_BLOCKED"

STEP_STATUS_PASSED = "PASSED"
STEP_STATUS_FAILED = "FAILED"
STEP_STATUS_BLOCKED = "BLOCKED"

SCENARIO_STATUS_PASSED = "PASSED"
SCENARIO_STATUS_FAILED = "FAILED"
SCENARIO_STATUS_BLOCKED = "BLOCKED"

OK_REASON = "ok"
NO_SCENARIOS_REASON = "no_regime_replay_scenarios"
INVALID_SCENARIO_REASON = "invalid_regime_replay_scenario"
NO_SCENARIO_STEPS_REASON = "no_regime_replay_steps"
INVALID_STEP_REASON = "invalid_regime_replay_step"
INVALID_SNAPSHOT_REASON = "invalid_regime_replay_snapshot"
REGIME_EXPECTATION_MISMATCH_REASON = "regime_expectation_mismatch"
REGIME_STEP_BLOCKED_REASON = "regime_replay_step_blocked"
TRANSITION_EXPECTATION_MISMATCH_REASON = "regime_transition_expectation_mismatch"
UNKNOWN_SCENARIO = "UNKNOWN_SCENARIO"
UNKNOWN_STEP = "UNKNOWN_STEP"
UNKNOWN_REGIME_ID = "UNKNOWN"

_DIMENSION_NAMES = ("trend", "volatility", "breadth", "liquidity", "session")
_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class RegimeReplayStep:
    """One replay input snapshot plus optional expected classification."""

    step_id: str
    snapshot: Mapping[str, Any]
    expected_dimensions: Mapping[str, Any] = field(default_factory=dict)
    expected_regime_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "step_id": _text(self.step_id) or UNKNOWN_STEP,
            "snapshot": _safe_json_mapping(self.snapshot),
            "expected_dimensions": _safe_json_mapping(self.expected_dimensions),
            "expected_regime_id": _text(self.expected_regime_id),
            "metadata": _safe_json_mapping(self.metadata),
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class RegimeReplayScenario:
    """A deterministic regime replay scenario."""

    scenario_id: str
    description: str
    steps: Sequence[RegimeReplayStep | Mapping[str, Any]]
    expected_transition_count: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "scenario_id": _text(self.scenario_id) or UNKNOWN_SCENARIO,
            "description": _text(self.description),
            "steps": [_payload(step) for step in self.steps],
            "expected_transition_count": self.expected_transition_count,
            "metadata": _safe_json_mapping(self.metadata),
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class RegimeReplayStepResult:
    """Replay result for one scenario step."""

    step_id: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    regime_id: str
    expected_regime_id: str
    dimensions: dict[str, str]
    expected_dimensions: dict[str, str]
    dimension_mismatches: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence: float
    evidence_snapshot: dict[str, Any]
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "step_id": self.step_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "regime_id": self.regime_id,
            "expected_regime_id": self.expected_regime_id,
            "dimensions": dict(self.dimensions),
            "expected_dimensions": dict(self.expected_dimensions),
            "dimension_mismatches": list(self.dimension_mismatches),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "confidence": self.confidence,
            "evidence_snapshot": dict(self.evidence_snapshot),
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class RegimeReplayScenarioResult:
    """Replay result for one full scenario."""

    scenario_id: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    step_count: int
    passed_step_count: int
    failed_step_count: int
    blocked_step_count: int
    expected_transition_count: int | None
    actual_transition_count: int
    transition_count_ok: bool
    first_regime_id: str
    terminal_regime_id: str
    transitions: tuple[dict[str, Any], ...]
    steps: tuple[RegimeReplayStepResult, ...]
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "step_count": self.step_count,
            "passed_step_count": self.passed_step_count,
            "failed_step_count": self.failed_step_count,
            "blocked_step_count": self.blocked_step_count,
            "expected_transition_count": self.expected_transition_count,
            "actual_transition_count": self.actual_transition_count,
            "transition_count_ok": self.transition_count_ok,
            "first_regime_id": self.first_regime_id,
            "terminal_regime_id": self.terminal_regime_id,
            "transitions": [dict(item) for item in self.transitions],
            "steps": [step.to_payload() for step in self.steps],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class RegimeReplayReport:
    """Top-level read-only regime replay report."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    scenario_count: int
    passed_scenario_count: int
    failed_scenario_count: int
    blocked_scenario_count: int
    results: tuple[RegimeReplayScenarioResult, ...]
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "scenario_count": self.scenario_count,
            "passed_scenario_count": self.passed_scenario_count,
            "failed_scenario_count": self.failed_scenario_count,
            "blocked_scenario_count": self.blocked_scenario_count,
            "results": [result.to_payload() for result in self.results],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def default_regime_replay_scenarios() -> tuple[RegimeReplayScenario, ...]:
    """Return deterministic canonical scenarios for EDGE-91 replay proof."""

    return (
        RegimeReplayScenario(
            scenario_id="opening_uptrend_to_midday_range",
            description="Opening trend expansion cools into a low-volatility midday range.",
            expected_transition_count=1,
            steps=(
                RegimeReplayStep(
                    step_id="opening_trend_expansion",
                    snapshot={
                        "index_change_pct": 0.82,
                        "vwap_distance_pct": 0.58,
                        "ema_slope_pct": 0.44,
                        "atr_pct": 0.82,
                        "realized_vol_pct": 0.72,
                        "india_vix": 18.2,
                        "advance_decline_ratio": 1.8,
                        "sector_positive_pct": 68.0,
                        "avg_spread_bps": 9.0,
                        "depth_score": 0.82,
                        "quote_age_sec": 1.0,
                        "session_phase": "OPENING",
                    },
                    expected_dimensions={
                        "trend": "UP",
                        "volatility": "HIGH",
                        "breadth": "BULLISH",
                        "liquidity": "DEEP",
                        "session": "OPENING",
                    },
                    expected_regime_id="UP_HIGH_BULLISH_DEEP_OPENING",
                ),
                RegimeReplayStep(
                    step_id="midday_range_compression",
                    snapshot={
                        "index_change_pct": 0.04,
                        "vwap_distance_pct": -0.03,
                        "ema_slope_pct": 0.02,
                        "atr_pct": 0.24,
                        "realized_vol_pct": 0.28,
                        "india_vix": 11.5,
                        "advance_decline_ratio": 1.02,
                        "sector_positive_pct": 51.0,
                        "avg_spread_bps": 24.0,
                        "depth_score": 0.62,
                        "quote_age_sec": 1.0,
                        "session_phase": "MIDDAY",
                    },
                    expected_dimensions={
                        "trend": "SIDEWAYS",
                        "volatility": "LOW",
                        "breadth": "MIXED",
                        "liquidity": "NORMAL",
                        "session": "MIDDAY",
                    },
                    expected_regime_id="SIDEWAYS_LOW_MIXED_NORMAL_MIDDAY",
                ),
            ),
            metadata={"canonical": True, "scenario_family": "trend_to_range"},
        ),
        RegimeReplayScenario(
            scenario_id="closing_downtrend_extreme_thin",
            description="Closing selloff with bearish breadth, extreme volatility, and thin liquidity.",
            expected_transition_count=0,
            steps=(
                RegimeReplayStep(
                    step_id="closing_selloff",
                    snapshot={
                        "index_change_pct": -1.1,
                        "vwap_distance_pct": -0.9,
                        "ema_slope_pct": -0.55,
                        "atr_pct": 1.45,
                        "realized_vol_pct": 1.55,
                        "india_vix": 24.0,
                        "advance_decline_ratio": 0.42,
                        "sector_positive_pct": 24.0,
                        "avg_spread_bps": 64.0,
                        "depth_score": 0.28,
                        "quote_age_sec": 2.0,
                        "session_phase": "CLOSING",
                    },
                    expected_dimensions={
                        "trend": "DOWN",
                        "volatility": "EXTREME",
                        "breadth": "BEARISH",
                        "liquidity": "THIN",
                        "session": "CLOSING",
                    },
                    expected_regime_id="DOWN_EXTREME_BEARISH_THIN_CLOSING",
                ),
            ),
            metadata={"canonical": True, "scenario_family": "selloff"},
        ),
    )


def build_regime_replay_report(
    scenarios: Iterable[RegimeReplayScenario | Mapping[str, Any]] | None = None,
    *,
    symbol: str = "MARKET",
    mode: str = "PAPER",
) -> RegimeReplayReport:
    """Replay deterministic market snapshots and verify regime expectations."""

    scenario_items = default_regime_replay_scenarios() if scenarios is None else tuple(_iterable_or_empty(scenarios))
    if not scenario_items:
        return _report(
            status=REGIME_REPLAY_BLOCKED,
            reason_code=NO_SCENARIOS_REASON,
            reasons=(NO_SCENARIOS_REASON,),
            results=(),
            metadata={"symbol": _text(symbol) or "MARKET", "mode": _text(mode).upper() or "PAPER"},
        )

    results = tuple(_replay_scenario(item, symbol=symbol, mode=mode) for item in scenario_items)
    blocked_count = sum(1 for item in results if item.status == SCENARIO_STATUS_BLOCKED)
    failed_count = sum(1 for item in results if item.status == SCENARIO_STATUS_FAILED)
    if blocked_count:
        status = REGIME_REPLAY_BLOCKED
        reason_code = REGIME_STEP_BLOCKED_REASON
    elif failed_count:
        status = REGIME_REPLAY_FAILED
        reason_code = REGIME_EXPECTATION_MISMATCH_REASON
    else:
        status = REGIME_REPLAY_PASSED
        reason_code = OK_REASON
    return _report(
        status=status,
        reason_code=reason_code,
        reasons=_dedupe((reason_code, *(reason for result in results for reason in result.reasons if reason != OK_REASON))),
        results=results,
        metadata={
            "symbol": _text(symbol) or "MARKET",
            "mode": _text(mode).upper() or "PAPER",
            "scenario_source": "default" if scenarios is None else "provided",
            "evidence_only": True,
            "does_not_rank_candidates": True,
            "does_not_select_strategies": True,
        },
    )


def _replay_scenario(
    scenario: RegimeReplayScenario | Mapping[str, Any],
    *,
    symbol: str,
    mode: str,
) -> RegimeReplayScenarioResult:
    payload = _payload(scenario)
    scenario_id = _text(payload.get("scenario_id")) or UNKNOWN_SCENARIO
    raw_steps = payload.get("steps")
    if not isinstance(payload, Mapping) or not scenario_id or not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
        return _blocked_scenario_result(scenario_id=scenario_id, reason_code=INVALID_SCENARIO_REASON)
    if not raw_steps:
        return _blocked_scenario_result(scenario_id=scenario_id, reason_code=NO_SCENARIO_STEPS_REASON)

    steps = tuple(_replay_step(step, symbol=symbol, mode=mode) for step in raw_steps)
    transitions = _build_transitions(steps)
    actual_transition_count = sum(1 for item in transitions if item.get("changed") is True)
    expected_transition_count = _optional_non_negative_int(payload.get("expected_transition_count"))
    transition_count_ok = expected_transition_count is None or expected_transition_count == actual_transition_count

    blocked_step_count = sum(1 for step in steps if step.status == STEP_STATUS_BLOCKED)
    failed_step_count = sum(1 for step in steps if step.status == STEP_STATUS_FAILED)
    if blocked_step_count:
        status = SCENARIO_STATUS_BLOCKED
        reason_code = REGIME_STEP_BLOCKED_REASON
    elif failed_step_count:
        status = SCENARIO_STATUS_FAILED
        reason_code = REGIME_EXPECTATION_MISMATCH_REASON
    elif not transition_count_ok:
        status = SCENARIO_STATUS_FAILED
        reason_code = TRANSITION_EXPECTATION_MISMATCH_REASON
    else:
        status = SCENARIO_STATUS_PASSED
        reason_code = OK_REASON

    reasons = _dedupe((reason_code, *(reason for step in steps for reason in step.reasons if reason != OK_REASON)))
    if not transition_count_ok:
        reasons = _dedupe((*reasons, TRANSITION_EXPECTATION_MISMATCH_REASON))

    return RegimeReplayScenarioResult(
        scenario_id=scenario_id,
        status=status,
        reason_code=reason_code,
        reasons=reasons,
        step_count=len(steps),
        passed_step_count=sum(1 for step in steps if step.status == STEP_STATUS_PASSED),
        failed_step_count=failed_step_count,
        blocked_step_count=blocked_step_count,
        expected_transition_count=expected_transition_count,
        actual_transition_count=actual_transition_count,
        transition_count_ok=transition_count_ok,
        first_regime_id=steps[0].regime_id if steps else UNKNOWN_REGIME_ID,
        terminal_regime_id=steps[-1].regime_id if steps else UNKNOWN_REGIME_ID,
        transitions=transitions,
        steps=steps,
        metadata={
            "description": _text(payload.get("description")),
            "source_metadata": _safe_json_mapping(payload.get("metadata")),
        },
    )


def _replay_step(
    step: RegimeReplayStep | Mapping[str, Any],
    *,
    symbol: str,
    mode: str,
) -> RegimeReplayStepResult:
    payload = _payload(step)
    step_id = _text(payload.get("step_id")) or UNKNOWN_STEP
    snapshot = payload.get("snapshot")
    if not isinstance(payload, Mapping):
        return _blocked_step_result(step_id=step_id, reason_code=INVALID_STEP_REASON)
    if not isinstance(snapshot, Mapping):
        return _blocked_step_result(step_id=step_id, reason_code=INVALID_SNAPSHOT_REASON)

    market_state = build_market_state(snapshot, symbol=symbol, mode=mode)
    dimensions = {
        "trend": _dimension_value(market_state.trend),
        "volatility": _dimension_value(market_state.volatility),
        "breadth": _dimension_value(market_state.breadth),
        "liquidity": _dimension_value(market_state.liquidity),
        "session": _dimension_value(market_state.session),
    }
    expected_dimensions = _expected_dimensions(payload)
    blockers = _tuple_text(market_state.blockers)
    warnings = _tuple_text(market_state.warnings)
    regime_id = UNKNOWN_REGIME_ID if blockers else _regime_id(dimensions)
    expected_regime_id = _text(payload.get("expected_regime_id")) or _text(expected_dimensions.pop("regime_id", ""))
    mismatches = _dimension_mismatches(dimensions, expected_dimensions)
    if expected_regime_id and expected_regime_id != regime_id:
        mismatches = _dedupe((*mismatches, "regime_id"))

    if blockers:
        status = STEP_STATUS_BLOCKED
        reason_code = REGIME_STEP_BLOCKED_REASON
    elif mismatches:
        status = STEP_STATUS_FAILED
        reason_code = REGIME_EXPECTATION_MISMATCH_REASON
    else:
        status = STEP_STATUS_PASSED
        reason_code = OK_REASON

    return RegimeReplayStepResult(
        step_id=step_id,
        status=status,
        reason_code=reason_code,
        reasons=_dedupe((reason_code, *blockers, *mismatches)),
        regime_id=regime_id,
        expected_regime_id=expected_regime_id,
        dimensions=dimensions,
        expected_dimensions=expected_dimensions,
        dimension_mismatches=mismatches,
        blockers=blockers,
        warnings=warnings,
        confidence=float(market_state.confidence),
        evidence_snapshot=dict(market_state.evidence_snapshot),
        metadata={"source": market_state.source, "symbol": market_state.symbol, "mode": market_state.mode},
    )


def _blocked_step_result(*, step_id: str, reason_code: str) -> RegimeReplayStepResult:
    return RegimeReplayStepResult(
        step_id=_text(step_id) or UNKNOWN_STEP,
        status=STEP_STATUS_BLOCKED,
        reason_code=reason_code,
        reasons=(reason_code,),
        regime_id=UNKNOWN_REGIME_ID,
        expected_regime_id="",
        dimensions={},
        expected_dimensions={},
        dimension_mismatches=(),
        blockers=(reason_code,),
        warnings=(),
        confidence=0.0,
        evidence_snapshot={},
        metadata={"blocked_before_market_state": True},
    )


def _blocked_scenario_result(*, scenario_id: str, reason_code: str) -> RegimeReplayScenarioResult:
    return RegimeReplayScenarioResult(
        scenario_id=_text(scenario_id) or UNKNOWN_SCENARIO,
        status=SCENARIO_STATUS_BLOCKED,
        reason_code=reason_code,
        reasons=(reason_code,),
        step_count=0,
        passed_step_count=0,
        failed_step_count=0,
        blocked_step_count=0,
        expected_transition_count=None,
        actual_transition_count=0,
        transition_count_ok=False,
        first_regime_id=UNKNOWN_REGIME_ID,
        terminal_regime_id=UNKNOWN_REGIME_ID,
        transitions=(),
        steps=(),
        metadata={"blocked_before_replay": True},
    )


def _report(
    *,
    status: str,
    reason_code: str,
    reasons: tuple[str, ...],
    results: tuple[RegimeReplayScenarioResult, ...],
    metadata: dict[str, Any] | None = None,
) -> RegimeReplayReport:
    return RegimeReplayReport(
        schema_version=REGIME_REPLAY_SCHEMA_VERSION,
        source=REGIME_REPLAY_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=_dedupe(reasons),
        scenario_count=len(results),
        passed_scenario_count=sum(1 for item in results if item.status == SCENARIO_STATUS_PASSED),
        failed_scenario_count=sum(1 for item in results if item.status == SCENARIO_STATUS_FAILED),
        blocked_scenario_count=sum(1 for item in results if item.status == SCENARIO_STATUS_BLOCKED),
        results=results,
        metadata=dict(metadata or {}),
    )


def _build_transitions(steps: Sequence[RegimeReplayStepResult]) -> tuple[dict[str, Any], ...]:
    transitions: list[dict[str, Any]] = []
    for previous, current in zip(steps, steps[1:]):
        changed = previous.regime_id != current.regime_id
        item = {
            "from_step_id": previous.step_id,
            "to_step_id": current.step_id,
            "from_regime_id": previous.regime_id,
            "to_regime_id": current.regime_id,
            "changed": changed,
            "read_only": True,
            "append": False,
        }
        _mark_non_action(item)
        transitions.append(item)
    return tuple(transitions)


def _expected_dimensions(payload: Mapping[str, Any]) -> dict[str, str]:
    raw = payload.get("expected_dimensions")
    if not isinstance(raw, Mapping):
        raw = payload.get("expected")
    expected = {name: _text(value).upper() for name, value in dict(raw or {}).items() if _text(value)} if isinstance(raw, Mapping) else {}
    for name in _DIMENSION_NAMES:
        direct = _text(payload.get(f"expected_{name}"))
        if direct:
            expected[name] = direct.upper()
    return {str(key): str(value) for key, value in expected.items() if str(key)}


def _dimension_mismatches(actual: Mapping[str, str], expected: Mapping[str, str]) -> tuple[str, ...]:
    mismatches = []
    for name in _DIMENSION_NAMES:
        expected_value = _text(expected.get(name)).upper()
        if expected_value and expected_value != _text(actual.get(name)).upper():
            mismatches.append(name)
    return tuple(mismatches)


def _regime_id(dimensions: Mapping[str, str]) -> str:
    values = [_text(dimensions.get(name)).upper() or UNKNOWN_REGIME_ID for name in _DIMENSION_NAMES]
    return "_".join(values)


def _dimension_value(dimension: Any) -> str:
    return _text(getattr(dimension, "value", "")).upper() or UNKNOWN_REGIME_ID


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_payload"):
        value = value.to_payload()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _iterable_or_empty(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        return ()
    try:
        return tuple(value)
    except Exception:
        return ()


def _optional_non_negative_int(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return max(0, int(value))
    except Exception:
        return None


def _tuple_text(values: Any) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        iterable = (values,)
    else:
        try:
            iterable = tuple(values or ())
        except Exception:
            iterable = ()
    return _dedupe(_text(value) for value in iterable)


def _safe_json_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _safe_json_value(item) for key, item in value.items()}


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "INVALID_SCENARIO_REASON",
    "INVALID_SNAPSHOT_REASON",
    "NO_SCENARIOS_REASON",
    "REGIME_EXPECTATION_MISMATCH_REASON",
    "REGIME_REPLAY_BLOCKED",
    "REGIME_REPLAY_FAILED",
    "REGIME_REPLAY_PASSED",
    "REGIME_REPLAY_SCHEMA_VERSION",
    "REGIME_REPLAY_SOURCE",
    "REGIME_STEP_BLOCKED_REASON",
    "TRANSITION_EXPECTATION_MISMATCH_REASON",
    "RegimeReplayReport",
    "RegimeReplayScenario",
    "RegimeReplayScenarioResult",
    "RegimeReplayStep",
    "RegimeReplayStepResult",
    "build_regime_replay_report",
    "default_regime_replay_scenarios",
]
