# MROS autonomous bridge exact-head self-test R99

Exact candidate: `fed1c4b003c3a42766a2e4638b3df2073ab75e34`

This is a non-certifying bridge deployment candidate self-test. Do not repair or review the MROS research candidate.

Run exactly these read-only-safe checks from the detached bridge candidate worktree:

1. `git rev-parse HEAD`
2. `python3 --version`
3. `PYTHONDONTWRITEBYTECODE=1 python3 -B -c "import pathlib; fs=list(pathlib.Path('scripts/mros').glob('*.py')); [compile(p.read_text(encoding='utf-8'),str(p),'exec') for p in fs]; print('IN_MEMORY_COMPILE_PASS',len(fs))"`
4. `PYTHONDONTWRITEBYTECODE=1 python3 -B -c "import sys; sys.path.insert(0,'scripts/mros'); import mros_autonomous_supervisor as s, mros_program_catalog as c, mros_post_bootstrap_cycle as p, mros_program_sprint_executor as i, mros_program_repair_executor as r, mros_program_native_validator as n, mros_s003_autonomous_finalizer as f; assert c.sprint_spec(4).sprint=='S004'; assert c.sprint_spec(110).terminal_m8; assert c.next_sprint(110) is None; assert s.derive_phase({'active_milestone':'M1','active_sprint':'S004'},[],{})==('AUTONOMOUS_PROGRAM_CYCLE','RUN_AUTONOMOUS_CYCLE'); assert s.derive_phase({'active_milestone':'M9','active_sprint':'S111'},[],{})[0]=='HARD_STOP'; print('AUTONOMY_IMPORT_ASSERTIONS_PASS')"`

Do not invoke pytest or py_compile because this reviewer sandbox intentionally has no writable temp/cache directory.

Return Markdown containing exact HEAD, Python version, complete stdout for both Python checks, each exit code, `RUNTIME_AUTHORITY=NONE`, `BROKER_ACTIONS=NONE`, and `AUTONOMY_BRIDGE_SELFTEST=PASS|FAIL`. PASS requires exact HEAD and every command exit 0.