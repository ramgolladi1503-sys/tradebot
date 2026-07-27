#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from research.upstox_expired_options.dynamic_atm_selection import (
    dynamic_cycle_strike_union,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Build a dynamic session-ATM contract request manifest.'
    )
    parser.add_argument('--underlying-candles', required=True)
    parser.add_argument('--contracts-root', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cycle-days', type=int, default=7)
    parser.add_argument('--strike-wings', type=int, default=2)
    args = parser.parse_args()

    underlying = pd.read_parquet(args.underlying_candles)
    root = Path(args.contracts_root)
    selected_rows: list[dict] = []
    for expiry_dir in sorted(root.glob('expiry=*')):
        expiry = date.fromisoformat(expiry_dir.name.split('=', 1)[1])
        contracts_path = expiry_dir / 'contracts.json'
        if not contracts_path.exists():
            continue
        contracts = json.loads(contracts_path.read_text())
        strikes = sorted(
            {
                float(row['strike_price'])
                for row in contracts
                if str(row.get('instrument_type', '')).upper() in {'CE', 'PE'}
            }
        )
        selected = set(
            dynamic_cycle_strike_union(
                underlying,
                strikes,
                expiry,
                cycle_days=args.cycle_days,
                wings=args.strike_wings,
            )
        )
        for row in contracts:
            option_type = str(row.get('instrument_type', '')).upper()
            strike = float(row.get('strike_price', -1))
            if option_type not in {'CE', 'PE'} or strike not in selected:
                continue
            selected_rows.append(
                {
                    'expiry': expiry.isoformat(),
                    'option_type': option_type,
                    'strike': strike,
                    'instrument_key': row['instrument_key'],
                    'trading_symbol': row.get('trading_symbol'),
                    'selection_policy': 'DYNAMIC_SESSION_ATM_UNION_V2',
                }
            )

    frame = pd.DataFrame(selected_rows).sort_values(
        ['expiry', 'strike', 'option_type']
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    print(
        json.dumps(
            {
                'selection_policy': 'DYNAMIC_SESSION_ATM_UNION_V2',
                'selected_contracts': len(frame),
                'expiries': int(frame.expiry.nunique()) if not frame.empty else 0,
                'output': str(output),
            },
            sort_keys=True,
        )
    )


if __name__ == '__main__':
    main()
