#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.late_day_downside_confirmation_v1.engine import (
    Policy,
    normalize_ts,
    replay_one,
    round_atm,
    summarize,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--intent-csv', required=True)
    parser.add_argument('--contract-inventory-csv', required=True)
    parser.add_argument('--archive-root', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    intents = pd.read_csv(args.intent_csv)
    intents = intents[
        (intents.strategy_id == 'LATE_DAY_MOMENTUM')
        & (intents.direction == 'BUY_PUT')
        & (intents.partition != 'holdout')
    ]
    inventory = pd.read_csv(args.contract_inventory_csv)
    index: dict[tuple[date, str, date], list[dict]] = defaultdict(list)
    expiries = sorted({date.fromisoformat(value) for value in inventory.expiry.astype(str)})
    for row in inventory.to_dict('records'):
        contract = {
            'expiry': date.fromisoformat(str(row['expiry'])),
            'option_type': str(row['option_type']),
            'strike': float(row['strike']),
            'path': str(Path(args.archive_root) / str(row['raw_candle_path'])),
        }
        for session in str(row['session_dates']).split(';'):
            if session:
                index[(contract['expiry'], contract['option_type'], date.fromisoformat(session))].append(contract)

    policy = Policy()
    trades: list[dict] = []
    blockers: list[dict] = []
    for row in intents.to_dict('records'):
        signal = normalize_ts(row['signal_timestamp'])
        session = signal.date()
        expiry = next((value for value in expiries if value >= session), None)
        intent = {
            'signal_timestamp': signal,
            'underlying_price': float(row['signal_time_underlying_price']),
            'partition': row['partition'],
            'signal_identity_hash': row['signal_identity_hash'],
            'strategy_id': row['strategy_id'],
            'direction': row['direction'],
        }
        if expiry is None or (expiry - session).days > 7:
            blockers.append({**intent, 'reason': 'EXPIRY_UNIVERSE_UNAVAILABLE'})
            continue
        pool = index.get((expiry, 'PE', session), [])
        target = round_atm(intent['underlying_price'])
        if not pool:
            blockers.append({**intent, 'reason': 'SAME_SESSION_PE_UNAVAILABLE'})
            continue
        contract = min(pool, key=lambda item: (abs(item['strike'] - target), item['strike']))
        if abs(contract['strike'] - target) > policy.max_strike_distance:
            blockers.append(
                {
                    **intent,
                    'reason': 'NEAR_ATM_PE_UNAVAILABLE',
                    'nearest_distance': contract['strike'] - target,
                }
            )
            continue
        trade = replay_one(intent, contract, policy)
        if trade is None:
            blockers.append(
                {**intent, 'reason': 'CONFIRMATION_ENTRY_OR_EXIT_FILTERED'}
            )
            continue
        trades.append(trade)

    trade_frame = pd.DataFrame(trades)
    blocker_frame = pd.DataFrame(blockers)
    trade_frame.to_csv(output / 'trade_ledger.csv', index=False)
    blocker_frame.to_csv(output / 'blockers.csv', index=False)
    summarize(trade_frame).to_csv(output / 'summary.csv', index=False)
    manifest = {
        'schema_version': 'late_day_downside_confirmation_v1',
        'policy': policy.__dict__,
        'input_intents': len(intents),
        'trades': len(trade_frame),
        'blockers': len(blocker_frame),
        'holdout_read': False,
        'verdict': 'PROMISING_RESEARCH_HYPOTHESIS_NOT_CERTIFIED',
    }
    (output / 'manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + '\n'
    )


if __name__ == '__main__':
    main()
