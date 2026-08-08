#!/usr/bin/env python3
"""Controlled autonomous implementer for MROS sprints S004-S110.

Fresh Codex implementation runs only in a disposable detached worktree. Publication
is allowed only when scope remains inside research/MROS code and the authority head
has not moved. TradeBot runtime/broker/execution paths are forbidden before M9.
"""
from __future__ import annotations
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
from mros_program_catalog import sprint_spec,common_acceptance
AUTH='research/mros-program-v1'
ALLOWED_PREFIXES=('scripts/mros/','tests/mros/','research/')
FORBIDDEN_PREFIXES=('research/program/','runtime/','execution/','broker/','strategies/','strategy/','tradebot/')
class SprintExecutionError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout:int=3600,check=True,env=None):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False,env=env)
 if check and p.returncode!=0:raise SprintExecutionError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def changed_paths(wt:Path)->list[str]:
 out=[]
 for line in git(wt,'status','--porcelain').stdout.splitlines():
  if not line.strip():continue
  p=line[3:]
  if ' -> ' in p:p=p.split(' -> ',1)[1]
  out.append(p)
 return sorted(set(out))
def validate_scope(paths:list[str])->None:
 if not paths:raise SprintExecutionError('SPRINT_IMPLEMENTATION_PRODUCED_NO_CHANGES')
 for p in paths:
  if p.startswith('/') or '..' in Path(p).parts:raise SprintExecutionError(f'INVALID_PATH:{p}')
  if any(p.startswith(x) for x in FORBIDDEN_PREFIXES):raise SprintExecutionError(f'FORBIDDEN_PATH:{p}')
  if not any(p.startswith(x) for x in ALLOWED_PREFIXES):raise SprintExecutionError(f'PATH_NOT_ALLOWLISTED:{p}')

def prompt(number:int,base:str)->str:
 s=sprint_spec(number)
 return f'''You are the autonomous MROS implementation agent for {s.sprint}. You are not its reviewer or auditor.

Exact starting authority head: {base}
Milestone: {s.milestone}
Work package: {s.wp}
Work-package product context: {s.product_context}
Primary risk: {s.primary_risk}
Sprint phase: {s.phase}
Sprint objective: {s.objective}
Assurance tier after implementation: {s.assurance_tier}

Repository/manual law:
- repository evidence outranks model confidence;
- one active sprint objective; adjacent ideas are Parking Lot only;
- Unknown is legal;
- no silent supersession;
- causal time and no denominator laundering;
- research remains Research/R and runtime authority remains NONE through M8;
- M9/S111+ is forbidden to this autonomous controller.

Required engineering behavior:
- Inspect existing repository artifacts first and reuse accepted contracts.
- Implement only what is necessary for this sprint and {s.wp}.
- Prefer machine-readable contracts, deterministic fixtures, explicit fail-closed errors and provenance.
- Add/adjust focused tests including negative, boundary, reproducibility and regression controls appropriate to the phase.
- Preserve prior accepted evidence; never rewrite failed historical evidence.
- Do not weaken existing gates, schemas, fixtures, calibration, review independence or acceptance criteria to get a pass.
- Do not edit research/program state/ledger; the controller owns transitions.
- Do not touch runtime, strategies, risk, execution, broker behavior, credentials, or live data.
- Do not create a new long-lived worktree, branch, daemon, queue, scheduler or architecture layer unless this sprint's contract explicitly requires it.

Common acceptance obligations:
{json.dumps(common_acceptance(),indent=2)}

For this phase, create durable sprint evidence under research/evidence/sprints/{s.sprint}/, including a machine-readable sprint contract/manifest and documented test commands/results sufficient for an independent reviewer. For acceptance/handoff phases, seal the WP evidence manifest and update only research documentation/journal artifacts needed by the work-package objective; do not mutate program state/ledger.

Run the most relevant deterministic tests available. Do not commit or push. Implement now; final response should summarize files and tests only.'''

