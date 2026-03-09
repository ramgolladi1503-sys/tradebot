from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if out != out:  # NaN guard
        return None
    return out


def _normalize_features(features: Any) -> dict[str, Any]:
    if isinstance(features, Mapping):
        return dict(features)
    return {}


@dataclass(frozen=True)
class SignalResult:
    confidence: float | None
    features: dict[str, Any]
    direction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "features": dict(self.features),
            "direction": self.direction,
        }


def evaluate(
    snapshot: Mapping[str, Any] | None,
    signal_payload: Mapping[str, Any] | None = None,
) -> SignalResult:
    """
    Evaluate signal-only characteristics.
    This intentionally excludes execution constraints.
    """
    payload = dict(signal_payload or {})
    snap = dict(snapshot or {})
    features = _normalize_features(payload.get("features"))
    if not features and isinstance(payload.get("signals"), Mapping):
        features = dict(payload.get("signals") or {})

    confidence = _safe_float(payload.get("confidence"))
    if confidence is None:
        confidence = _safe_float(payload.get("rank_score"))
    if confidence is None and isinstance(features, Mapping):
        confidence = _safe_float(features.get("confidence"))

    direction = str(payload.get("direction") or "").strip().upper()
    if not direction:
        direction = str((snap.get("meta") or {}).get("direction") or "").strip().upper()
    if not direction:
        direction = "UNKNOWN"

    if "pattern_flags" not in features:
        pattern_flags = payload.get("pattern_flags")
        if isinstance(pattern_flags, list):
            features["pattern_flags"] = list(pattern_flags)
    if "rank_score" not in features and payload.get("rank_score") is not None:
        features["rank_score"] = payload.get("rank_score")

    return SignalResult(confidence=confidence, features=features, direction=direction)
