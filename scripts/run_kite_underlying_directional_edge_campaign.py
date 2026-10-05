#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    canonical_json,
)
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.canonical_adapter import (
    CANONICAL_STRATEGIES,
)
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.canonical_intent_campaign import (
    CanonicalIntentPolicy,
)
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.underlying_corpus import (
    UNDERLYINGS,
    audit_corpus,
    build_partitions,
)
from scripts.run_canonical_option_intent_campaign_v1 import (
    run_campaign as run_canonical_intent_campaign,
)

STRATEGIES = tuple(sorted(CANONICAL_STRATEGIES))


def generate_signals(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    raise RuntimeError(
        "proxy_signal_generation_removed_use_canonical_strategy_owners"
    )


def _simulate_signal(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(
        "proxy_directional_pnl_removed_use_real_option_contract_replay"
    )


def _intent_rows(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    raise RuntimeError(
        "proxy_intent_conversion_removed_use_canonical_intent_campaign"
    )


def _controls(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(
        "proxy_directional_controls_removed_use_option_replay_controls"
    )


def run_campaign(kite_root: Path, output_root: Path) -> dict[str, Any]:
    """Compatibility entrypoint; emits canonical intents and no proxy P&L."""
    return run_canonical_intent_campaign(
        kite_root,
        output_root,
        underlyings=UNDERLYINGS,
        policy=CanonicalIntentPolicy(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compatibility wrapper for the repaired canonical underlying-to-option "
            "intent campaign. Local proxy strategy equations and proxy P&L are removed."
        )
    )
    parser.add_argument(
        "--kite-replay-root",
        type=Path,
        default=Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            "/Users/madhuram/tradebot-ml-evidence/"
            "kite-underlying-directional-edge-campaign-v1"
        ),
    )
    args = parser.parse_args()
    manifest = run_campaign(
        args.kite_replay_root.resolve(strict=True),
        args.output_root.resolve(),
    )
    print(
        canonical_json(
            {
                key: manifest[key]
                for key in (
                    "campaign",
                    "verdict",
                    "invocation_count",
                    "canonical_intent_count",
                    "holdout_outcomes_read",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
