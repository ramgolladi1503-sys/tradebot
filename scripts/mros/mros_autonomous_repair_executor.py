#!/usr/bin/env python3
"""Controlled Codex repair executor for the MROS research program.

This is implementation machinery, not a reviewer. It gives a fresh Codex process
write access only inside a disposable detached worktree, validates the resulting
change scope, runs local syntax/tests, and fast-forwards the research branch only
when its remote head has not moved. Runtime/broker paths and program state are
never writable through this executor.
"""
from __future__ import annotations
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path

AUTH='research/mros-program-v1'
ALLOWED_PREFIXES=('scripts/mros/','tests/mros/','research/review_board/','research/audit_board/')
FORBIDDEN_PREFIXES=('research/program/','tradebot/','runtime/','execution/','broker/','strategies/','strategy/')
MAX_REPAIR_GENERATIONS=5
class RepairError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout:int=1800,check:bool=True,env=None):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False,env=env)
 if check and p.returncode!=0:raise RepairError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p

def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def changed_paths(wt:Path)->list[str]:
 out=[]
 for line in git(wt,'status','--porcelain').stdout.splitlines():
  if not line.strip():continue
  raw=line[3:]
  if ' -> ' in raw:raw=raw.split(' -> ',1)[1]
  out.append(raw)
 return sorted(set(out))
def validate_scope(paths:list[str])->None:
 if not paths:raise RepairError('REPAIR_PRODUCED_NO_CHANGES')
 for p in paths:
  if p.startswith('/') or '..' in Path(p).parts:raise RepairError(f'REPAIR_PATH_INVALID:{p}')
  if any(p.startswith(x) for x in FORBIDDEN_PREFIXES):raise RepairError(f'REPAIR_FORBIDDEN_PATH:{p}')
  if not any(p.startswith(x) for x in ALLOWED_PREFIXES):raise RepairError(f'REPAIR_PATH_NOT_ALLOWLISTED:{p}')

def prompt(contract:dict,generation:int)->str:
 return f'''You are the MROS implementation repair agent, not a reviewer.\n\nRepair generation: {generation}/{MAX_REPAIR_GENERATIONS}\n\nThe frozen review/audit population has completed and the controller has synthesized the following blocking repair contract:\n\n{json.dumps(contract,sort_keys=True,indent=2)}\n\nRules:\n- Repair the common root causes, not each reviewer wording separately.\n- Make the smallest correct changes.\n- You MAY edit only scripts/mros/, tests/mros/, research/review_board/, research/audit_board/.\n- NEVER edit research/program/, TradeBot runtime/strategy/risk/execution/broker code, queue artifacts, credentials, or live configuration.\n- NEVER weaken calibration fixtures, acceptance criteria, schemas, negative controls, or independence requirements to obtain PASS.\n- Preserve runtime_authority=NONE and M9=NOT_STARTED.\n- Add focused regression tests for every root-cause class in the repair contract.\n- Run the most relevant local tests you can run.\n- Do not commit, push, merge, or modify another worktree. The controller owns publication.\n\nImplement the repair now. Your final message should summarize changed files and tests only.\n'''

