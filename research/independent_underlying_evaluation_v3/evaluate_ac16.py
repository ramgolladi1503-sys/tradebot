from __future__ import annotations

from typing import Any

import pandas as pd

from research.prospective_structural_edge_v2.cycle4_underlying_runner import ac16_generate


HYPOTHESIS_ID = "AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION"
ALPHA = 0.004
SPECIFICATION_HASH = "2064343bc20abe841ba23591683afa041e8f67dda864721746a1f49af475062f"
PARAMETER_HASH = "96962f33f660a0f6927b860b475ac2c595bc62cd7e156e9ad6bfc1816052bc98"
GENERATOR_SEMANTIC_HASH = "6b9419ca1b631492f78d3e0965046e78f0574c601aab432af1cc7068bea4d596"


def generate(session: str, data: dict[str, pd.DataFrame], prior: dict[str, pd.DataFrame] | None) -> tuple[list[Any], list[str]]:
    return ac16_generate(session, data, prior)
