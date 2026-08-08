#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess
from pathlib import Path

QUEUE_REF='origin/automation/mros-agent-queue-v1'
QUEUE_ROOT=Path('research/evidence/sprints/S003/agent_queue')


def _run(repo:Path,*args:str):
 p=subprocess.run(['git',*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
 return p

def _show_json(repo:Path,ref:str,path:str):
 p=_run(repo,'show',f'{ref}:{path}')
 if p.returncode!=0:raise ValueError(f'QUEUE_GIT_OBJECT_MISSING:{path}')
 return json.loads(p.stdout)
def _path(value)->str:
 return Path(str(value)).as_posix()
def canonical_manifest_path(sprint:str,round_id:str,job_type:str)->str:
 suffix='REVIEW' if job_type=='reviewer' else 'AUDIT'
 return (QUEUE_ROOT/'manifests'/f'{sprint}_{round_id}_{suffix}_POPULATION.json').as_posix()
def canonical_request_path(member:dict)->str:
 return (QUEUE_ROOT/'requests'/Path(str(member.get('output_path',''))).name).as_posix()

def _single_origin(repo:Path,path:str)->tuple[str|None,list[str]]:
 """Return the single add-origin commit for an immutable queue artifact."""
 hist=_run(repo,'log','--format=%H',QUEUE_REF,'--',path)
 commits=[x for x in hist.stdout.splitlines() if x.strip()] if hist.returncode==0 else []
 adds=_run(repo,'log','--diff-filter=A','--format=%H',QUEUE_REF,'--',path)
 add_commits=[x for x in adds.stdout.splitlines() if x.strip()] if adds.returncode==0 else []
 errors=[]
 if len(commits)!=1:errors.append('HISTORY_NOT_IMMUTABLE')
 if len(add_commits)!=1:errors.append('ORIGIN_AMBIGUOUS')
 return (add_commits[0] if len(add_commits)==1 else None),errors

def _freeze_commit(queue_repo:Path,manifest:dict)->tuple[str|None,list[str]]:
 if not isinstance(manifest,dict):return None,['RECEIPT_MANIFEST_INVALID']
 sprint=manifest.get('sprint');round_id=manifest.get('round');job_type=manifest.get('job_type')
 if not all(isinstance(x,str) and x for x in (sprint,round_id,job_type)):return None,['RECEIPT_MANIFEST_IDENTITY_INVALID']
 rel=canonical_manifest_path(sprint,round_id,job_type)
 hist=_run(queue_repo,'log','--format=%H',QUEUE_REF,'--',rel)
 commits=[x for x in hist.stdout.splitlines() if x.strip()] if hist.returncode==0 else []
 if len(commits)!=1:return None,['RECEIPT_MANIFEST_FREEZE_AMBIGUOUS']
 return commits[0],[]

def validate_trusted_population(*,queue_repo:Path,manifest_path:Path|str,manifest:dict,candidate_head:str,sprint:str,round_id:str,job_type:str)->list[str]:
 e=[];queue_repo=Path(queue_repo).resolve();expected_rel=canonical_manifest_path(sprint,round_id,job_type)
 supplied=Path(manifest_path);supplied=(supplied if supplied.is_absolute() else queue_repo/supplied).resolve();expected=(queue_repo/expected_rel).resolve()
 if supplied!=expected:e.append('POPULATION_MANIFEST_CANONICAL_PATH_MISMATCH')
 if manifest.get('candidate_head')!=candidate_head:e.append('POPULATION_TRUST_HEAD_MISMATCH')
 if manifest.get('sprint')!=sprint:e.append('POPULATION_TRUST_SPRINT_MISMATCH')
 if manifest.get('round')!=round_id:e.append('POPULATION_TRUST_ROUND_MISMATCH')
 if manifest.get('job_type')!=job_type:e.append('POPULATION_TRUST_JOB_TYPE_MISMATCH')
 if manifest.get('frozen_before_execution') is not True:e.append('POPULATION_TRUST_NOT_FROZEN')
 p=_run(queue_repo,'rev-parse','--verify',QUEUE_REF)
 if p.returncode!=0:return e+['CANONICAL_QUEUE_REF_MISSING']
 try:remote_manifest=_show_json(queue_repo,QUEUE_REF,expected_rel)
 except Exception:return e+['CANONICAL_QUEUE_MANIFEST_MISSING']
 if remote_manifest!=manifest:e.append('POPULATION_MANIFEST_CANONICAL_CONTENT_MISMATCH')
 hist=_run(queue_repo,'log','--format=%H',QUEUE_REF,'--',expected_rel)
 commits=[x for x in hist.stdout.splitlines() if x.strip()] if hist.returncode==0 else []
 if len(commits)!=1:return e+['POPULATION_MANIFEST_NOT_IMMUTABLE_IN_GIT_HISTORY']
 freeze=commits[0]
 members=manifest.get('members') if isinstance(manifest.get('members'),list) else []
 for i,m in enumerate(members):
  if not isinstance(m,dict):e.append(f'POPULATION_TRUST_MEMBER_{i}_INVALID');continue
  req_rel=canonical_request_path(m)
  try:req=_show_json(queue_repo,QUEUE_REF,req_rel)
  except Exception:e.append(f'POPULATION_TRUST_REQUEST_{i}_MISSING');continue
  expected_fields={'candidate_sha':candidate_head,'role_id':m.get('execution_role_id'),'packet_path':m.get('packet_path'),'output_path':m.get('output_path')}
  for k,v in expected_fields.items():
   if req.get(k)!=v:e.append(f'POPULATION_TRUST_REQUEST_{i}_{k.upper()}_MISMATCH')
  rh=_run(queue_repo,'log','--diff-filter=A','--format=%H',QUEUE_REF,'--',req_rel)
  rcommits=[x for x in rh.stdout.splitlines() if x.strip()] if rh.returncode==0 else []
  if len(rcommits)!=1:e.append(f'POPULATION_TRUST_REQUEST_{i}_ORIGIN_AMBIGUOUS');continue
  anc=_run(queue_repo,'merge-base','--is-ancestor',freeze,rcommits[0])
  if anc.returncode!=0:e.append(f'POPULATION_REQUEST_{i}_PREDATES_FREEZE')
 return sorted(set(e))

def load_exact_receipts(*,queue_repo:Path,manifest:dict)->tuple[dict,list[str]]:
 queue_repo=Path(queue_repo).resolve();out={};e=[]
 freeze,freeze_errors=_freeze_commit(queue_repo,manifest);e.extend(freeze_errors)
 candidate=manifest.get('candidate_head') if isinstance(manifest,dict) else None
 for i,m in enumerate(manifest.get('members',[]) if isinstance(manifest,dict) else []):
  if not isinstance(m,dict):e.append(f'RECEIPT_MEMBER_{i}_INVALID');continue
  rel=m.get('receipt_path')
  if not isinstance(rel,str) or not rel:e.append(f'RECEIPT_MEMBER_{i}_PATH_INVALID');continue
  rel=_path(rel)
  try:r=_show_json(queue_repo,QUEUE_REF,rel)
  except Exception:e.append(f'RECEIPT_MEMBER_{i}_CANONICAL_FILE_MISSING');continue
  if not isinstance(r,dict):e.append(f'RECEIPT_MEMBER_{i}_OBJECT_REQUIRED');continue
  origin,hist_errors=_single_origin(queue_repo,rel)
  for err in hist_errors:e.append(f'RECEIPT_MEMBER_{i}_{err}')
  if freeze and origin:
   # Frozen population means identity/path are fixed before execution; receipt
   # content is created by execution and therefore must originate strictly after
   # the population-freeze commit. This preserves causal ordering without
   # allowing post-hoc role/path substitution.
   anc=_run(queue_repo,'merge-base','--is-ancestor',freeze,origin)
   same=origin==freeze
   if anc.returncode!=0 or same:e.append(f'RECEIPT_MEMBER_{i}_ORIGIN_NOT_STRICTLY_AFTER_FREEZE')
  req=r.get('request')
  if not isinstance(req,dict):e.append(f'RECEIPT_MEMBER_{i}_REQUEST_INVALID')
  else:
   expected={'candidate_sha':candidate,'role_id':m.get('execution_role_id'),'packet_path':m.get('packet_path'),'output_path':m.get('output_path')}
   for k,v in expected.items():
    if req.get(k)!=v:e.append(f'RECEIPT_MEMBER_{i}_{k.upper()}_MISMATCH')
  job=r.get('job');job_id=job.get('job_id') if isinstance(job,dict) else None
  if not isinstance(job_id,str) or not job_id:e.append(f'RECEIPT_MEMBER_{i}_JOB_ID_INVALID');continue
  if job_id in out:e.append('RECEIPT_JOB_ID_DUPLICATE');continue
  r=dict(r);r['_frozen_receipt_path']=rel;out[job_id]=r
 return out,sorted(set(e))
