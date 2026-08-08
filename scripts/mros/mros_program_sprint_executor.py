#!/usr/bin/env python3
"""Controlled autonomous implementer for MROS sprints S004-S110."""
from __future__ import annotations
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
from mros_program_catalog import sprint_spec,sprint_acceptance
AUTH='research/mros-program-v1';ALLOWED_PREFIXES=('scripts/mros/','tests/mros/','research/');FORBIDDEN_PREFIXES=('research/program/','runtime/','execution/','broker/','strategies/','strategy/','tradebot/')
class SprintExecutionError(RuntimeError):pass
def run(cwd:Path,*args:str,timeout:int=3600,check=True,env=None):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False,env=env)
 if check and p.returncode!=0:raise SprintExecutionError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def changed_paths(wt:Path):
 out=[]
 for line in git(wt,'status','--porcelain').stdout.splitlines():
  if not line.strip():continue
  p=line[3:]
  if ' -> ' in p:p=p.split(' -> ',1)[1]
  out.append(p)
 return sorted(set(out))
def validate_scope(paths):
 if not paths:raise SprintExecutionError('SPRINT_IMPLEMENTATION_PRODUCED_NO_CHANGES')
 for p in paths:
  if p.startswith('/') or '..' in Path(p).parts:raise SprintExecutionError(f'INVALID_PATH:{p}')
  if any(p.startswith(x) for x in FORBIDDEN_PREFIXES):raise SprintExecutionError(f'FORBIDDEN_PATH:{p}')
  if not any(p.startswith(x) for x in ALLOWED_PREFIXES):raise SprintExecutionError(f'PATH_NOT_ALLOWLISTED:{p}')
def prompt(number:int,base:str):
 s=sprint_spec(number);milestone_extra='This is a milestone-closing sprint: seal the milestone evidence manifest and update the MROS manual/research journal release artifacts.' if s.assurance_tier=='FULL' else ''
 return f'''You are the autonomous MROS implementation agent for {s.sprint}. You are not its reviewer or auditor.\n\nExact starting authority head: {base}\nMilestone: {s.milestone}\nWork package: {s.wp}\nWork-package product context: {s.product_context}\nPrimary risk: {s.primary_risk}\nSprint phase: {s.phase}\nSprint objective: {s.objective}\nAssurance tier after implementation: {s.assurance_tier}\n{milestone_extra}\n\nRepository/manual law:\n- repository evidence outranks model confidence;\n- one active sprint objective; adjacent ideas are Parking Lot only;\n- Unknown is legal and negative results remain durable;\n- no silent supersession;\n- causal time and no denominator laundering;\n- research remains Research/R and runtime authority remains NONE through M8;\n- M9/S111+ is forbidden to this autonomous controller.\n\nRequired engineering behavior:\n- Inspect existing repository artifacts first and reuse accepted contracts.\n- Implement only what is necessary for this sprint and {s.wp}.\n- Prefer machine-readable contracts, deterministic fixtures, explicit fail-closed errors and provenance.\n- Add focused positive, negative, boundary, leakage, determinism, reproducibility, regression, fault-injection and invariant tests as applicable.\n- Preserve prior accepted/rejected evidence; never rewrite history.\n- Never weaken gates, schemas, fixtures, calibration, review independence or acceptance criteria to obtain PASS.\n- Do not edit research/program state/ledger; the controller owns transitions.\n- Do not touch runtime, strategies, risk, execution, broker behavior, credentials, or live data.\n- Do not create a new long-lived worktree/branch/daemon/queue/scheduler unless the frozen sprint contract explicitly requires it.\n\nAcceptance obligations for this sprint:\n{json.dumps(sprint_acceptance(number),indent=2)}\n\nCreate durable sprint evidence under research/evidence/sprints/{s.sprint}/ including machine-readable contract/manifest, exact changed-file manifest, test commands/results, hashes/IDs, assumptions/unknowns, destroyers where material, and decision-ready evidence. In acceptance/handoff phases seal the WP evidence manifest. {milestone_extra}\n\nRun the most relevant deterministic tests. Do not commit or push. Implement now; final response should summarize files and tests only.'''
