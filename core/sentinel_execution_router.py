"""
Sentinel Index Execution Mode Router
====================================
Governs multi-index automated execution policies:
- NIFTY: Live Automated Execution (LIVE mode) when approved, or PAPER dry-run.
- SENSEX & BANKNIFTY: Exclusively PAPER / SIM mode (never LIVE).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any


class ExecutionMode(str, Enum):
    LIVE = "LIVE"
    PAPER = "PAPER"
    SIM = "SIM"


@dataclass
class IndexExecutionPolicy:
    index_name: str
    target_mode: ExecutionMode
    allowed_live: bool
    lot_size: int
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False


class SentinelExecutionRouter:
    """
    Directs trade intents based on index policies:
    - NIFTY is permitted for LIVE execution if system flag is enabled.
    - SENSEX and BANKNIFTY are strictly quarantined to PAPER / SIM mode.
    """

    def __init__(self, enable_nifty_live: bool = False):
        self.enable_nifty_live = enable_nifty_live
        self._policies: Dict[str, IndexExecutionPolicy] = {
            "NIFTY": IndexExecutionPolicy(
                index_name="NIFTY",
                target_mode=ExecutionMode.LIVE if enable_nifty_live else ExecutionMode.PAPER,
                allowed_live=enable_nifty_live,
                lot_size=65,
                read_only=not enable_nifty_live,
                is_order_action=enable_nifty_live,
            ),
            "BANKNIFTY": IndexExecutionPolicy(
                index_name="BANKNIFTY",
                target_mode=ExecutionMode.PAPER,
                allowed_live=False,  # Strictly forbidden for live execution
                lot_size=30,
                read_only=True,
                is_order_action=False,
            ),
            "SENSEX": IndexExecutionPolicy(
                index_name="SENSEX",
                target_mode=ExecutionMode.PAPER,
                allowed_live=False,  # Strictly forbidden for live execution
                lot_size=20,
                read_only=True,
                is_order_action=False,
            ),
        }

    def get_policy(self, index_name: str) -> IndexExecutionPolicy:
        norm = str(index_name or "").upper().strip()
        if norm == "BANKNIFTY" or norm.startswith(("BANKNIFTY ", "BANKNIFTY-", "BANKNIFTY_")):
            return self._policies["BANKNIFTY"]
        if norm == "SENSEX" or norm.startswith(("SENSEX ", "SENSEX-", "SENSEX_")):
            return self._policies["SENSEX"]
        if norm == "NIFTY":
            return self._policies["NIFTY"]
        # Unknown or missing instrument identity must never inherit NIFTY's
        # potentially live policy. Represent it as an explicit no-route.
        return IndexExecutionPolicy(
            index_name=norm or "UNKNOWN",
            target_mode=ExecutionMode.SIM,
            allowed_live=False,
            lot_size=0,
            read_only=True,
            is_order_action=False,
            broker_api_called=False,
        )

    def route_execution_intent(self, index_name: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Enforces mode stamping and live execution isolation."""
        policy = self.get_policy(index_name)
        routed = dict(intent)
        routed["index_name"] = policy.index_name
        routed["mode"] = policy.target_mode.value
        routed["lot_size"] = policy.lot_size
        routed["allowed_for_live"] = policy.allowed_live
        routed["route_valid"] = policy.lot_size > 0

        # Safety override: if not NIFTY, force mode to PAPER regardless of intent
        if policy.index_name in {"SENSEX", "BANKNIFTY"}:
            routed["mode"] = ExecutionMode.PAPER.value
            routed["allowed_for_live"] = False

        return routed
