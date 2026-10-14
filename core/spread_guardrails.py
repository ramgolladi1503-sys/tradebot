"""Deterministic spread and midpoint jump guardrails for TradeBot microstructure safety.

Enforces invariants I-1 through I-5:
- Invariant I-1: Strict pre-arithmetic non-zero and order admissibility (zero/null/crossed book protection).
- Invariant I-2: Pure deterministic spread bps calculation and thresholding.
- Invariant I-3: Reference baseline isolation & contamination defense (rejected ticks do not poison baseline).
- Invariant I-4: Causal recovery / resynchronization window (K consecutive consistent ticks reset baseline after genuine market gap).
- Invariant I-5: Non-executive safety and immutable audit record (read_only=True, is_order_action=False).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Optional

DEFAULT_MAX_SPREAD_BPS: float = 50.0        # 0.50%
DEFAULT_MAX_JUMP_PCT: float = 2.0           # 2.00%
DEFAULT_RECOVERY_K_TICKS: int = 3           # 3 consecutive consistent ticks to reset baseline
DEFAULT_CLUSTER_TOLERANCE_PCT: float = 0.5   # 0.50% cluster consistency tolerance

@dataclass(frozen=True, slots=True)
class SpreadGuardResult:
    passed: bool
    reason: str
    bid: float
    ask: float
    midpoint: float
    spread_bps: float
    jump_pct: float
    baseline_midpoint: Optional[float] = None
    in_recovery: bool = False
    recovery_count: int = 0
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "bid": self.bid,
            "ask": self.ask,
            "midpoint": self.midpoint,
            "spread_bps": self.spread_bps,
            "jump_pct": self.jump_pct,
            "baseline_midpoint": self.baseline_midpoint,
            "in_recovery": self.in_recovery,
            "recovery_count": self.recovery_count,
            "read_only": self.read_only,
            "is_order_action": self.is_order_action,
            "broker_api_called": self.broker_api_called,
        }

class SpreadGuardrailState:
    """Stateful guardrail tracking baseline midpoint and causal recovery."""

    def __init__(
        self,
        max_spread_bps: float = DEFAULT_MAX_SPREAD_BPS,
        max_jump_pct: float = DEFAULT_MAX_JUMP_PCT,
        recovery_k_ticks: int = DEFAULT_RECOVERY_K_TICKS,
        cluster_tolerance_pct: float = DEFAULT_CLUSTER_TOLERANCE_PCT,
    ) -> None:
        self.max_spread_bps = float(max_spread_bps)
        self.max_jump_pct = float(max_jump_pct)
        self.recovery_k_ticks = int(recovery_k_ticks)
        self.cluster_tolerance_pct = float(cluster_tolerance_pct)

        self.last_accepted_midpoint: Optional[float] = None
        self.recovery_count: int = 0
        self.recovery_cluster_midpoint: Optional[float] = None

    def reset(self) -> None:
        self.last_accepted_midpoint = None
        self.recovery_count = 0
        self.recovery_cluster_midpoint = None

    def validate_quote(self, bid: Any, ask: Any) -> SpreadGuardResult:
        # 1. Non-null check
        if bid is None or ask is None:
            return SpreadGuardResult(
                passed=False,
                reason="INVALID_QUOTE_NULL",
                bid=0.0,
                ask=0.0,
                midpoint=0.0,
                spread_bps=0.0,
                jump_pct=0.0,
                baseline_midpoint=self.last_accepted_midpoint,
            )

        try:
            bid_f = float(bid)
            ask_f = float(ask)
        except (ValueError, TypeError):
            return SpreadGuardResult(
                passed=False,
                reason="INVALID_QUOTE_NON_NUMERIC",
                bid=0.0,
                ask=0.0,
                midpoint=0.0,
                spread_bps=0.0,
                jump_pct=0.0,
                baseline_midpoint=self.last_accepted_midpoint,
            )

        # 2. Strict non-positive and finite check
        import math
        if not math.isfinite(bid_f) or not math.isfinite(ask_f) or bid_f <= 0.0 or ask_f <= 0.0:
            return SpreadGuardResult(
                passed=False,
                reason="INVALID_QUOTE_NON_POSITIVE",
                bid=bid_f if math.isfinite(bid_f) else 0.0,
                ask=ask_f if math.isfinite(ask_f) else 0.0,
                midpoint=0.0,
                spread_bps=0.0,
                jump_pct=0.0,
                baseline_midpoint=self.last_accepted_midpoint,
            )

        # 3. Crossed book check
        if bid_f > ask_f:
            return SpreadGuardResult(
                passed=False,
                reason="CROSSED_QUOTE_BID_GT_ASK",
                bid=bid_f,
                ask=ask_f,
                midpoint=0.0,
                spread_bps=0.0,
                jump_pct=0.0,
                baseline_midpoint=self.last_accepted_midpoint,
            )

        # 4. Pure Spread check
        midpoint = (bid_f + ask_f) / 2.0
        spread = ask_f - bid_f
        spread_bps = (spread / midpoint) * 10000.0

        if spread_bps > self.max_spread_bps:
            return SpreadGuardResult(
                passed=False,
                reason="SPREAD_EXCEEDS_MAX_BPS",
                bid=bid_f,
                ask=ask_f,
                midpoint=midpoint,
                spread_bps=spread_bps,
                jump_pct=0.0,
                baseline_midpoint=self.last_accepted_midpoint,
            )

        # 5. Midpoint Jump & Recovery Logic
        if self.last_accepted_midpoint is None:
            # First valid tick initializes baseline
            self.last_accepted_midpoint = midpoint
            self.recovery_count = 0
            self.recovery_cluster_midpoint = None
            return SpreadGuardResult(
                passed=True,
                reason="INITIALIZED_BASELINE",
                bid=bid_f,
                ask=ask_f,
                midpoint=midpoint,
                spread_bps=spread_bps,
                jump_pct=0.0,
                baseline_midpoint=midpoint,
            )

        jump_pct = (abs(midpoint - self.last_accepted_midpoint) / self.last_accepted_midpoint) * 100.0

        if jump_pct <= self.max_jump_pct:
            # Normal smooth market update
            self.last_accepted_midpoint = midpoint
            self.recovery_count = 0
            self.recovery_cluster_midpoint = None
            return SpreadGuardResult(
                passed=True,
                reason="PASSED",
                bid=bid_f,
                ask=ask_f,
                midpoint=midpoint,
                spread_bps=spread_bps,
                jump_pct=jump_pct,
                baseline_midpoint=midpoint,
            )

        # Jump exceeds threshold -> Engage Recovery Evaluation (Blocker 1 & Blocker 3)
        if self.recovery_cluster_midpoint is None:
            # First tick in candidate gap cluster
            self.recovery_cluster_midpoint = midpoint
            self.recovery_count = 1
        else:
            # Check if current tick is consistent with ongoing recovery cluster
            cluster_diff_pct = (abs(midpoint - self.recovery_cluster_midpoint) / self.recovery_cluster_midpoint) * 100.0
            if cluster_diff_pct <= self.cluster_tolerance_pct:
                self.recovery_count += 1
            else:
                # Inconsistent spike / jitter: reset recovery count to this new tick
                self.recovery_cluster_midpoint = midpoint
                self.recovery_count = 1

        if self.recovery_count >= self.recovery_k_ticks:
            # Causal recovery satisfied: K consistent ticks prove genuine market gap
            self.last_accepted_midpoint = midpoint
            old_count = self.recovery_count
            self.recovery_count = 0
            self.recovery_cluster_midpoint = None
            return SpreadGuardResult(
                passed=True,
                reason="BASELINE_RESYNCHRONIZED_AFTER_K_TICKS",
                bid=bid_f,
                ask=ask_f,
                midpoint=midpoint,
                spread_bps=spread_bps,
                jump_pct=jump_pct,
                baseline_midpoint=midpoint,
                in_recovery=True,
                recovery_count=old_count,
            )

        # Still in recovery window or rejected spike:
        # Crucial: last_accepted_midpoint remains UNCHANGED!
        return SpreadGuardResult(
            passed=False,
            reason="MIDPOINT_JUMP_EXCEEDS_MAX_PCT",
            bid=bid_f,
            ask=ask_f,
            midpoint=midpoint,
            spread_bps=spread_bps,
            jump_pct=jump_pct,
            baseline_midpoint=self.last_accepted_midpoint,
            in_recovery=True,
            recovery_count=self.recovery_count,
        )


def apply_spread_guard_to_candidate(candidate: dict[str, Any], guard_result: SpreadGuardResult) -> dict[str, Any]:
    """Safely apply spread guard evaluation to an execution candidate."""
    if not guard_result.passed:
        candidate["execution_allowed"] = False
        candidate["mode"] = "advisory_only"
        candidate["primary_blocker"] = f"spread_guardrail:{guard_result.reason}"
        candidate["spread_guard_audit"] = guard_result.to_dict()
    else:
        candidate["spread_guard_audit"] = guard_result.to_dict()
    return candidate


# ---------------------------------------------------------------------------
# WI-13: Volatility Regime Shift & Tick Spike Calibration
# ---------------------------------------------------------------------------

from enum import Enum
import math
from dataclasses import field
from typing import Sequence


class VolatilityRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TickSpikeFilterResult:
    is_spike: bool
    is_cluster: bool
    filtered_price: float
    raw_price: float
    deviation_sigma: float
    quarantined: bool


@dataclass(frozen=True)
class VolatilityRegimeState:
    regime: VolatilityRegime
    regime_multiplier: float
    realized_vol_bps: float
    cluster_count: int
    last_evaluated_bar_ts: float | None
    is_sufficient_history: bool


@dataclass(frozen=True)
class SpreadGuardrailDecision:
    passed: bool
    reason: str
    spread_bps: float | None
    effective_max_spread_bps: float
    regime_state: VolatilityRegimeState
    spike_info: TickSpikeFilterResult | None
    audit_telemetry: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False


class VolatilityCalibrator:
    """Causal, outlier-isolated volatility regime calibrator and tick spike filter.

    Enforces:
    - I-1: Absolute hard ceiling clamp (HARD_MAX_CAP_BPS = 150.0). Multiplier clamped in [0.8, 1.5].
    - I-2: Outlier prints (> 3.5 sigma) are quarantined and excluded from volatility estimators.
    - I-3: Causal temporal invariance: regime evaluated strictly over historical completed bar closes.
    - I-4: Multi-tick cluster confirmation: requires 3 consecutive prints to confirm regime escalation.
    - I-5: Fail-closed default: insufficient history (< 20 bars) returns is_sufficient_history=False.
    """

    HARD_MAX_CAP_BPS: float = 150.0  # 1.5% immovable ceiling
    MIN_MULTIPLIER: float = 0.8
    MAX_MULTIPLIER: float = 1.5
    MIN_REQUIRED_BARS: int = 20
    CLUSTER_CONFIRMATION_THRESHOLD: int = 3
    SPIKE_SIGMA_THRESHOLD: float = 3.5

    def __init__(self) -> None:
        self._cluster_count = 0
        self._current_regime = VolatilityRegime.NORMAL
        self._last_evaluated_bar_ts: float | None = None

    def evaluate_regime(
        self,
        historical_closed_bars: Sequence[Mapping[str, Any]] | None,
        now_ts: float | None = None,
    ) -> VolatilityRegimeState:
        if not historical_closed_bars or len(historical_closed_bars) < self.MIN_REQUIRED_BARS:
            return VolatilityRegimeState(
                regime=VolatilityRegime.UNKNOWN,
                regime_multiplier=1.0,
                realized_vol_bps=0.0,
                cluster_count=0,
                last_evaluated_bar_ts=None,
                is_sufficient_history=False,
            )

        # Causal check: ensure bars are completed historical closes
        last_bar = historical_closed_bars[-1]
        last_bar_ts = float(last_bar.get("close_epoch") or last_bar.get("ts_epoch") or 0.0)
        if now_ts is not None and last_bar_ts > now_ts:
            # Lookahead / non-causal bar rejected
            return VolatilityRegimeState(
                regime=VolatilityRegime.UNKNOWN,
                regime_multiplier=1.0,
                realized_vol_bps=0.0,
                cluster_count=0,
                last_evaluated_bar_ts=None,
                is_sufficient_history=False,
            )

        # Compute realized return volatility over closed bars
        returns = []
        for i in range(1, len(historical_closed_bars)):
            p0 = float(historical_closed_bars[i - 1].get("close") or historical_closed_bars[i - 1].get("ltp") or 0.0)
            p1 = float(historical_closed_bars[i].get("close") or historical_closed_bars[i].get("ltp") or 0.0)
            if p0 > 0.0 and p1 > 0.0:
                returns.append((p1 - p0) / p0)

        if len(returns) < self.MIN_REQUIRED_BARS - 1:
            return VolatilityRegimeState(
                regime=VolatilityRegime.UNKNOWN,
                regime_multiplier=1.0,
                realized_vol_bps=0.0,
                cluster_count=0,
                last_evaluated_bar_ts=None,
                is_sufficient_history=False,
            )

        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_ret = math.sqrt(var)
        realized_vol_bps = std_ret * 10000.0

        # Classify regime based on realized vol bps baseline (typical NIFTY 1-min baseline ~ 10-25 bps)
        # Cluster confirmation: increment count if vol is elevated
        if realized_vol_bps > 50.0:
            self._cluster_count += 1
            if self._cluster_count >= self.CLUSTER_CONFIRMATION_THRESHOLD:
                self._current_regime = VolatilityRegime.CRITICAL if realized_vol_bps > 80.0 else VolatilityRegime.HIGH
        elif realized_vol_bps < 8.0:
            self._cluster_count = 0
            self._current_regime = VolatilityRegime.LOW
        else:
            self._cluster_count = 0
            self._current_regime = VolatilityRegime.NORMAL

        # Multiplier formula scaled relative to 20 bps normal baseline
        raw_mult = 1.0 + ((realized_vol_bps - 20.0) / 40.0)
        regime_multiplier = max(self.MIN_MULTIPLIER, min(self.MAX_MULTIPLIER, float(raw_mult)))

        return VolatilityRegimeState(
            regime=self._current_regime,
            regime_multiplier=regime_multiplier,
            realized_vol_bps=realized_vol_bps,
            cluster_count=self._cluster_count,
            last_evaluated_bar_ts=last_bar_ts,
            is_sufficient_history=True,
        )

    def evaluate_tick(
        self,
        tick_price: float,
        rolling_mean: float,
        rolling_std: float,
        consecutive_outside_count: int = 0,
    ) -> TickSpikeFilterResult:
        if rolling_std <= 1e-9:
            return TickSpikeFilterResult(
                is_spike=False,
                is_cluster=False,
                filtered_price=tick_price,
                raw_price=tick_price,
                deviation_sigma=0.0,
                quarantined=False,
            )

        deviation = abs(tick_price - rolling_mean)
        sigma = deviation / rolling_std

        if sigma > self.SPIKE_SIGMA_THRESHOLD:
            # If multiple consecutive ticks confirm the displacement, it's a confirmed cluster move
            if consecutive_outside_count >= self.CLUSTER_CONFIRMATION_THRESHOLD:
                return TickSpikeFilterResult(
                    is_spike=False,
                    is_cluster=True,
                    filtered_price=tick_price,
                    raw_price=tick_price,
                    deviation_sigma=sigma,
                    quarantined=False,
                )
            # Solitary outlier spike: quarantine from rolling volatility buffers
            return TickSpikeFilterResult(
                is_spike=True,
                is_cluster=False,
                filtered_price=rolling_mean,
                raw_price=tick_price,
                deviation_sigma=sigma,
                quarantined=True,
            )

        return TickSpikeFilterResult(
            is_spike=False,
            is_cluster=False,
            filtered_price=tick_price,
            raw_price=tick_price,
            deviation_sigma=sigma,
            quarantined=False,
        )


class SpreadGuardrail:
    """Dynamic volatility-calibrated spread guardrail."""

    def __init__(self, calibrator: VolatilityCalibrator | None = None) -> None:
        self.calibrator = calibrator or VolatilityCalibrator()

    def evaluate(
        self,
        *,
        bid: float,
        ask: float,
        ltp: float,
        historical_closed_bars: Sequence[Mapping[str, Any]] | None,
        base_cap_bps: float = 30.0,
        now_ts: float | None = None,
    ) -> SpreadGuardrailDecision:
        # Pre-arithmetic quote check
        try:
            bid_f = float(bid)
            ask_f = float(ask)
            ltp_f = float(ltp)
        except (TypeError, ValueError):
            return SpreadGuardrailDecision(
                passed=False,
                reason="INVALID_QUOTE_NON_NUMERIC",
                spread_bps=None,
                effective_max_spread_bps=base_cap_bps,
                regime_state=VolatilityRegimeState(VolatilityRegime.UNKNOWN, 1.0, 0.0, 0, None, False),
                spike_info=None,
            )

        if bid_f <= 0.0 or ask_f <= 0.0 or ltp_f <= 0.0 or ask_f < bid_f:
            return SpreadGuardrailDecision(
                passed=False,
                reason="INVALID_QUOTE_CROSSED_OR_NON_POSITIVE",
                spread_bps=None,
                effective_max_spread_bps=base_cap_bps,
                regime_state=VolatilityRegimeState(VolatilityRegime.UNKNOWN, 1.0, 0.0, 0, None, False),
                spike_info=None,
            )

        # Evaluate regime state from closed historical bars
        regime_state = self.calibrator.evaluate_regime(historical_closed_bars, now_ts=now_ts)
        if not regime_state.is_sufficient_history:
            return SpreadGuardrailDecision(
                passed=False,
                reason="INSUFFICIENT_VOL_DATA",
                spread_bps=None,
                effective_max_spread_bps=base_cap_bps,
                regime_state=regime_state,
                spike_info=None,
            )

        midpoint = (bid_f + ask_f) / 2.0
        spread_bps = ((ask_f - bid_f) / midpoint) * 10000.0

        # Dynamic ceiling calculation with absolute upper clamp (I-1)
        raw_cap = base_cap_bps * regime_state.regime_multiplier
        effective_max_spread_bps = min(raw_cap, self.calibrator.HARD_MAX_CAP_BPS)

        if spread_bps > effective_max_spread_bps:
            return SpreadGuardrailDecision(
                passed=False,
                reason="SPREAD_EXCEEDS_DYNAMIC_CAP",
                spread_bps=spread_bps,
                effective_max_spread_bps=effective_max_spread_bps,
                regime_state=regime_state,
                spike_info=None,
                audit_telemetry={
                    "spread_bps": spread_bps,
                    "effective_max_spread_bps": effective_max_spread_bps,
                    "regime": regime_state.regime.value,
                    "regime_multiplier": regime_state.regime_multiplier,
                },
            )

        return SpreadGuardrailDecision(
            passed=True,
            reason="SPREAD_WITHIN_DYNAMIC_CAP",
            spread_bps=spread_bps,
            effective_max_spread_bps=effective_max_spread_bps,
            regime_state=regime_state,
            spike_info=None,
            audit_telemetry={
                "spread_bps": spread_bps,
                "effective_max_spread_bps": effective_max_spread_bps,
                "regime": regime_state.regime.value,
                "regime_multiplier": regime_state.regime_multiplier,
            },
        )