def execute(repo:Path,state_root:Path,number:int):
 if number<4 or number>110:raise SprintExecutionError('SPRINT_OUTSIDE_AUTONOMOUS_POST_BOOTSTRAP_RANGE')
 if shutil.which('codex') is None:raise SprintExecutionError('CODEX_CLI_NOT_FOUND')
 git(repo,'fetch','origin',AUTH,timeout=300);base=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip();root=state_root/'program-sprint-worktrees';root.mkdir(parents=True,exist_ok=True);wt=root/f'S{number:03d}-{base[:8]}'
 if wt.exists():git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True)
 git(repo,'worktree','add','--detach',str(wt),base,timeout=300)
 try:
  env=os.environ.copy();env.update({'MROS_RUNTIME_AUTHORITY':'NONE','MROS_BROKER_ACTIONS_ALLOWED':'0','MROS_ACTIVE_SPRINT':f'S{number:03d}'})
  agent=run(wt,'codex','exec','--ephemeral','--sandbox','workspace-write','--color','never',prompt(number,base),timeout=int(os.environ.get('MROS_CODEX_SPRINT_TIMEOUT_SECONDS','5400')),check=False,env=env)
  if agent.returncode!=0:raise SprintExecutionError(f'CODEX_SPRINT_FAILED:{agent.returncode}:{(agent.stdout or "")[-4000:]}')
  paths=changed_paths(wt);validate_scope(paths)
  py=[p for p in paths if p.endswith('.py') and (wt/p).is_file()]
  if py:run(wt,'python3','-m','py_compile',*py,timeout=300)
  tests=[p for p in paths if p.startswith('tests/mros/') and p.endswith('.py') and (wt/p).is_file()]
  if tests:run(wt,'python3','-m','pytest','-q',*tests,timeout=1800)
  git(wt,'add','--',*paths);staged=git(wt,'diff','--cached','--name-only').stdout.splitlines()
  if set(staged)!=set(paths):raise SprintExecutionError('STAGED_SCOPE_MISMATCH')
  git(wt,'config','user.name','MROS Autonomous Implementer');git(wt,'config','user.email','mros-autonomous@local.invalid');git(wt,'commit','-m',f'mros(S{number:03d}): autonomous sprint implementation [skip ci]');code_candidate=git(wt,'rev-parse','HEAD').stdout.strip()
  ev=wt/f'research/evidence/sprints/S{number:03d}/AUTONOMOUS_IMPLEMENTATION_EXECUTION.json';ev.parent.mkdir(parents=True,exist_ok=True);ev.write_text(json.dumps({'schema_version':'mros-autonomous-sprint-execution-v1','sprint':f'S{number:03d}','base_head':base,'candidate_head':code_candidate,'changed_paths':paths,'agent_exit_code':agent.returncode,'runtime_authority':'NONE','broker_actions':'NONE','m9_status':'NOT_STARTED','recorded_at':time.time()},sort_keys=True,indent=2)+'\n',encoding='utf-8');rel=str(ev.relative_to(wt));git(wt,'add','--',rel);git(wt,'commit','-m',f'mros(S{number:03d}): seal autonomous implementation evidence [skip ci]');authority_head=git(wt,'rev-parse','HEAD').stdout.strip()
  git(repo,'fetch','origin',AUTH,timeout=300);remote=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip()
  if remote!=base:raise SprintExecutionError(f'AUTHORITY_MOVED_DURING_SPRINT:base={base}:remote={remote}')
  git(wt,'push','origin',f'HEAD:{AUTH}',timeout=300);return {'status':'SPRINT_IMPLEMENTATION_PUBLISHED','sprint':f'S{number:03d}','base':base,'candidate_head':code_candidate,'authority_head':authority_head,'changed_paths':paths,'runtime_authority':'NONE'}
 finally:
  git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True);git(repo,'worktree','prune',check=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);p.add_argument('--sprint-number',required=True,type=int);a=p.parse_args()
 try:print(json.dumps(execute(a.repo.resolve(),a.state_root.resolve(),a.sprint_number),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'SPRINT_IMPLEMENTATION_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
