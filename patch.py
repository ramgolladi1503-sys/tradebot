with open("scripts/generate_opening_drive_trade_ledger.py", "r") as f:
    content = f.read()

lines = content.split('\n')
idx = 0
for i, line in enumerate(lines):
    if "cap_saturation_ratio" in line:
        idx = i - 5
        break

lines = lines[:idx]
lines.extend([
    '    summary = {',
    '        "metrics": {',
    '            "total_trades": total_trades,',
    '            "buy_call_count": setup_types.get("BUY_CALL", 0),',
    '            "buy_put_count": setup_types.get("BUY_PUT", 0),',
    '            "active_symbol_days": active_symbol_days,',
    '            "max_possible_trades": max_possible_trades,',
    '            "cap_saturation_ratio": cap_saturation,',
    '            "symbol_days_at_cap": symbol_days_at_cap,',
    '            "zero_trade_symbol_days": zero_trade_symbol_days',
    '        }',
    '    }',
    '    with open(out_dir / "phase_4_trade_ledger_summary.json", \'w\') as f:',
    '        json.dump(summary, f, indent=2)',
    '',
    'if __name__ == "__main__":',
    '    parser = argparse.ArgumentParser()',
    '    parser.add_argument("--start-date", required=True)',
    '    parser.add_argument("--end-date", required=True)',
    '    parser.add_argument("--config-override", default="{}")',
    '    args = parser.parse_args()',
    '    ',
    '    s_date = args.start_date.replace("-", "")',
    '    e_date = args.end_date.replace("-", "")',
    '    generate_ledger(s_date, e_date, args.config_override)',
    ''
])

with open("scripts/generate_opening_drive_trade_ledger.py", "w") as f:
    f.write('\n'.join(lines))
