from pathlib import Path

path = Path('dashboard/ui/table_model.py')
text = path.read_text(encoding='utf-8')
old = 'hard_blockers soft_penalties warnings trade_key tradingsymbol\n'
new = 'hard_blockers soft_penalties warnings trade_id candidate_id trade_key tradingsymbol\n'
if text.count(old) != 1:
    raise SystemExit(f'UI_IDENTITY_PATCH_CONTEXT_COUNT:{text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('UI identity columns added')
