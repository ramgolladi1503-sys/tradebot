from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from core.regime_contract_v2 import (
    INSUFFICIENT_DATA,
    INVALID_INPUT,
    REGIME_LABELS,
    UNCERTAIN,
    VALID,
    normalized_heuristic_scores,
    probability_diagnostics,
    stable_softmax,
)
from core.regime_session_context import resolve_canonical_session_context

REGIMES = list(REGIME_LABELS)


class RegimeProbModel:
    """Regime model with bounded evidence and explicit provenance."""

    def __init__(self, model_path: str | None = None):
        self.model_path = (
            Path(model_path) if model_path else Path("models/regime_model.json")
        )
        self.model: dict[str, Any] | None = None
        self.model_hash: str | None = None
        self.model_load_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.model_path.exists():
            self.model = None
            self.model_hash = None
            self.model_load_error = "model_file_missing"
            return
        try:
            raw = self.model_path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("model_payload_not_object")
            for key in ("priors", "means", "vars"):
                if not isinstance(payload.get(key), dict):
                    raise ValueError(f"model_schema_missing:{key}")
            self.model = payload
            self.model_hash = hashlib.sha256(raw).hexdigest()
            self.model_load_error = None
        except Exception as exc:
            self.model = None
            self.model_hash = None
            self.model_load_error = f"{type(exc).__name__}:{exc}"

    @staticmethod
    def _finite_features(
        features: Mapping[str, Any],
    ) -> tuple[dict[str, float], list[str]]:
        clean: dict[str, float] = {}
        ignored: list[str] = []
        for key, value in features.items():
            try:
                number = float(value)
            except (TypeError, ValueError):
                ignored.append(str(key))
                continue
            if not math.isfinite(number):
                ignored.append(str(key))
                continue
            clean[str(key)] = number
        return clean, ignored

    def _model_required_features(self) -> tuple[str, ...]:
        if not self.model:
            return ()
        explicit = self.model.get("feature_names")
        if isinstance(explicit, list):
            names = tuple(
                sorted(
                    {
                        str(name).strip()
                        for name in explicit
                        if str(name).strip()
                    }
                )
            )
            if names:
                return names

        means = self.model.get("means", {})
        variances = self.model.get("vars", {})
        common: set[str] | None = None
        for regime in REGIMES:
            regime_means = means.get(regime)
            regime_vars = variances.get(regime)
            if not isinstance(regime_means, dict) or not isinstance(
                regime_vars,
                dict,
            ):
                return ()
            keys = set(regime_means) & set(regime_vars)
            common = keys if common is None else common & keys
        return tuple(sorted(common or ()))

    def _gaussian_nb_proba(
        self,
        features: Mapping[str, Any],
    ) -> dict[str, float]:
        if not self.model:
            raise ValueError("gaussian_model_unavailable")
        clean, _ = self._finite_features(features)
        required = self._model_required_features()
        if not required:
            raise ValueError("model_feature_schema_empty")
        missing = [name for name in required if name not in clean]
        if missing:
            raise ValueError(
                "model_required_features_missing:" + ",".join(missing)
            )

        priors = self.model.get("priors", {})
        means = self.model.get("means", {})
        variances = self.model.get("vars", {})
        scores: dict[str, float] = {}
        for regime in REGIMES:
            prior = float(priors.get(regime, 0.0) or 0.0)
            if prior <= 0.0 or not math.isfinite(prior):
                raise ValueError(f"invalid_prior:{regime}")
            score = math.log(prior)
            regime_means = means.get(regime, {})
            regime_vars = variances.get(regime, {})
            for key in required:
                value = clean[key]
                mean = float(regime_means[key])
                variance = max(float(regime_vars[key]), 1e-6)
                if not math.isfinite(mean) or not math.isfinite(variance):
                    raise ValueError(
                        f"invalid_gaussian_parameter:{regime}:{key}"
                    )
                score += -0.5 * (
                    math.log(2.0 * math.pi * variance)
                    + ((value - mean) ** 2) / variance
                )
            scores[regime] = score
        return stable_softmax(scores)

    def _heuristic_proba(
        self,
        features: Mapping[str, Any],
    ) -> dict[str, float]:
        scores, quality = normalized_heuristic_scores(features)
        if quality.get("status") != VALID:
            return {regime: 1.0 / len(REGIMES) for regime in REGIMES}
        return stable_softmax(scores)

    def _resolve_session_bucket(self, features: Mapping[str, Any]) -> str:
        explicit = str(features.get("session_bucket") or "").strip().upper()
        if explicit:
            return explicit
        timestamp_keys = (
            "timestamp_ist",
            "timestamp",
            "ltp_ts_epoch",
            "quote_ts_epoch",
            "quote_ts",
            "candle_ts_epoch",
            "regime_ts",
        )
        for key in timestamp_keys:
            value = features.get(key)
            if value is None or value == "":
                continue
            context = resolve_canonical_session_context(
                value,
                segment=str(features.get("segment") or "NSE_FNO"),
                is_expiry_day=bool(features.get("is_expiry_day")),
                is_event_mode=bool(features.get("is_event_mode")),
            )
            return context.canonical_session_bucket
        return "DEFAULT"

    def predict(self, features: Mapping[str, Any]) -> dict[str, Any]:
        feature_payload = dict(features or {})
        session_bucket = self._resolve_session_bucket(feature_payload)
        model_source = (
            "GAUSSIAN_NB_JSON"
            if self.model
            else "HEURISTIC_STRUCTURAL_V2_UNCALIBRATED"
        )
        ignored_features: list[str] = []
        feature_quality: dict[str, Any]
        inference_error: str | None = None

        if self.model:
            clean, ignored_features = self._finite_features(feature_payload)
            required = self._model_required_features()
            missing_required = [
                name for name in required if name not in clean
            ]
            if not required:
                probabilities = {
                    regime: 1.0 / len(REGIMES) for regime in REGIMES
                }
                feature_quality = {
                    "status": INVALID_INPUT,
                    "required_features": [],
                    "missing_required": [],
                    "invalid_required": ["model_feature_schema_empty"],
                    "missing_optional": ignored_features,
                    "required_coverage": 0.0,
                    "probability_calibrated": False,
                }
            elif missing_required:
                probabilities = {
                    regime: 1.0 / len(REGIMES) for regime in REGIMES
                }
                feature_quality = {
                    "status": INSUFFICIENT_DATA,
                    "required_features": list(required),
                    "missing_required": missing_required,
                    "invalid_required": [],
                    "missing_optional": ignored_features,
                    "required_coverage": (
                        (len(required) - len(missing_required)) / len(required)
                    ),
                    "probability_calibrated": bool(
                        self.model.get("calibrated", False)
                    ),
                }
            else:
                try:
                    probabilities = self._gaussian_nb_proba(clean)
                    feature_quality = {
                        "status": VALID,
                        "required_features": list(required),
                        "missing_required": [],
                        "invalid_required": [],
                        "missing_optional": ignored_features,
                        "required_coverage": 1.0,
                        "probability_calibrated": bool(
                            self.model.get("calibrated", False)
                        ),
                    }
                except Exception as exc:
                    inference_error = f"{type(exc).__name__}:{exc}"
                    probabilities = {
                        regime: 1.0 / len(REGIMES) for regime in REGIMES
                    }
                    feature_quality = {
                        "status": INVALID_INPUT,
                        "required_features": list(required),
                        "missing_required": [],
                        "invalid_required": [
                            "gaussian_model_inference_failed"
                        ],
                        "missing_optional": ignored_features,
                        "required_coverage": 0.0,
                        "probability_calibrated": False,
                    }
        else:
            scores, feature_quality = normalized_heuristic_scores(
                feature_payload
            )
            if feature_quality.get("status") == VALID:
                probabilities = stable_softmax(scores)
            else:
                probabilities = {
                    regime: 1.0 / len(REGIMES) for regime in REGIMES
                }

        diagnostics = probability_diagnostics(probabilities)
        primary = (
            diagnostics["top_label"]
            if feature_quality.get("status") == VALID
            else "UNKNOWN"
        )

        from core.regime_entropy_gate import evaluate_regime_entropy_gate

        gate = evaluate_regime_entropy_gate(
            probabilities=probabilities,
            session_bucket=session_bucket,
            expiry_day=bool(feature_payload.get("is_expiry_day")),
            event_mode=bool(feature_payload.get("is_event_mode")),
            market_data={
                **feature_payload,
                "feature_quality_status": feature_quality.get("status"),
            },
            primary_regime=primary,
            regime_prob_max=diagnostics["top_probability"],
        )

        status = str(feature_quality.get("status") or INVALID_INPUT)
        if status == VALID and gate.get("uncertain"):
            status = UNCERTAIN

        probability_calibrated = bool(
            feature_quality.get("probability_calibrated", False)
        )
        probability_semantics = str(
            feature_quality.get("probability_semantics")
            or (
                "calibrated_model_probability"
                if probability_calibrated
                else "uncalibrated_model_probability"
            )
        )

        return {
            "regime_probs": probabilities,
            "primary_regime": primary,
            "regime_entropy": diagnostics["entropy"],
            "regime_entropy_normalized": diagnostics[
                "normalized_entropy"
            ],
            "regime_entropy_threshold": gate["threshold"],
            "regime_entropy_state": gate["entropy_state"],
            "regime_prob_max": diagnostics["top_probability"],
            "regime_prob_second": diagnostics["second_probability"],
            "regime_top_two_margin": diagnostics["top_two_margin"],
            "unstable_regime_flag": status != VALID,
            "market_regime_uncertain": status != VALID,
            "regime_status": status,
            "feature_quality": feature_quality,
            "model_source": model_source,
            "model_path": str(self.model_path),
            "model_hash": self.model_hash,
            "model_load_error": self.model_load_error,
            "model_inference_error": inference_error,
            "ignored_features": ignored_features,
            "probability_calibrated": probability_calibrated,
            "probability_semantics": probability_semantics,
            "session_bucket": session_bucket,
            "entropy_gate": gate,
        }


def _softmax(scores: Mapping[str, float]) -> dict[str, float]:
    """Backward-compatible export with full-precision probabilities."""
    return stable_softmax(scores)
