from __future__ import annotations

import json
from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_7.ledger_builder import build_signal_ledgers
from research.option_e2e_recertification_v4.signal_ledgers_v4_7.strategy_source_registry import build_strategy_source_registry


def test_strategy_source_registry_contains_known_strategies() -> None:
    registry = build_strategy_source_registry()

    assert "VWAP_RECLAIM" in registry
    assert "OPENING_RANGE_BREAKOUT" in registry
    assert registry["NO_TRADE_CHOP"].directional_eligibility == "non_directional_or_helper"
    assert registry["VWAP_RECLAIM"].source_domain == "CURRENT_MASTER_DIAGNOSTIC"


def test_v4_7_builder_is_fail_closed_without_signal_artifacts(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "entities": [
                    {"id": "VWAP_RECLAIM", "counted_as_strategy": True},
                    {"id": "NO_TRADE_CHOP", "counted_as_strategy": True},
                ]
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    ledgers, summary, detail = build_signal_ledgers(tmp_path, inventory)

    assert ledgers == []
    assert summary["strategy_count"] == 0
    assert summary["oracle_verdict"] == "SIGNAL_LEDGER_NOT_CERTIFIED"
    assert detail["coverage"]["resolved"] == 0
    assert detail["coverage"]["blocked"] == 0
