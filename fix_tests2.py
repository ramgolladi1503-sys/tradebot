import re

with open('tests/test_trade_builder_soft_vetoes.py', 'r') as f:
    content = f.read()

def inject(func_name, patch_str):
    global content
    pattern = r'(def ' + func_name + r'\(.*?\):\n(?:    .*?\n)*?)(    builder = TradeBuilder)'
    # Find insertion point before `builder = TradeBuilder`
    match = re.search(pattern, content)
    if match:
        content = content[:match.end(1)] + "    " + patch_str + "\n" + content[match.start(2):]
    else:
        print("Failed to inject for", func_name)

patch = 'monkeypatch.setattr(cfg, "PLANNING_SIGNAL_MEAN_EDGE_MIN", 0.0012, raising=False)\n    monkeypatch.setattr(cfg, "PLANNING_SIGNAL_VWAP_EDGE_MIN", 0.0008, raising=False)'

inject('test_sideways_regime_caps_directional_candidates', patch)
inject('test_sideways_snapshot_can_emit_watchlist_candidates', patch)
inject('test_breakout_family_blocked_in_sideways_regime', patch)
inject('test_sideways_snapshot_can_emit_real_sideways_watchlist_candidates', patch)
inject('test_range_watchlist_allowed_in_sideways_regime', patch)
inject('test_sideways_range_candidate_carries_sideways_direction_family', patch)
inject('test_exceptional_family_can_override_regime_gate_when_configured', patch)

with open('tests/test_trade_builder_soft_vetoes.py', 'w') as f:
    f.write(content)
