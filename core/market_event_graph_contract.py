"""Frozen Market Event Graph reversal contract.

This module is deliberately static: it contains only recovered research
constants and validation helpers. It does not discover, tune, fetch data, call a
broker, or authorize execution.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Mapping

STRATEGY_ID = "market_event_graph_reversal_v1"
DATASET_SHA256 = "30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c"
SOURCE_ARCHIVE_SHA256 = "fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3"
FROZEN_DISCOVERY_SPEC_SHA256 = "75432ed1c9e3be9172079dc003ea9da38f7065cdfd4ca46ebd9538d7f863f218"

FROZEN_GRAPH = (
    "breadth_down_1:HIGH",
    "index_breadth_divergence:LOW",
    "breadth_down_1:LOW",
)

FROZEN_THRESHOLDS = {
    "breadth_high": 0.21862348178137653,
    "breadth_low": 0.10121457489878542,
    "divergence_low": -0.000238836424541256,
    "min_constituents": 40,
}

SECONDARY_PE_THRESHOLDS = {
    "breadth_up_1_low": 0.09716599190283401,
    "volume_shock_share_high": 0.2793522267206478,
    "breadth_mean_ret1_low": -0.00019076586779298327,
}

CONTRACT_STATUS = (
    "EXACT_UNDERLYING_DISCOVERY_REPRODUCED",
    "NOT_OPTION_PREMIUM_VALIDATED",
    "NOT_INDEPENDENTLY_CERTIFIED",
    "SHADOW_ADVISORY_ONLY",
)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def thresholds_match_frozen(values: Mapping[str, Any]) -> bool:
    try:
        for key in ("breadth_high", "breadth_low", "divergence_low"):
            if not math.isclose(float(values[key]), FROZEN_THRESHOLDS[key], rel_tol=0.0, abs_tol=1e-15):
                return False
        if int(values.get("min_constituents", FROZEN_THRESHOLDS["min_constituents"])) != int(
            FROZEN_THRESHOLDS["min_constituents"]
        ):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def metadata_has_frozen_contract(metadata: Mapping[str, Any]) -> bool:
    return (
        str(metadata.get("market_event_graph_strategy_id") or "") == STRATEGY_ID
        and str(metadata.get("market_event_graph_dataset_sha256") or "") == DATASET_SHA256
        and str(metadata.get("market_event_graph_frozen_spec_sha256") or "")
        == FROZEN_DISCOVERY_SPEC_SHA256
    )


__all__ = [
    "CONTRACT_STATUS",
    "DATASET_SHA256",
    "FROZEN_DISCOVERY_SPEC_SHA256",
    "FROZEN_GRAPH",
    "FROZEN_THRESHOLDS",
    "SECONDARY_PE_THRESHOLDS",
    "SOURCE_ARCHIVE_SHA256",
    "STRATEGY_ID",
    "file_sha256",
    "metadata_has_frozen_contract",
    "thresholds_match_frozen",
]
