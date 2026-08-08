# MROS M1-M8 autonomous bridge exact-head self-test R100

Exact bridge candidate: `786924bb3cd6da992aff944094879fe55cfc3f45`

Non-certifying infrastructure self-test. Do not modify anything.

Run from the detached candidate worktree with no writes:

1. `git rev-parse HEAD`
2. `python3 --version`
3. `PYTHONDONTWRITEBYTECODE=1 python3 -B -c "import pathlib; fs=list(pathlib.Path('scripts/mros').glob('*.py'))+list(pathlib.Path('tests/mros').glob('*.py')); [compile(p.read_text(encoding='utf-8'),str(p),'exec') for p in fs]; print('IN_MEMORY_COMPILE_PASS',len(fs))"`
4. `PYTHONDONTWRITEBYTECODE=1 python3 -B -c "import sys; sys.path.insert(0,'scripts/mros'); import mros_autonomous_supervisor as s, mros_program_catalog as c, mros_post_bootstrap_cycle_v2 as p, mros_program_sprint_executor as i, mros_program_repair_executor as r, mros_program_native_validator as n; assert c.sprint_spec(4).sprint=='S004'; assert c.sprint_spec(30).assurance_tier=='FULL'; assert c.sprint_spec(110).terminal_m8 and c.next_sprint(110) is None; assert any('Constitution can be applied' in x for x in c.sprint_acceptance(5)); assert any('milestone evidence manifest' in x.lower() for x in c.sprint_acceptance(30)); assert s.derive_phase({'active_milestone':'M1','active_sprint':'S004'},[],{})==('AUTONOMOUS_PROGRAM_CYCLE','RUN_AUTONOMOUS_CYCLE'); assert s.derive_phase({'active_milestone':'M9','active_sprint':'S111'},[],{})[0]=='HARD_STOP'; print('M1_M8_AUTONOMY_ASSERTIONS_PASS')"`

Do not use pytest or py_compile in this read-only sandbox.

Return Markdown with exact HEAD, Python version, complete stdout, every exit code, `RUNTIME_AUTHORITY=NONE`, `BROKER_ACTIONS=NONE`, and `AUTONOMY_BRIDGE_SELFTEST=PASS|FAIL`. PASS requires exact HEAD and all commands exit 0.