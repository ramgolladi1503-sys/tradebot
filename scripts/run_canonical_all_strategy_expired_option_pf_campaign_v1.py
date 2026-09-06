#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    sha256_file,
)
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.canonical_intent_campaign import (
    CanonicalIntentPolicy,
)
from scripts.run_canonical_option_intent_campaign_v1 import (
    run_campaign as run_intent_campaign,
)
from scripts.run_expired_option_contract_replay_v1 import run as run_option_replay


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_root = Path(args.output_root).resolve()
    intent_output = output_root / "canonical_intents"
    replay_output = output_root / "option_replay"
    output_root.mkdir(parents=True, exist_ok=True)

    intent_manifest = run_intent_campaign(
        Path(args.kite_replay_root).resolve(strict=True),
        intent_output,
        underlyings=("NIFTY",),
        policy=CanonicalIntentPolicy(
            minimum_completed_bars=args.minimum_completed_bars,
            max_intents_per_strategy_session=args.max_intents_per_strategy_session,
        ),
    )
    intents_csv = intent_output / "canonical_option_intents.csv"
    replay_manifest = run_option_replay(
        Namespace(
            option_source=args.option_source,
            intents_csv=str(intents_csv),
            output_root=str(replay_output),
            max_hold_minutes=args.max_hold_minutes,
            stop_loss_pct=args.stop_loss_pct,
            target_pct=args.target_pct,
            friction_bps_per_side=args.friction_bps_per_side,
            minimum_partition_trades=args.minimum_partition_trades,
            authorize_holdout=False,
        )
    )
    final_manifest = {
        "schema_version": "canonical_all_strategy_expired_option_pf_campaign_v1",
        "campaign": "CANONICAL_ALL_STRATEGY_EXPIRED_OPTION_PF_CAMPAIGN_V1",
        "canonical_intent_manifest": intent_manifest,
        "option_replay_manifest": replay_manifest,
        "canonical_intents_csv_sha256": sha256_file(intents_csv),
        "holdout_authorized": False,
        "holdout_outcomes_read": False,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "verdict": replay_manifest["verdict"],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(final_manifest, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return final_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-command canonical TradeBot strategy -> option intent -> real "
            "expired-option replay campaign. Holdout is always sealed."
        )
    )
    parser.add_argument(
        "--kite-replay-root",
        required=True,
        help="Existing Kite five-minute underlying replay corpus",
    )
    parser.add_argument(
        "--option-source",
        required=True,
        help="Upstox expired-option directory or ZIP archive",
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--minimum-completed-bars", type=int, default=2)
    parser.add_argument("--max-intents-per-strategy-session", type=int, default=1)
    parser.add_argument("--max-hold-minutes", type=int, default=30)
    parser.add_argument("--stop-loss-pct", type=float, default=0.25)
    parser.add_argument("--target-pct", type=float, default=0.375)
    parser.add_argument("--friction-bps-per-side", type=float, default=5.0)
    parser.add_argument("--minimum-partition-trades", type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
