from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

REGIME_LABELS: tuple[str, ...] = (
    "TREND",
    "RANGE",
    "RANGE_VOLATILE",
    "EVENT",
    "PANIC",
)
PROBABILITY_SUM_TOLERANCE = 1e-5
HEURISTIC_LOGIT_SCALE = 6.0

VALID = "VALID"
UNCERTAIN = "UNCERTAIN"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
INVALID_INPUT = "INVALID_INPUT"


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def clamp(value: float, low: float, high: float) -> float:
    return max(float(low), min(float(high), float(value)))


def normalize_iv(value: Any) -> tuple[float | None, str | None]:
    """Return IV as a decimal fraction with explicit scale diagnostics."""
    raw = finite_float(value)
    if raw is None:
        return None, "iv_missing"
    if raw < 0.0:
        return None, "iv_negative"
    if raw <= 3.0:
        return raw, None
    if raw <= 300.0:
        return raw / 100.0, "iv_scaled_percent"
    return None, "iv_out_of_range"


def normalize_oi_delta(
    delta: Any,
    gross: Any = None,
    *,
    fallback_scale: float = 1_000_000.0,
) -> tuple[float, str]:
    """Bound OI evidence to [-1, 1]; raw OI must never dominate logits."""
    d = finite_float(delta)
    if d is None:
        return 0.0, "oi_missing"
    g = finite_float(gross)
    if g is not None and g > 0.0:
        return clamp(d / g, -1.0, 1.0), "oi_gross_ratio"
    scale = max(abs(float(fallback_scale)), 1.0)
    return math.tanh(d / scale), "oi_bounded_fallback"


