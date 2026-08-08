#!/usr/bin/env python3
from __future__ import annotations
import re
SHA=re.compile(r'^[0-9a-f]{40}$')
RID={'reviewer':re.compile(r'^R[0-9]{2,3}$'),'auditor':re.compile(r'^A[0-9]{2,3}$')}
ROUND={'reviewer':re.compile(r'^R[0-9]{3}$'),'auditor':re.compile(r'^A[0-9]{3}$')}

def validate_population_manifest(data:object,*,candidate_head:str,job_type:str)->list[str]:
 e=[]
 if not isinstance(data,dict):return ['POPULATION_MANIFEST_OBJECT_REQUIRED']
 if data.get('schema_version')!='mros-agent-population-v1':e.append('POPULATION_SCHEMA_INVALID')
 if data.get('job_type')!=job_type:e.append('POPULATION_JOB_TYPE_MISMATCH')
 if data.get('candidate_head')!=candidate_head or not SHA.fullmatch(str(data.get('candidate_head',''))):e.append('POPULATION_HEAD_MISMATCH')
 if not re.fullmatch(r'S[0-9]{3}',str(data.get('sprint',''))):e.append('POPULATION_SPRINT_INVALID')
 if not ROUND[job_type].fullmatch(str(data.get('round',''))):e.append('POPULATION_ROUND_INVALID')
 if data.get('frozen_before_execution') is not True:e.append('POPULATION_NOT_FROZEN')
 members=data.get('members')
 if not isinstance(members,list):return e+['POPULATION_MEMBERS_INVALID']
 expected=data.get('expected_count')
 if isinstance(expected,bool) or not isinstance(expected,int) or expected<10:e.append('POPULATION_EXPECTED_COUNT_INVALID')
 elif expected!=len(members):e.append('POPULATION_COUNT_MISMATCH')
 seen={k:set() for k in ('execution_role_id','semantic_role','packet_path','output_path','receipt_path')}
 for i,m in enumerate(members):
  if not isinstance(m,dict):e.append(f'POPULATION_MEMBER_{i}_INVALID');continue
  for k in seen:
   v=m.get(k)
   if not isinstance(v,str) or not v.strip():e.append(f'POPULATION_MEMBER_{i}_{k.upper()}_INVALID');continue
   if v in seen[k]:e.append(f'POPULATION_MEMBER_{i}_{k.upper()}_DUPLICATE')
   seen[k].add(v)
  rid=m.get('execution_role_id')
  if isinstance(rid,str) and not RID[job_type].fullmatch(rid):e.append(f'POPULATION_MEMBER_{i}_ROLE_ID_INVALID')
 return e

def reconcile_population(manifest:dict,artifacts:list[dict])->dict:
 expected={m['output_path']:m for m in manifest['members']}
 submitted={a.get('output_path'):a for a in artifacts if isinstance(a,dict) and isinstance(a.get('output_path'),str)}
 return {
  'expected':len(expected),'submitted':len(submitted),
  'omitted':sorted(set(expected)-set(submitted)),
  'extra':sorted(set(submitted)-set(expected)),
  'expected_members':expected,
 }
