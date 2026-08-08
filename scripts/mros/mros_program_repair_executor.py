#!/usr/bin/env python3
"""Bounded autonomous repair executor for MROS S004-S110."""
from __future__ import annotations
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
AUTH='research/mros-program-v1';MAX_GENERATIONS=5
ALLOWED_PREFIXES=('scripts/mros/','tests/mros/','research/')
FORBIDDEN_PREFIXES=('research/program/','runtime/','execution/','broker/','strategies/','strategy/','tradebot/')
class RepairError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout:int=3600,check=True,env=None):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False,env=env)
 if check and p.returncode!=0:raise RepairError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def changed(wt:Path):
 out=[]
 for l in git(wt,'status','--porcelain').stdout.splitlines():
  if not l.strip():continue
  p=l[3:]
  if ' -> ' in p:p=p.split(' -> ',1)[1]
  out.append(p)
 return sorted(set(out))
def scope(paths):
 if not paths:raise RepairError('NO_REPAIR_CHANGES')
 for p in paths:
  if any(p.startswith(x) for x in FORBIDDEN_PREFIXES):raise RepairError(f'FORBIDDEN_PATH:{p}')
  if not any(p.startswith(x) for x in ALLOWED_PREFIXES):raise RepairError(f'PATH_NOT_ALLOWLISTED:{p}')

def execute(repo:Path,state_root:Path,contract_path:Path,generation:int)->dict:
 if generation<1 or generation>MAX_GENERATIONS:raise RepairError('REPAIR_GENERATION_LIMIT')
 c=json.loads(contract_path.read_text(encoding='utf-8'));sprint=str(c.get('sprint',''))
 if not re.fullmatch(r'S\d{3}',sprint):raise RepairError('SPRINT_INVALID')
 failed=str(c.get('failed_head',''))
 if not re.fullmatch(r'[0-9a-f]{40}',failed):raise RepairError('FAILED_HEAD_INVALID')
 if shutil.which('codex') is None:raise RepairError('CODEX_CLI_NOT_FOUND')
 git(repo,'fetch','origin',AUTH,timeout=300);base=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip()
 if git(repo,'merge-base','--is-ancestor',failed,base,check=False).returncode!=0:raise RepairError('FAILED_HEAD_NOT_ANCESTOR')
 root=state_root/'program-repair-worktrees';root.mkdir(parents=True,exist_ok=True);wt=root/f'{sprint}-G{generation}-{base[:8]}'
 if wt.exists():git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True)
 git(repo,'worktree','add','--detach',str(wt),base,timeout=300)
 try:
  prompt=f'''You are the autonomous MROS repair implementer for {sprint}, generation {generation}/{MAX_GENERATIONS}. You are not a reviewer/auditor.\n\nRepair contract:\n{json.dumps(c,indent=2,sort_keys=True)}\n\nCluster related findings into root causes and repair them once. Preserve all gates, negative controls, history and authority semantics. Add focused regressions for each root-cause class. You may edit only MROS research/code/tests under research/, scripts/mros/, tests/mros/. Never edit research/program state/ledger, runtime, strategy, risk, execution, broker code, credentials or live data. Never start M9 or grant runtime authority. Do not commit/push; controller publishes. Run relevant tests.'''
  env=os.environ.copy();env.update({'MROS_RUNTIME_AUTHORITY':'NONE','MROS_BROKER_ACTIONS_ALLOWED':'0','MROS_REPAIR_GENERATION':str(generation)})
  a=run(wt,'codex','exec','--ephemeral','--sandbox','workspace-write','--color','never',prompt,timeout=int(os.environ.get('MROS_CODEX_REPAIR_TIMEOUT_SECONDS','5400')),check=False,env=env)
  if a.returncode!=0:raise RepairError(f'CODEX_REPAIR_FAILED:{a.returncode}:{(a.stdout or "")[-3000:]}')
  paths=changed(wt);scope(paths)
  py=[p for p in paths if p.endswith('.py') and (wt/p).is_file()]
  if py:run(wt,'python3','-m','py_compile',*py,timeout=600)
  tests=[p for p in paths if p.startswith('tests/mros/') and p.endswith('.py') and (wt/p).is_file()]
  if tests:run(wt,'python3','-m','pytest','-q',*tests,timeout=1800)
  git(wt,'add','--',*paths);git(wt,'config','user.name','MROS Autonomous Repair');git(wt,'config','user.email','mros-autonomous@local.invalid');git(wt,'commit','-m',f'mros({sprint}): autonomous repair generation {generation} [skip ci]')
  code=git(wt,'rev-parse','HEAD').stdout.strip();evrel=f'research/evidence/sprints/{sprint}/AUTONOMOUS_REPAIR_G{generation}_{code[:8]}.json';ev=wt/evrel;ev.parent.mkdir(parents=True,exist_ok=True);ev.write_text(json.dumps({'schema_version':'mros-autonomous-program-repair-v1','sprint':sprint,'generation':generation,'failed_head':failed,'repair_base':base,'candidate_head':code,'changed_paths':paths,'runtime_authority':'NONE','m9_status':'NOT_STARTED','recorded_at':time.time()},sort_keys=True,indent=2)+'\n',encoding='utf-8');git(wt,'add','--',evrel);git(wt,'commit','-m',f'mros({sprint}): seal autonomous repair evidence [skip ci]')
  git(repo,'fetch','origin',AUTH,timeout=300);remote=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip()
  if remote!=base:raise RepairError('AUTHORITY_MOVED_DURING_REPAIR')
  git(wt,'push','origin',f'HEAD:{AUTH}',timeout=300)
  return {'status':'PROGRAM_REPAIR_PUBLISHED','sprint':sprint,'generation':generation,'candidate_head':code,'authority_head':git(wt,'rev-parse','HEAD').stdout.strip(),'runtime_authority':'NONE'}
 finally:
  git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True);git(repo,'worktree','prune',check=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);p.add_argument('--contract',required=True,type=Path);p.add_argument('--generation',required=True,type=int);a=p.parse_args()
 try:print(json.dumps(execute(a.repo.resolve(),a.state_root.resolve(),a.contract.resolve(),a.generation),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'PROGRAM_REPAIR_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
