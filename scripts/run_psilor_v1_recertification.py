#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.psilor_v1 import (
    PSILORError,
    assert_precomputed_outcome_reconciles,
    audit_bar_horizon,
    build_elapsed_time_trade,
    current_drive_option_schema_assessment,
    reconcile_long_return,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def calibration_evidence() -> dict:
    one_minute = pd.date_range(
        "2026-08-05T09:15:00Z",
        periods=20,
        freq="1min",
    )
    five_minute = pd.date_range(
        one_minute[-1] + pd.Timedelta(minutes=5),
        periods=20,
        freq="5min",
    )
    mixed = pd.DataFrame(
        {"timestamp": list(one_minute) + list(five_minute)}
    )
    horizon_audit = audit_bar_horizon(mixed, horizon_bars=15)

    trade_frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-08-05T09:15:00Z",
                periods=5,
                freq="5min",
            ),
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
        }
    )
    trade = build_elapsed_time_trade(
        trade_frame,
        signal_timestamp=trade_frame.loc[0, "timestamp"],
        entry_delay_seconds=1,
        hold_seconds=10 * 60,
    )
    mismatch_detected = False
    try:
        assert_precomputed_outcome_reconciles(0.50, trade)
    except PSILORError:
        mismatch_detected = True

    gross, net = reconcile_long_return(
        entry_price=105.0,
        exit_price=95.0,
        round_trip_cost_fraction=0.0,
    )
    return {
        "mixed_bar_horizon_audit": horizon_audit,
        "elapsed_trade": trade.to_dict(),
        "precomputed_outcome_mismatch_detected": mismatch_detected,
        "ltp_spread_trap_fixture": {
            "fake_ltp_return": 110.0 / 105.0 - 1.0,
            "executable_bid_exit_gross_return": gross,
            "executable_bid_exit_net_return": net,
            "passed": gross < 0.0 and net < 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="runtime/research/psilor_v1/readiness.json",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    spec_path = root / "research/psilor_v1/spec.json"
    specification = json.loads(spec_path.read_text(encoding="utf-8"))
    readiness = current_drive_option_schema_assessment()
    final_verdict = (
        "NOT_EVALUATED_DATA_BLOCKED"
        if not readiness["ready"]
        else "PROMISING_FRESH_CONFIRMATION_REQUIRED"
    )
    evidence = {
        "schema_version": "1.0",
        "strategy_id": specification["strategy_id"],
        "family": specification["family"],
        "spec_sha256": _sha256(spec_path),
        "calibration": calibration_evidence(),
        "data_readiness": readiness,
        "candidate_count": 0,
        "candidate": None,
        "final_verdict": final_verdict,
        "claim_boundary": specification["claim_boundary"],
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
