#!/usr/bin/env python3
"""Turn a failed exact-head S003 calibration into a bounded autonomous repair."""
from __future__ import annotations
import argparse,json,re,subprocess,sys
from pathlib import Path
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1';ROOT=Path('research/evidence/sprints/S003/agent_queue')
class CalibrationRepairError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout=5400,check=True):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise CalibrationRepairError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def read_json(p:Path):return json.loads(p.read_text(encoding='utf-8'))
def commit(auth:Path,paths:list[Path],message:str):
 bridge=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros').resolve()
 if str(bridge) not in sys.path:sys.path.insert(0,str(bridge))
 from mros_state_transition_engine import commit_transition
 parent=git(auth,'rev-parse','HEAD').stdout.strip();return commit_transition(repo=auth,lock_path=Path.home()/'.mros-agent-bridge/state/authority-writer.lock',expected_parent=parent,changed_paths=[p.as_posix() for p in paths],message=message).commit_sha
def latest_failed(q:Path,candidate:str):
 rows=[];d=q/ROOT/'requests'
 for rp in sorted(d.glob('*CALIBRATION*.json')) if d.is_dir() else []:
  try:req=read_json(rp)
  except Exception:continue
  if req.get('candidate_sha')!=candidate:continue
  rec=q/ROOT/'receipts'/rp.name;out=q/str(req.get('output_path',''))
  if not rec.is_file() or not out.is_file():continue
  try:r=read_json(rec);job=r.get('job',{})
  except Exception:continue
  text=out.read_text(encoding='utf-8',errors='replace')
  if job.get('state')=='SUCCEEDED' and job.get('exit_code')==0 and 'CALIBRATION_EXECUTION_RESULT=FAIL' in text:rows.append((float(job.get('finished_at') or 0),rp,req,rec,text,job))
  elif 'S003_BOARD_DETERMINISTIC_CALIBRATION_FAIL' in text:rows.append((float(job.get('finished_at') or 0),rp,req,rec,text,job))
 if not rows:raise CalibrationRepairError('NO_EXACT_HEAD_CALIBRATION_FAILURE')
 return sorted(rows,key=lambda x:x[0])[-1]
def generation(auth:Path):
 nums=[];d=auth/'research/evidence/sprints/S003'
 for p in d.glob('AUTONOMOUS_REPAIR_G*_*.json') if d.is_dir() else []:
  m=re.search(r'_G(\d+)_',p.name)
  if m:nums.append(int(m.group(1)))
 return max(nums,default=0)+1
def main():
 p=argparse.ArgumentParser();p.add_argument('--authority-repo',required=True,type=Path);p.add_argument('--queue-repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);a=p.parse_args();auth=a.authority_repo.resolve();q=a.queue_repo.resolve()
 try:
  git(auth,'fetch','origin',AUTH,QUEUE,timeout=300);git(q,'fetch','origin',QUEUE,AUTH,timeout=300);git(auth,'merge','--ff-only',f'origin/{AUTH}');git(q,'rebase',f'origin/{QUEUE}');candidate=git(auth,'rev-parse','HEAD').stdout.strip();_,rp,req,rec,text,job=latest_failed(q,candidate);gen=generation(auth)
  if gen>5:raise CalibrationRepairError('ARCHITECTURAL_REVIEW_REQUIRED:REPAIR_GENERATION_LIMIT_EXCEEDED')
  failed_cases=[]
  for line in text.splitlines():
   m=re.match(r'FAIL\s*\|\s*(CAL-\d+)\s*\|\s*(.*)',line)
   if m:failed_cases.append({'case_id':m.group(1),'observed':m.group(2)})
  cp=Path(f'research/evidence/sprints/S003/S003_CALIBRATION_FAILURE_REPAIR_G{gen}.json');contract={'schema_version':'mros-repair-contract-v2','sprint':'S003','failed_head':candidate,'source_kind':'native_calibration','source_round':str(req.get('role_id')),'aggregate_decision':'CALIBRATION_FAIL','blocking_findings':[{'finding_id':f"CAL-{x['case_id']}",'severity':'MAJOR','requirement':'All frozen calibration cases and declared metrics must pass on the exact candidate head.','evidence':x['observed'],'falsifier':'The same frozen case passes on the repaired exact head without weakening its expected result.','recommended_repair_scope':'Repair the implementation or contract inconsistency causing this frozen calibration failure; do not change expected outcomes.'} for x in failed_cases] or [{'finding_id':'CALIBRATION-FAIL','severity':'MAJOR','requirement':'Exact-head deterministic Board calibration must pass all frozen cases and metrics.','evidence':text[-6000:],'falsifier':'Repaired exact head returns S003_BOARD_DETERMINISTIC_CALIBRATION_PASS with exit 0.','recommended_repair_scope':'Diagnose and repair the failed calibration without weakening fixtures, metrics, schemas, or authority boundaries.'}],'root_cause_instruction':'Repair the smallest common cause; preserve adaptive routine assurance and full final Board authorization.','repair_scope':{'allowed':['scripts/mros/','tests/mros/','research/review_board/','research/audit_board/'],'forbidden':['research/program/','TradeBot runtime/strategy/risk/execution/broker','weaken calibration expected results','begin M9','create runtime authority']},'runtime_authority':'NONE','m9_status':'NOT_STARTED'}
  (auth/cp).write_text(json.dumps(contract,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit(auth,[cp],f'mros(S003): record autonomous calibration failure repair contract G{gen} [skip ci]')
  script=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_autonomous_repair_executor.py');r=run(auth,sys.executable,str(script),'--repo',str(auth),'--state-root',str(a.state_root.resolve()),'--repair-contract',str(auth/cp),'--generation',str(gen),check=False)
  try:result=json.loads((r.stdout or '').splitlines()[-1])
  except Exception:raise CalibrationRepairError('REPAIR_EXECUTOR_INVALID_OUTPUT')
  if r.returncode!=0 or result.get('status')!='REPAIR_PUBLISHED':raise CalibrationRepairError('REPAIR_EXECUTOR_BLOCKED:'+str(result.get('error')))
  print(json.dumps({'status':'CALIBRATION_FAILURE_REPAIRED','generation':gen,'old_candidate':candidate,'new_candidate':result.get('candidate_head'),'repair_contract':cp.as_posix(),'runtime_authority':'NONE'},sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'CALIBRATION_REPAIR_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