def execute(*,repo:Path,state_root:Path,contract_path:Path,generation:int)->dict:
 if generation<1 or generation>MAX_REPAIR_GENERATIONS:raise RepairError('REPAIR_GENERATION_LIMIT_EXCEEDED')
 if shutil.which('codex') is None:raise RepairError('CODEX_CLI_NOT_FOUND')
 git(repo,'fetch','origin',AUTH,timeout=300);base=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip()
 contract=json.loads(contract_path.read_text(encoding='utf-8'))
 failed=contract.get('failed_head')
 if not isinstance(failed,str) or not re.fullmatch(r'[0-9a-f]{40}',failed):raise RepairError('REPAIR_CONTRACT_FAILED_HEAD_INVALID')
 if git(repo,'merge-base','--is-ancestor',failed,base,check=False).returncode!=0:raise RepairError('FAILED_HEAD_NOT_ANCESTOR_OF_AUTHORITY')
 root=state_root/'repair-worktrees';root.mkdir(parents=True,exist_ok=True);wt=root/f"{contract.get('sprint','SXXX')}-{generation}-{base[:8]}"
 if wt.exists():git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True)
 git(repo,'worktree','add','--detach',str(wt),base,timeout=300)
 try:
  env=os.environ.copy();env.update({'MROS_RUNTIME_AUTHORITY':'NONE','MROS_BROKER_ACTIONS_ALLOWED':'0','MROS_REPAIR_GENERATION':str(generation)})
  cmd=['codex','exec','--ephemeral','--sandbox','workspace-write','--color','never',prompt(contract,generation)]
  agent=run(wt,*cmd,timeout=int(os.environ.get('MROS_CODEX_REPAIR_TIMEOUT_SECONDS','3600')),check=False,env=env)
  if agent.returncode!=0:raise RepairError(f'CODEX_REPAIR_FAILED:{agent.returncode}:{(agent.stdout or "")[-4000:]}')
  paths=changed_paths(wt);validate_scope(paths)
  py=[p for p in paths if p.endswith('.py') and (wt/p).is_file()]
  if py:run(wt,'python3','-m','py_compile',*py,timeout=300)
  tests=[p for p in paths if p.startswith('tests/mros/') and p.endswith('.py') and (wt/p).is_file()]
  if tests:run(wt,'python3','-m','pytest','-q',*tests,timeout=1200)
  git(wt,'add','--',*paths);staged=git(wt,'diff','--cached','--name-only').stdout.splitlines()
  if set(staged)!=set(paths):raise RepairError('REPAIR_STAGED_SCOPE_MISMATCH')
  git(wt,'config','user.name','MROS Autonomous Repair');git(wt,'config','user.email','mros-autonomous@local.invalid')
  git(wt,'commit','-m',f"mros({contract.get('sprint','S003')}): autonomous repair generation {generation} [skip ci]")
  code_commit=git(wt,'rev-parse','HEAD').stdout.strip()
  evidence_rel=f"research/evidence/sprints/{contract.get('sprint','S003')}/AUTONOMOUS_REPAIR_G{generation}_{code_commit[:8]}.json"
  evidence=wt/evidence_rel;evidence.parent.mkdir(parents=True,exist_ok=True)
  evidence.write_text(json.dumps({'schema_version':'mros-autonomous-repair-execution-v1','sprint':contract.get('sprint'),'generation':generation,'failed_head':failed,'repair_base':base,'code_commit':code_commit,'changed_paths':paths,'agent_exit_code':agent.returncode,'runtime_authority':'NONE','broker_actions':'NONE','m9_status':'NOT_STARTED','recorded_at':time.time()},sort_keys=True,indent=2)+'\n',encoding='utf-8')
  git(wt,'add','--',evidence_rel);git(wt,'commit','-m',f"mros({contract.get('sprint','S003')}): seal autonomous repair generation {generation} evidence [skip ci]")
  candidate=git(wt,'rev-parse','HEAD').stdout.strip()
  git(repo,'fetch','origin',AUTH,timeout=300);remote=git(repo,'rev-parse',f'origin/{AUTH}').stdout.strip()
  if remote!=base:raise RepairError(f'AUTHORITY_MOVED_DURING_REPAIR:base={base}:remote={remote}')
  git(wt,'push','origin',f'HEAD:{AUTH}',timeout=300)
  return {'status':'REPAIR_PUBLISHED','generation':generation,'failed_head':failed,'base':base,'code_commit':code_commit,'candidate_head':candidate,'changed_paths':paths,'evidence_path':evidence_rel,'runtime_authority':'NONE'}
 finally:
  git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True);git(repo,'worktree','prune',check=False)

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);p.add_argument('--repair-contract',required=True,type=Path);p.add_argument('--generation',required=True,type=int);a=p.parse_args()
 try:print(json.dumps(execute(repo=a.repo.resolve(),state_root=a.state_root.resolve(),contract_path=a.repair_contract.resolve(),generation=a.generation),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'REPAIR_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
