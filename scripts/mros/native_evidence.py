#!/usr/bin/env python3
from __future__ import annotations
import hashlib,posixpath,re
from datetime import datetime
SHA_RE=re.compile(r'^[0-9a-f]{40}$');SHA64_RE=re.compile(r'^[0-9a-f]{64}$');JOB_RE=re.compile(r'^[0-9a-f]{32}$');PY_RE=re.compile(r'^\d+\.\d+\.\d+$')
REPOSITORY='ramgolladi1503-sys/tradebot';BRANCH='research/mros-program-v1'
REQUIRED=('schema_version','evidence_kind','repository','branch','head','validator','python_version','command','checks','passed','failed','exit_code','timestamp','transport','execution_job_id','execution_receipt_ref','source_output_ref','source_output_sha256','runtime_authority','broker_actions')

def _canonical_repo_ref(value:object)->str|None:
 if not isinstance(value,str) or not value.strip():return None
 v=value.strip().replace('\\','/')
 if v.startswith('/') or re.match(r'^[A-Za-z]:/',v):return None
 norm=posixpath.normpath(v)
 if norm in {'.','..'} or norm.startswith('../') or '/..' in '/'+norm:return None
 return norm

def validate_native_evidence(data:object,candidate_head:str)->list[str]:
 e=[]
 if not isinstance(data,dict):return ['NATIVE_EVIDENCE_OBJECT_REQUIRED']
 for k in REQUIRED:
  if k not in data:e.append('NATIVE_MISSING:'+k)
 if e:return e
 if data.get('schema_version')!='mros-native-evidence-v2':e.append('NATIVE_SCHEMA_INVALID')
 if data.get('evidence_kind')!='native_validation':e.append('NATIVE_KIND_INVALID')
 if data.get('repository')!=REPOSITORY:e.append('NATIVE_REPOSITORY_MISMATCH')
 if data.get('branch')!=BRANCH:e.append('NATIVE_BRANCH_MISMATCH')
 head=data.get('head')
 if not isinstance(head,str) or not SHA_RE.fullmatch(head):e.append('NATIVE_HEAD_INVALID')
 elif head!=candidate_head:e.append('NATIVE_HEAD_MISMATCH')
 validator=data.get('validator');command=data.get('command')
 if not isinstance(validator,str) or not validator.startswith('scripts/mros/') or not validator.endswith('.py'):e.append('NATIVE_VALIDATOR_INVALID')
 if not isinstance(command,str) or not command.strip():e.append('NATIVE_COMMAND_INVALID')
 elif isinstance(validator,str) and validator not in command:e.append('NATIVE_COMMAND_VALIDATOR_MISMATCH')
 if not isinstance(data.get('python_version'),str) or not PY_RE.fullmatch(data['python_version']):e.append('NATIVE_PYTHON_VERSION_INVALID')
 for k in ('checks','passed','failed','exit_code'):
  v=data.get(k)
  if isinstance(v,bool) or not isinstance(v,int):e.append(f'NATIVE_{k.upper()}_TYPE_INVALID')
 if all(isinstance(data.get(k),int) and not isinstance(data.get(k),bool) for k in ('checks','passed','failed','exit_code')):
  checks,passed,failed,exit_code=data['checks'],data['passed'],data['failed'],data['exit_code']
  if checks<=0:e.append('NATIVE_CHECKS_NONPOSITIVE')
  if passed<0 or failed<0 or passed+failed!=checks:e.append('NATIVE_COUNTS_INCONSISTENT')
  if failed!=0 or passed!=checks or exit_code!=0:e.append('NATIVE_VALIDATION_NOT_PASS')
 ts=data.get('timestamp')
 if not isinstance(ts,str) or not ts.strip():e.append('NATIVE_TIMESTAMP_INVALID')
 else:
  try:datetime.fromisoformat(ts.replace('Z','+00:00'))
  except ValueError:e.append('NATIVE_TIMESTAMP_INVALID')
 if data.get('transport')!='mac_git_mailbox':e.append('NATIVE_TRANSPORT_INVALID')
 if not JOB_RE.fullmatch(str(data.get('execution_job_id',''))):e.append('NATIVE_EXECUTION_JOB_INVALID')
 for k in ('execution_receipt_ref','source_output_ref'):
  if _canonical_repo_ref(data.get(k)) is None:e.append(f'NATIVE_{k.upper()}_INVALID')
 if not SHA64_RE.fullmatch(str(data.get('source_output_sha256',''))):e.append('NATIVE_SOURCE_OUTPUT_SHA256_INVALID')
 if data.get('runtime_authority')!='NONE':e.append('NATIVE_RUNTIME_AUTHORITY_INVALID')
 if data.get('broker_actions')!='NONE':e.append('NATIVE_BROKER_BOUNDARY_INVALID')
 return e

def verify_native_sources(data:dict,*,source_output_text:str,receipt:dict,candidate_head:str,source_output_ref:str|None=None,execution_receipt_ref:str|None=None)->list[str]:
 e=validate_native_evidence(data,candidate_head)
 if e:return e
 declared_source=_canonical_repo_ref(data.get('source_output_ref'));declared_receipt=_canonical_repo_ref(data.get('execution_receipt_ref'))
 actual_source=_canonical_repo_ref(source_output_ref);actual_receipt=_canonical_repo_ref(execution_receipt_ref)
 if actual_source is None:e.append('NATIVE_SOURCE_OUTPUT_ACTUAL_REF_REQUIRED')
 elif declared_source!=actual_source:e.append('NATIVE_SOURCE_OUTPUT_REF_MISMATCH')
 if actual_receipt is None:e.append('NATIVE_EXECUTION_RECEIPT_ACTUAL_REF_REQUIRED')
 elif declared_receipt!=actual_receipt:e.append('NATIVE_EXECUTION_RECEIPT_REF_MISMATCH')
 actual=hashlib.sha256(source_output_text.encode('utf-8')).hexdigest()
 if actual!=data['source_output_sha256']:e.append('NATIVE_SOURCE_OUTPUT_HASH_MISMATCH')
 job=receipt.get('job') if isinstance(receipt,dict) else None;req=receipt.get('request') if isinstance(receipt,dict) else None
 if not isinstance(job,dict) or not isinstance(req,dict):return e+['NATIVE_RECEIPT_INVALID']
 if receipt.get('runtime_authority')!='NONE' or receipt.get('broker_actions_allowed') is not False:e.append('NATIVE_RECEIPT_BOUNDARY_INVALID')
 if job.get('job_id')!=data['execution_job_id']:e.append('NATIVE_RECEIPT_JOB_ID_MISMATCH')
 if job.get('candidate_sha')!=candidate_head or req.get('candidate_sha')!=candidate_head:e.append('NATIVE_RECEIPT_HEAD_MISMATCH')
 if job.get('state')!='SUCCEEDED' or job.get('exit_code')!=0:e.append('NATIVE_RECEIPT_JOB_NOT_SUCCESSFUL')
 return e

def native_pass(data:object,candidate_head:str)->bool:return not validate_native_evidence(data,candidate_head)
