"""Forensic Investigation CLI & Diagnostic Surface.

Usage:
  python3 -m core.trade_truth.investigate <TRACE_ID> [--json] [--replay] [--verify-hash]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from core.trade_truth.replay import replay_truth_record
from core.trade_truth.store import TruthStore, default_truth_store_path


def format_human_report(record: dict, replay_res=None) -> str:
    ident = record.get("identity") or {}
    tim = record.get("timing") or {}
    mkt = record.get("market") or {}
    ana = record.get("analytical") or {}
    dec = record.get("decision") or {}
    prov = record.get("provenance") or {}
    exc = record.get("execution") or {}
    out = record.get("outcome") or {}

    lines = [
        "=" * 70,
        f"TRADE TRUTH FORENSIC REPORT: {ident.get('trace_id')}",
        "=" * 70,
        f"Record ID:    {ident.get('truth_record_id')}",
        f"Session ID:   {ident.get('session_id')}",
        f"Candidate ID: {ident.get('candidate_id')}",
        f"Strategy:     {ident.get('strategy_id')}",
        f"Instrument:   {ident.get('instrument')} (Underlying: {ident.get('underlying')})",
        "",
        "--- MARKET STATE USED ---",
        f"LTP: {mkt.get('ltp')} | Bid: {mkt.get('bid')} | Ask: {mkt.get('ask')} | Spread: {mkt.get('spread')}",
        f"Feed Age: {mkt.get('feed_age_sec')}s | Source: {mkt.get('data_source')}",
        f"Integrity: {mkt.get('market_state_integrity')} | Gap Status: {mkt.get('sequence_gap_status')}",
        "",
        "--- ANALYTICAL STATE ---",
        f"Regime: {ana.get('regime')} (Conf: {ana.get('regime_confidence')})",
        f"Features count: {len(ana.get('features_used') or {})}",
        f"Signal Conf: {ana.get('signal_confidence')}",
        "",
        "--- DECISION TRUTH ---",
        f"Final Action:        {dec.get('final_action')}",
        f"Governance Decision: {dec.get('governance_decision')}",
        f"Risk Result:         {dec.get('risk_result')}",
        f"Reason Codes:        {', '.join(dec.get('reason_codes') or []) or 'NONE'}",
        f"Blockers:            {', '.join(dec.get('blockers') or []) or 'NONE'}",
        "",
        "--- EXECUTION REALITY ---",
        f"Execution Type:      {exc.get('execution_type')}",
        f"Executable State:    {exc.get('executable_market_state')}",
        f"Theoretical Price:   {exc.get('theoretical_executable_price')}",
        f"Broker Submission:   {exc.get('actual_broker_submission')} (Auth: {exc.get('broker_submission_authorized')})",
        f"Actual Fill:         {exc.get('actual_fill')}",
        f"Is Counterfactual:   {exc.get('is_counterfactual')}",
        "",
        "--- PROVENANCE ---",
        f"Git SHA:             {prov.get('git_sha')} (Dirty: {prov.get('dirty_tree')})",
        f"Config Hash:         {prov.get('config_hash')}",
        f"Truth Schema:        v{prov.get('truth_schema_version')}",
        "",
        "--- OUTCOME TRUTH ---",
        f"Status:              {out.get('status')}",
        f"Price Basis:         {out.get('price_basis')}",
        f"Realized Outcome:    {out.get('realized_outcome')}",
        f"MFE (abs):           {out.get('mfe_abs')}",
        f"MAE (abs):           {out.get('mae_abs')}",
        f"Attribution:         {out.get('attribution_primary')}",
        "",
        "--- DETERMINISTIC INTEGRITY & REPLAY ---",
        f"Live Decision Hash:   {record.get('live_decision_hash')}",
        f"Record Hash:          {record.get('record_hash')}",
    ]

    if replay_res:
        lines.extend([
            f"Replay Decision Hash: {replay_res.replay_decision_hash}",
            f"Parity Status:        {replay_res.status}",
            f"Parity Match:         {replay_res.parity}",
            f"Integrity Valid:      {replay_res.record_integrity_valid}",
        ])
        if replay_res.divergences:
            lines.append("Divergences:")
            for d in replay_res.divergences:
                lines.append(f"  - {d}")

    lines.append("=" * 70)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Investigate TradeBot decision truth by trace_id.")
    parser.add_argument("trace_id", help="Trace identifier to investigate.")
    parser.add_argument("--store", default=None, help="Custom path to trade_truth.jsonl.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    parser.add_argument("--replay", action="store_true", help="Perform deterministic replay verification.")
    parser.add_argument("--verify-hash", action="store_true", help="Verify record integrity hash.")

    args = parser.parse_args(argv)

    store = TruthStore(args.store)
    records = store.get_by_trace_id(args.trace_id)

    if not records:
        print(f"ERROR: No truth records found for trace_id '{args.trace_id}' in {store.path}", file=sys.stderr)
        return 1

    outputs = []
    for record in records:
        replay_res = None
        if args.replay or args.verify_hash:
            replay_res = replay_truth_record(record)

        if args.json:
            outputs.append({
                "record": record,
                "replay": replay_res.to_dict() if replay_res else None,
                "broker_api_called": False,
                "is_order_action": False,
            })
        else:
            print(format_human_report(record, replay_res))
            print()

    if args.json:
        print(json.dumps(outputs if len(outputs) > 1 else outputs[0], indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
