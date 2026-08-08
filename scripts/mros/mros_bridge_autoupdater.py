#!/usr/bin/env python3
"""Safely self-update the Mac MROS bridge/supervisor from its Git branch.

The updater is separate from the supervisor. It never updates authority state.
It promotes a new bridge commit only after running the bridge/supervisor safety
tests in an isolated temporary worktree, then kickstarts the persistent services.
Benign no-op cases exit 0 so launchd does not report them as failures.
"""
from __future__ import annotations
import argparse,fcntl,os,shutil,subprocess,time
from pathlib import Path
BRANCH='research/mros-agent-bridge-v1';SERVICES=('com.aixion.mros-agent-worker','com.aixion.mros-autonomous-supervisor')
class UpdateError(RuntimeError):pass
def run(cwd:Path,*args:str,timeout:int=600,check=True):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise UpdateError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--source-repo',type=Path,default=Path('/Users/madhuram/tradebot'));ap.add_argument('--bridge-worktree',type=Path,default=Path('/Users/madhuram/.mros-agent-bridge/bridge'));ap.add_argument('--state-root',type=Path,default=Path('/Users/madhuram/.mros-agent-bridge/state'));ns=ap.parse_args();source=ns.source_repo.resolve();bridge=ns.bridge_worktree.resolve();state=ns.state_root.resolve();state.mkdir(parents=True,exist_ok=True)
 lock=(state/'bridge-updater.lock').open('a+')
 try:
  try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   print('MROS_BRIDGE_UPDATE_NOOP_LOCK_HELD');return 0
  git(source,'fetch','origin',BRANCH);target=git(source,'rev-parse',f'origin/{BRANCH}').stdout.strip();current=git(bridge,'rev-parse','HEAD').stdout.strip()
  if target==current:
   print(f'MROS_BRIDGE_UPDATE_NOOP_CURRENT {current}');return 0
  if git(bridge,'status','--porcelain').stdout.strip():raise UpdateError('BRIDGE_WORKTREE_NOT_CLEAN')
  test_root=state/'update-test-worktree'
  if test_root.exists():
   git(source,'worktree','remove','--force',str(test_root),check=False);shutil.rmtree(test_root,ignore_errors=True)
  git(source,'worktree','add','--detach',str(test_root),target,timeout=300)
  try:
   tests=[
    str(test_root/'tests/mros/test_mros_agent_bridge.py'),
    str(test_root/'tests/mros/test_mros_autonomous_supervisor.py'),
    str(test_root/'tests/mros/test_mros_state_transition_engine.py'),
    str(test_root/'tests/mros/test_mros_review_transport.py'),
   ]
   p=run(test_root,'python3','-m','pytest','-q',*tests,timeout=900,check=False)
   if p.returncode!=0:raise UpdateError('TARGET_TESTS_FAILED:'+((p.stdout or '')+(p.stderr or ''))[-4000:])
   compile_targets=[
    str(test_root/'scripts/mros/mros_autonomous_cycle_v2.py'),
    str(test_root/'scripts/mros/mros_review_transport.py'),
    str(test_root/'scripts/mros/mros_agent_git_worker.py'),
    str(test_root/'scripts/mros/mros_codex_backend.py'),
   ]
   c=run(test_root,'python3','-m','py_compile',*compile_targets,timeout=120,check=False)
   if c.returncode!=0:raise UpdateError('TARGET_COMPILE_FAILED:'+((c.stdout or '')+(c.stderr or ''))[-4000:])
  finally:
   git(source,'worktree','remove','--force',str(test_root),check=False);shutil.rmtree(test_root,ignore_errors=True);git(source,'worktree','prune',check=False)
  git(bridge,'checkout','--detach',target,timeout=300)
  uid=os.getuid()
  for svc in SERVICES:run(source,'launchctl','kickstart','-k',f'gui/{uid}/{svc}',timeout=60,check=False)
  log=state/'bridge_updates.log';log.write_text((log.read_text(encoding='utf-8') if log.exists() else '')+f'{time.time()} {current} -> {target}\n',encoding='utf-8')
  print(f'MROS_BRIDGE_UPDATED {current} -> {target}');return 0
 finally:
  fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
if __name__=='__main__':raise SystemExit(main())
