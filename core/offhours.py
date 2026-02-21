"""Migration note:
Compatibility wrapper. Keep importing is_offhours from this module,
while delegating all logic to core.market_context.derive_market_context.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.market_context import derive_market_context


def is_offhours(snapshot_or_config: Mapping[str, Any] | Any = None) -> bool:
    return derive_market_context(snapshot_or_config).mode == "OFFHOURS"
