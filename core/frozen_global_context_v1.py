"""Read-only binding contract for the frozen Global Context V1 model.

This module deliberately does not train, refit, load, or promote a model. It
only validates metadata supplied by an evidence adapter against the locked V1
identity and feature contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence


FROZEN_GLOBAL_CONTEXT_V1_SHA256 = "d432566f5dc15b5f28d10c82879e0cb779ae306e102aab091d6251d9e167e17e"
FROZEN_GLOBAL_CONTEXT_V1_VERSION = "GLOBAL_CONTEXT_V1"


@dataclass(frozen=True)
class FrozenGlobalContextV1Binding:
    """Immutable evidence binding for one already-frozen V1 artifact."""

    model_sha256: str
    model_version: str
    feature_names: tuple[str, ...]
    refit: bool = False

    def validate(self, *, expected_features: Sequence[str]) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.model_sha256):
            raise ValueError("FROZEN_MODEL_SHA256_REQUIRED")
        if self.model_sha256 != FROZEN_GLOBAL_CONTEXT_V1_SHA256:
            raise ValueError("FROZEN_MODEL_SHA256_MISMATCH")
        if self.model_version != FROZEN_GLOBAL_CONTEXT_V1_VERSION:
            raise ValueError("FROZEN_MODEL_VERSION_MISMATCH")
        if self.refit:
            raise ValueError("FROZEN_MODEL_REFIT_FORBIDDEN")
        expected = tuple(expected_features)
        if self.feature_names != expected:
            raise ValueError("FROZEN_MODEL_FEATURE_DRIFT")


def binding_from_metadata(metadata: Mapping[str, object]) -> FrozenGlobalContextV1Binding:
    """Parse untrusted metadata without permitting defaults or silent drift."""

    features = metadata.get("feature_names")
    if not isinstance(features, (list, tuple)) or not all(isinstance(x, str) for x in features):
        raise ValueError("FROZEN_MODEL_FEATURES_REQUIRED")
    return FrozenGlobalContextV1Binding(
        model_sha256=str(metadata.get("model_sha256") or ""),
        model_version=str(metadata.get("model_version") or ""),
        feature_names=tuple(features),
        refit=metadata.get("refit") is True,
    )
