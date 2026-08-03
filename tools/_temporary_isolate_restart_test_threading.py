from pathlib import Path

path = Path('tests/test_kite_depth_restart.py')
text = path.read_text(encoding='utf-8')
old = '    monkeypatch.setattr(ws.threading, "Thread", _FailThread, raising=True)\n'
new = (
    '    # Replace only the websocket module reference. Mutating '\
    'ws.threading.Thread changes the shared Python threading module and '\
    'incorrectly blocks the independent persistence worker.\n'
    '    monkeypatch.setattr(\n'
    '        ws,\n'
    '        "threading",\n'
    '        SimpleNamespace(Thread=_FailThread),\n'
    '        raising=True,\n'
    '    )\n'
)
count = text.count(old)
if count != 1:
    raise SystemExit(f'RESTART_THREAD_PATCH_CONTEXT_COUNT:{count}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('restart test threading isolation applied')
