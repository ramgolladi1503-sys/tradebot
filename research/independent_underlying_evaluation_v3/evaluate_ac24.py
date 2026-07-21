from __future__ import annotations

from typing import Any

import pandas as pd

from research.prospective_structural_edge_v2.cycle5_failure_runner import ac24


HYPOTHESIS_ID = "AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION"
ALPHA = 0.006
SPECIFICATION_HASH = "81137922979a0497e16616ca0c596197c72b4ce1e28dfb153e81829f55f2934b"
PARAMETER_HASH = "532cacdebe2ed4909c9a32632d8cc04ede079a1e6fe02ba8b2876e1393172935"
GENERATOR_SEMANTIC_HASH = "4be001a9b7acf482235e90db389e9fd0fd4c0199ed68f8645e8f182b493b2d5f"


def generate(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> tuple[list[Any], list[str]]:
    return ac24(session, data, prior)