def execute(repo:Path,state_root:Path,number:int)->dict:
 if number<4 or number>110:raise SprintExecutionError('SPRINT_OUTSIDE_AUTONOMOUS_POST_BOOTSTRAP_RANGE')
 if shutil.which('codex') is None:raise SprintExecutionError('CODEX_CLI_NOT_FOUND')
 git(repo,'fetch','origin',AUTH,timeout=300);base=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip()
 root=state_root/'program-sprint-worktrees';root.mkdir(parents=True,exist_ok=True);wt=root/f'S{number:03d}-{base[:8]}'
 if wt.exists():git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True)
 git(repo,'worktree','add','--detach',str(wt),base,timeout=300)
 try:
  env=os.environ.copy();env.update({'MROS_RUNTIME_AUTHORITY':'NONE','MROS_BROKER_ACTIONS_ALLOWED':'0','MROS_ACTIVE_SPRINT':f'S{number:03d}'})
  agent=run(wt,'codex','exec','--ephemeral','--sandbox','workspace-write','--color','never',prompt(number,base),timeout=int(os.environ.get('MROS_CODEX_SPRINT_TIMEOUT_SECONDS','5400')),check=False,env=env)
  if agent.returncode!=0:raise SprintExecutionError(f'CODEX_SPRINT_FAILED:{agent.returncode}:{(agent.stdout or "")[-4000:]}')
  paths=changed_paths(wt);validate_scope(paths)
  # Program state must never be changed by the implementer even though research/ is otherwise allowed.
  if any(p.startswith('research/program/') for p in paths):raise SprintExecutionError('PROGRAM_STATE_MUTATION_FORBIDDEN')
  py=[p for p in paths if p.endswith('.py') and (wt/p).is_file()]
  if py:run(wt,'python3','-m','py_compile',*py,timeout=300)
  tests=[p for p in paths if p.startswith('tests/mros/') and p.endswith('.py') and (wt/p).is_file()]
  if tests:run(wt,'python3','-m','pytest','-q',*tests,timeout=1800)
  git(wt,'add','--',*paths);staged=git(wt,'diff','--cached','--name-only').stdout.splitlines()
  if set(staged)!=set(paths):raise SprintExecutionError('STAGED_SCOPE_MISMATCH')
  git(wt,'config','user.name','MROS Autonomous Implementer');git(wt,'config','user.email','mros-autonomous@local.invalid')
  git(wt,'commit','-m',f'mros(S{number:03d}): autonomous sprint implementation [skip ci]')
  candidate=git(wt,'rev-parse','HEAD').stdout.strip()
  ev=wt/f'research/evidence/sprints/S{number:03d}/AUTONOMOUS_IMPLEMENTATION_EXECUTION.json';ev.parent.mkdir(parents=True,exist_ok=True)
  ev.write_text(json.dumps({'schema_version':'mros-autonomous-sprint-execution-v1','sprint':f'S{number:03d}','base_head':base,'candidate_head':candidate,'changed_paths':paths,'agent_exit_code':agent.returncode,'runtime_authority':'NONE','broker_actions':'NONE','m9_status':'NOT_STARTED','recorded_at':time.time()},sort_keys=True,indent=2)+'\n',encoding='utf-8')
  rel=str(ev.relative_to(wt));git(wt,'add','--',rel);git(wt,'commit','-m',f'mros(S{number:03d}): seal autonomous implementation evidence [skip ci]');candidate=git(wt,'rev-parse','HEAD').stdout.strip()
  git(repo,'fetch','origin',AUTH,timeout=300);remote=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip()
  if remote!=base:raise SprintExecutionError(f'AUTHORITY_MOVED_DURING_SPRINT:base={base}:remote={remote}')
  git(wt,'push','origin',f'HEAD:{AUTH}',timeout=300)
  return {'status':'SPRINT_IMPLEMENTATION_PUBLISHED','sprint':f'S{number:03d}','base':base,'candidate_head':candidate,'changed_paths':paths,'runtime_authority':'NONE'}
 finally:
  git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True);git(repo,'worktree','prune',check=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);p.add_argument('--sprint-number',required=True,type=int);a=p.parse_args()
 try:print(json.dumps(execute(a.repo.resolve(),a.state_root.resolve(),a.sprint_number),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'SPRINT_IMPLEMENTATION_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
