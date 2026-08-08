#!/usr/bin/env python3
"""Deterministic exact-head native validation for autonomous MROS S004-S110."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
AUTH='research/mros-program-v1'
class NativeError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout:int=3600,check=True,env=None):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False,env=env)
 if check and p.returncode!=0:raise NativeError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)

def validate(repo:Path,state_root:Path,sprint:str,candidate:str)->dict:
 if not sprint.startswith('S') or len(sprint)!=4:raise NativeError('SPRINT_INVALID')
 root=state_root/'native-validation-worktrees';root.mkdir(parents=True,exist_ok=True);wt=root/f'{sprint}-{candidate[:8]}'
 if wt.exists():git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True)
 git(repo,'fetch','origin',AUTH,timeout=300);git(repo,'cat-file','-e',f'{candidate}^{{commit}}')
 git(repo,'worktree','add','--detach',str(wt),candidate,timeout=300)
 try:
  env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['MROS_RUNTIME_AUTHORITY']='NONE';env['MROS_BROKER_ACTIONS_ALLOWED']='0'
  pyver=run(wt,'python3','--version',env=env).stdout.strip()
  commands=[];outputs=[];passed=True
  # Compile without writing bytecode by using compile() on source text.
  scripts=sorted((wt/'scripts/mros').glob('*.py')) if (wt/'scripts/mros').is_dir() else []
  compile_code="import pathlib; files=[pathlib.Path(p) for p in __import__('sys').argv[1:]]; [compile(p.read_text(encoding='utf-8'),str(p),'exec') for p in files]; print('IN_MEMORY_COMPILE_PASS',len(files))"
  c=['python3','-c',compile_code,*[str(p.relative_to(wt)) for p in scripts]];r=run(wt,*c,timeout=600,check=False,env=env);commands.append(' '.join(c[:3])+' <scripts/mros/*.py>');outputs.append(r.stdout);passed &= r.returncode==0
  # Full MROS regression suite in writable detached worktree.
  tests=wt/'tests/mros'
  if tests.is_dir():
   c=['python3','-m','pytest','-q','tests/mros'];r=run(wt,*c,timeout=3600,check=False,env=env);commands.append(' '.join(c));outputs.append(r.stdout);passed &= r.returncode==0
  # Sprint-specific validator if implementer provided one.
  sv=wt/f'scripts/mros/validate_{sprint.lower()}.py'
  if sv.is_file():
   c=['python3',str(sv.relative_to(wt))];r=run(wt,*c,timeout=1800,check=False,env=env);commands.append(' '.join(c));outputs.append(r.stdout);passed &= r.returncode==0
  text='\n\n'.join(f'$ {cmd}\n{out}' for cmd,out in zip(commands,outputs));digest=hashlib.sha256(text.encode()).hexdigest()
  return {'schema_version':'mros-program-native-run-v1','sprint':sprint,'candidate_head':candidate,'python_version':pyver.replace('Python ','').strip(),'commands':commands,'output':text,'output_sha256':digest,'exit_code':0 if passed else 1,'result':'PASS' if passed else 'FAIL','runtime_authority':'NONE','broker_actions':'NONE','executed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 finally:
  git(repo,'worktree','remove','--force',str(wt),check=False);shutil.rmtree(wt,ignore_errors=True);git(repo,'worktree','prune',check=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);p.add_argument('--sprint',required=True);p.add_argument('--candidate',required=True);a=p.parse_args()
 try:print(json.dumps(validate(a.repo.resolve(),a.state_root.resolve(),a.sprint,a.candidate),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'NATIVE_VALIDATION_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