def stable_softmax(scores: Mapping[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    clean: dict[str, float] = {}
    for label in REGIME_LABELS:
        value = finite_float(scores.get(label))
        if value is None:
            raise ValueError(f"non_finite_regime_score:{label}")
        clean[label] = value
    maximum = max(clean.values())
    exponentials = {
        label: math.exp(value - maximum) for label, value in clean.items()
    }
    denominator = sum(exponentials.values())
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("invalid_softmax_denominator")
    return {
        label: exponentials[label] / denominator for label in REGIME_LABELS
    }


def probability_diagnostics(
    probabilities: Mapping[str, Any],
) -> dict[str, Any]:
    if not probabilities:
        raise ValueError("empty_probability_vector")

    unknown_nonzero: list[str] = []
    for raw_label, raw_value in probabilities.items():
        label = str(raw_label)
        if label in REGIME_LABELS:
            continue
        value = finite_float(raw_value)
        if value is None:
            raise ValueError(f"non_finite_probability:{label}")
        if abs(value) > PROBABILITY_SUM_TOLERANCE:
            unknown_nonzero.append(label)
    if unknown_nonzero:
        raise ValueError(
            "unknown_probability_labels:" + ",".join(sorted(unknown_nonzero))
        )

    probs: dict[str, float] = {}
    for label in REGIME_LABELS:
        value = finite_float(probabilities.get(label, 0.0))
        if value is None:
            raise ValueError(f"non_finite_probability:{label}")
        if value < 0.0:
            raise ValueError(f"negative_probability:{label}")
        probs[label] = value

    total = sum(probs.values())
    if not math.isclose(
        total,
        1.0,
        abs_tol=PROBABILITY_SUM_TOLERANCE,
    ):
        raise ValueError(f"probabilities_do_not_sum_to_one:{total}")
    if total <= 0.0:
        raise ValueError("probability_sum_non_positive")

    # Existing runtime evidence may be rounded to six decimals. Accept only the
    # repository's established small tolerance, then renormalize before entropy.
    probs = {label: value / total for label, value in probs.items()}
    entropy = -sum(p * math.log(p) for p in probs.values() if p > 0.0)
    max_entropy = math.log(len(REGIME_LABELS))
    normalized = clamp(
        entropy / max_entropy if max_entropy else 0.0,
        0.0,
        1.0,
    )
    ordered = sorted(probs.items(), key=lambda item: (-item[1], item[0]))
    top_label, top_probability = ordered[0]
    second_label, second_probability = ordered[1]
    return {
        "probabilities": probs,
        "input_probability_sum": total,
        "entropy": entropy,
        "max_entropy": max_entropy,
        "normalized_entropy": normalized,
        "top_label": top_label,
        "top_probability": top_probability,
        "second_label": second_label,
        "second_probability": second_probability,
        "top_two_margin": top_probability - second_probability,
    }


def classify_entropy_state(
    normalized_entropy: float,
    threshold: float,
) -> str:
    value = clamp(normalized_entropy, 0.0, 1.0)
    limit = clamp(threshold, 0.0, 1.0)
    if value <= 0.35:
        return "LOW"
    if value <= limit:
        return "NORMAL"
    if value < 0.95:
        return "HIGH"
    return "EXTREME"


def build_feature_quality(features: Mapping[str, Any]) -> dict[str, Any]:
    # These are dimensionless or already normalized across index families.
    required = ("adx", "vol_z", "atr_pct")
    optional = (
        "vwap_slope",
        "vwap_slope_atr",
        "iv_mean",
        "ltp_acceleration",
        "ltp_acceleration_atr",
        "option_chain_skew",
        "oi_delta",
        "oi_gross",
        "depth_imbalance",
        "regime_transition_rate",
        "shock_score",
        "uncertainty_index",
        "macro_direction_bias",
        "x_regime_align",
        "x_vol_spillover",
        "x_lead_lag",
    )
    missing_required = [
        name for name in required if finite_float(features.get(name)) is None
    ]
    invalid_required: list[str] = []
    adx = finite_float(features.get("adx"))
    atr_pct = finite_float(features.get("atr_pct"))
    if adx is not None and adx < 0.0:
        invalid_required.append("adx_negative")
    if atr_pct is not None and atr_pct <= 0.0:
        invalid_required.append("atr_pct_non_positive")
    missing_optional = [
        name for name in optional if finite_float(features.get(name)) is None
    ]
    required_present = (
        len(required) - len(missing_required) - len(invalid_required)
    )
    coverage = clamp(required_present / len(required), 0.0, 1.0)
    if invalid_required:
        status = INVALID_INPUT
    elif missing_required:
        status = INSUFFICIENT_DATA
    else:
        status = VALID
    return {
        "status": status,
        "required_features": list(required),
        "missing_required": missing_required,
        "invalid_required": invalid_required,
        "missing_optional": missing_optional,
        "required_coverage": coverage,
    }


def _normalized_slope_strength(
    features: Mapping[str, Any],
) -> tuple[float, str]:
    explicit = finite_float(features.get("vwap_slope_atr"))
    if explicit is not None:
        return clamp(abs(explicit), 0.0, 1.0), "vwap_slope_atr"
    # Raw point slope is not cross-symbol comparable. It is deliberately
    # excluded until the caller supplies an ATR-normalized value.
    if finite_float(features.get("vwap_slope")) is not None:
        return 0.0, "raw_vwap_slope_ignored"
    return 0.0, "vwap_slope_missing"


def _normalized_acceleration_strength(
    features: Mapping[str, Any],
) -> tuple[float, str]:
    explicit = finite_float(features.get("ltp_acceleration_atr"))
    if explicit is not None:
        return clamp(abs(explicit), 0.0, 1.0), "ltp_acceleration_atr"
    # Raw point acceleration has the same cross-symbol scale problem.
    if finite_float(features.get("ltp_acceleration")) is not None:
        return 0.0, "raw_ltp_acceleration_ignored"
    return 0.0, "ltp_acceleration_missing"


def normalized_heuristic_scores(
    features: Mapping[str, Any],
) -> tuple[dict[str, float], dict[str, Any]]:
    """Build discriminative structural logits from bounded evidence.

    These are deterministic heuristic pseudo-probabilities, not statistically
    calibrated probabilities. Clear structural states should separate; mixed
    structural states should remain high entropy.
    """
    quality = build_feature_quality(features)
    if quality["status"] != VALID:
        return {}, quality

    adx = finite_float(features.get("adx")) or 0.0
    vol_z = finite_float(features.get("vol_z")) or 0.0
    atr_pct = finite_float(features.get("atr_pct")) or 0.0
    skew = finite_float(features.get("option_chain_skew")) or 0.0
    depth_imb = finite_float(features.get("depth_imbalance")) or 0.0
    transition_rate = (
        finite_float(features.get("regime_transition_rate")) or 0.0
    )
    shock_score = finite_float(features.get("shock_score")) or 0.0
    uncertainty = finite_float(features.get("uncertainty_index")) or 0.0
    macro_bias = finite_float(features.get("macro_direction_bias")) or 0.0
    x_align = finite_float(features.get("x_regime_align")) or 0.0
    x_volspill = finite_float(features.get("x_vol_spillover")) or 0.0
    x_lead = finite_float(features.get("x_lead_lag")) or 0.0

    iv_mean, iv_note = normalize_iv(features.get("iv_mean"))
    iv_mean = iv_mean or 0.0
    oi_normalized, oi_source = normalize_oi_delta(
        features.get("oi_delta"),
        features.get("oi_gross"),
    )
    slope_strength, slope_source = _normalized_slope_strength(features)
    acceleration_strength, acceleration_source = (
        _normalized_acceleration_strength(features)
    )

    adx_strength = clamp((adx - 15.0) / 20.0, 0.0, 1.0)
    range_strength = 1.0 - adx_strength
    volatility_strength = clamp((vol_z + 0.5) / 2.5, 0.0, 1.0)
    atr_strength = clamp((atr_pct - 0.002) / 0.010, 0.0, 1.0)
    iv_strength = clamp((iv_mean - 0.12) / 0.40, 0.0, 1.0)
    shock_strength = clamp(shock_score, 0.0, 1.0)
    uncertainty_strength = clamp(uncertainty, 0.0, 1.0)
    transition_strength = clamp(transition_rate / 8.0, 0.0, 1.0)
    depth_strength = clamp(abs(depth_imb), 0.0, 1.0)
    oi_strength = clamp(abs(oi_normalized), 0.0, 1.0)
    positive_alignment = clamp(x_align, 0.0, 1.0)
    volatility_spillover = clamp(x_volspill / 1.5, 0.0, 1.0)
    lead_lag_strength = clamp(abs(x_lead), 0.0, 1.0)
    macro_strength = clamp(abs(macro_bias), 0.0, 1.0)

    panic_interaction = (
        shock_strength * volatility_strength * atr_strength
    )
    supports = {
        "TREND": (
            0.50 * adx_strength
            + 0.15 * atr_strength
            + 0.10 * oi_strength
            + 0.10 * depth_strength
            + 0.10 * positive_alignment
            + 0.05 * slope_strength
            - 0.15 * shock_strength
        ),
        "RANGE": (
            0.60 * range_strength
            + 0.20 * (1.0 - volatility_strength)
            + 0.20 * (1.0 - atr_strength)
            - 0.25 * shock_strength
        ),
        "RANGE_VOLATILE": (
            0.35 * range_strength
            + 0.35 * volatility_strength
            + 0.25 * atr_strength
            + 0.05 * volatility_spillover
            - 0.20 * shock_strength
        ),
        "EVENT": (
            0.35 * shock_strength
            + 0.20 * uncertainty_strength
            + 0.20 * iv_strength
            + 0.15 * volatility_strength
            + 0.10 * atr_strength
            - 0.12 * transition_strength
            - 0.08 * acceleration_strength
        ),
        "PANIC": (
            0.30 * shock_strength
            + 0.15 * volatility_strength
            + 0.10 * atr_strength
            + 0.15 * transition_strength
            + 0.10 * acceleration_strength
            + 0.10 * lead_lag_strength
            + 0.05 * macro_strength
            + 0.05 * volatility_spillover
            + 0.20 * panic_interaction
        ),
    }
    logits = {
        label: HEURISTIC_LOGIT_SCALE * (support - 0.50)
        for label, support in supports.items()
    }

    quality = dict(quality)
    quality["normalization"] = {
        "oi_source": oi_source,
        "oi_normalized": oi_normalized,
        "iv_note": iv_note,
        "iv_decimal": iv_mean,
        "slope_source": slope_source,
        "acceleration_source": acceleration_source,
    }
    quality["bounded_components"] = {
        "adx_strength": adx_strength,
        "range_strength": range_strength,
        "volatility_strength": volatility_strength,
        "atr_strength": atr_strength,
        "iv_strength": iv_strength,
        "shock_strength": shock_strength,
        "uncertainty_strength": uncertainty_strength,
        "transition_strength": transition_strength,
        "depth_strength": depth_strength,
        "oi_strength": oi_strength,
        "slope_strength": slope_strength,
        "acceleration_strength": acceleration_strength,
    }
    quality["structural_supports"] = supports
    quality["heuristic_logit_scale"] = HEURISTIC_LOGIT_SCALE
    quality["probability_calibrated"] = False
    quality["probability_semantics"] = "deterministic_structural_pseudo_probability"
    quality["ignored_unscaled_inputs"] = [
        name
        for name, source in (
            ("vwap_slope", slope_source),
            ("ltp_acceleration", acceleration_source),
        )
        if source.startswith("raw_")
    ]
    return logits, quality


@dataclass
class RegimeStabilizer:
    confirmation_bars: int = 3
    minimum_dwell_bars: int = 2
    fast_event_probability: float = 0.80
    stable_regime_by_symbol: dict[str, str] = field(default_factory=dict)
    candidate_regime_by_symbol: dict[str, str] = field(default_factory=dict)
    candidate_count_by_symbol: dict[str, int] = field(default_factory=dict)
    dwell_by_symbol: dict[str, int] = field(default_factory=dict)
    last_bar_by_symbol: dict[str, Any] = field(default_factory=dict)

    def update(
        self,
        *,
        symbol: str,
        completed_bar: Any,
        instantaneous_regime: str,
        top_probability: float,
        status: str,
    ) -> dict[str, Any]:
        key = str(symbol or "UNKNOWN").upper()
        if completed_bar is None:
            return self.snapshot(key, reason="missing_completed_bar")
        if self.last_bar_by_symbol.get(key) == completed_bar:
            return self.snapshot(key, reason="duplicate_completed_bar")
        self.last_bar_by_symbol[key] = completed_bar

        stable = self.stable_regime_by_symbol.get(key)
        if status != VALID or instantaneous_regime not in REGIME_LABELS:
            if stable:
                self.dwell_by_symbol[key] = (
                    self.dwell_by_symbol.get(key, 0) + 1
                )
            return self.snapshot(
                key,
                reason="non_valid_instantaneous_state",
            )

        fast_path = (
            instantaneous_regime in {"EVENT", "PANIC"}
            and top_probability >= self.fast_event_probability
        )
        if stable is None:
            required = 1 if fast_path else max(1, self.confirmation_bars)
        elif stable == instantaneous_regime:
            self.dwell_by_symbol[key] = self.dwell_by_symbol.get(key, 0) + 1
            self.candidate_regime_by_symbol.pop(key, None)
            self.candidate_count_by_symbol.pop(key, None)
            return self.snapshot(key, reason="stable_regime_confirmed")
        else:
            required = 1 if fast_path else max(1, self.confirmation_bars)
            if self.dwell_by_symbol.get(key, 0) < max(
                0,
                self.minimum_dwell_bars,
            ):
                required += 1

        if self.candidate_regime_by_symbol.get(key) == instantaneous_regime:
            count = self.candidate_count_by_symbol.get(key, 0) + 1
        else:
            self.candidate_regime_by_symbol[key] = instantaneous_regime
            count = 1
        self.candidate_count_by_symbol[key] = count

        if count >= required:
            self.stable_regime_by_symbol[key] = instantaneous_regime
            self.dwell_by_symbol[key] = 1
            self.candidate_regime_by_symbol.pop(key, None)
            self.candidate_count_by_symbol.pop(key, None)
            return self.snapshot(key, reason="stable_regime_transition")
        if stable:
            self.dwell_by_symbol[key] = self.dwell_by_symbol.get(key, 0) + 1
        return self.snapshot(key, reason="transition_pending")

    def snapshot(self, symbol: str, *, reason: str) -> dict[str, Any]:
        key = str(symbol or "UNKNOWN").upper()
        return {
            "stable_regime": self.stable_regime_by_symbol.get(
                key,
                "UNKNOWN",
            ),
            "transition_candidate": self.candidate_regime_by_symbol.get(key),
            "transition_confirmation_count": self.candidate_count_by_symbol.get(
                key,
                0,
            ),
            "dwell_bars": self.dwell_by_symbol.get(key, 0),
            "last_completed_bar": self.last_bar_by_symbol.get(key),
            "reason": reason,
        }
