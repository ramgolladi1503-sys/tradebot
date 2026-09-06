#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.cross_sectional_diffusion_direction_v1.campaign import (
    CAMPAIGN_ID,
    add_forward_returns,
    build_feature_frame,
    load_membership,
    load_price_table,
    sha256_path,
    summarize_result,
)
from research.cross_sectional_diffusion_direction_v1.session_wfa import (
    SessionCampaignConfig,
    assess_session_terminal_verdict,
    run_session_walk_forward,
)

PRE_HOLDOUT_END = date(2026, 2, 26)
HOLDOUT_START = date(2026, 2, 27)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=CAMPAIGN_ID)
    p.add_argument("--index", required=True, help="NIFTY minute CSV/Parquet")
    p.add_argument("--constituents", required=True, help="Long-format constituent minute CSV/Parquet or directory")
    p.add_argument("--membership", required=True, help="Historical membership/weights CSV/Parquet")
    p.add_argument("--execution", required=True, help="Authoritative tradable execution series, preferably the frozen causal NIFTY futures panel")
    p.add_argument("--roundtrip-cost-bps", type=float, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--membership-authoritative", action="store_true")
    p.add_argument("--execution-authoritative", action="store_true")
    return p.parse_args()


def _pre_holdout(df):
    session_date = df["timestamp"].dt.tz_convert("Asia/Kolkata").dt.date
    return df[session_date <= PRE_HOLDOUT_END].copy()


def main() -> int:
    args = parse_args()
    if args.roundtrip_cost_bps <= 0:
        raise SystemExit("roundtrip cost must be > 0 bps")

    cfg = SessionCampaignConfig()
    index_all = load_price_table(args.index)
    constituents_all = load_price_table(args.constituents, require_symbol=True)
    membership = load_membership(args.membership)
    execution_all = load_price_table(args.execution)

    # V1.2 is deliberately pre-holdout only. The existing REC-MD HOLDOUT begins
    # 2026-02-27 and is not used to select, tune, or score this campaign here.
    index = _pre_holdout(index_all)
    constituents = _pre_holdout(constituents_all)
    execution = _pre_holdout(execution_all)
    if index.empty or constituents.empty or execution.empty:
        raise SystemExit("no pre-holdout data available through 2026-02-26")

    features = build_feature_frame(
        index,
        constituents,
        membership,
        lookback_minutes=cfg.lookback_minutes,
        min_coverage=cfg.min_coverage,
    )
    frame = add_forward_returns(
        features,
        execution,
        (cfg.primary_horizon_minutes, cfg.secondary_horizon_minutes),
    )

    results = {}
    for horizon in (cfg.primary_horizon_minutes, cfg.secondary_horizon_minutes):
        result = run_session_walk_forward(
            frame,
            horizon=horizon,
            cost_bps=args.roundtrip_cost_bps,
            cfg=cfg,
        )
        verdict, blockers = assess_session_terminal_verdict(
            result,
            cfg=cfg,
            membership_authoritative=args.membership_authoritative,
            execution_authoritative=args.execution_authoritative,
        )
        results[str(horizon)] = {
            **summarize_result(result),
            "verdict": verdict,
            "blockers": blockers,
        }

    primary = results[str(cfg.primary_horizon_minutes)]
    evaluated_min = str(min(frame["session"])) if not frame.empty else None
    evaluated_max = str(max(frame["session"])) if not frame.empty else None
    if evaluated_max is not None and date.fromisoformat(evaluated_max) >= HOLDOUT_START:
        raise RuntimeError("holdout_boundary_violation")

    payload = {
        "campaign_id": CAMPAIGN_ID,
        "spec_version": "1.2.0",
        "stage": "PRE_HOLDOUT_WALK_FORWARD",
        "evaluation_claim": "AFTER_COST_CANDLE_PROXY_NOT_EXACT_FILL_CERTIFICATION",
        "config_sha256": cfg.digest(),
        "primary_horizon_minutes": cfg.primary_horizon_minutes,
        "secondary_horizon_minutes": cfg.secondary_horizon_minutes,
        "roundtrip_cost_bps": args.roundtrip_cost_bps,
        "research_window": {
            "evaluated_min_session": evaluated_min,
            "evaluated_max_session": evaluated_max,
            "pre_holdout_end": str(PRE_HOLDOUT_END),
            "holdout_start": str(HOLDOUT_START),
            "holdout_evaluated": False,
        },
        "input_sha256": {
            "index": sha256_path(args.index),
            "constituents": sha256_path(args.constituents),
            "membership": sha256_path(args.membership),
            "execution": sha256_path(args.execution),
        },
        "membership_authoritative": bool(args.membership_authoritative),
        "execution_authoritative": bool(args.execution_authoritative),
        "primary_verdict": primary["verdict"],
        "primary_blockers": primary["blockers"],
        "results": results,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if primary["verdict"] == "PRE_HOLDOUT_DIRECTIONAL_SURVIVOR" else 2


if __name__ == "__main__":
    raise SystemExit(main())
