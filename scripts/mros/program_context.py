#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path

SPRINT_RE=re.compile(r'^S[0-9]{3}$')

def _top(text:str,key:str):
 m=re.search(rf'(?m)^{re.escape(key)}:\s*([^\n#]+?)\s*$',text);return m.group(1).strip().strip('"\'') if m else None

def validate_acceptance_trace(data:object,*,sprint:str,candidate_head:str)->list[str]:
 e=[]
 if not isinstance(data,dict):return ['ACCEPTANCE_TRACE_OBJECT_REQUIRED']
 if data.get('schema_version')!='mros-sprint-acceptance-trace-v1':e.append('ACCEPTANCE_TRACE_SCHEMA_INVALID')
 if data.get('sprint')!=sprint:e.append('ACCEPTANCE_TRACE_SPRINT_MISMATCH')
 if data.get('candidate_head')!=candidate_head:e.append('ACCEPTANCE_TRACE_HEAD_MISMATCH')
 if data.get('authority')!='Research / R':e.append('ACCEPTANCE_TRACE_AUTHORITY_INVALID')
 if data.get('runtime_authority')!='NONE':e.append('ACCEPTANCE_TRACE_RUNTIME_AUTHORITY_INVALID')
 if data.get('m9_status')!='NOT_STARTED':e.append('ACCEPTANCE_TRACE_M9_INVALID')
 criteria=data.get('criteria')
 if not isinstance(criteria,list) or not criteria:e.append('ACCEPTANCE_TRACE_CRITERIA_INVALID')
 else:
  ids=set()
  for i,c in enumerate(criteria):
   if not isinstance(c,dict):e.append(f'ACCEPTANCE_CRITERION_{i}_INVALID');continue
   cid=c.get('id')
   if not isinstance(cid,str) or not cid.strip():e.append(f'ACCEPTANCE_CRITERION_{i}_ID_INVALID')
   elif cid in ids:e.append(f'ACCEPTANCE_CRITERION_{i}_DUPLICATE_ID')
   ids.add(cid)
   if c.get('status')!='PASS':e.append(f'ACCEPTANCE_CRITERION_{i}_NOT_PASS')
   refs=c.get('evidence_refs')
   if not isinstance(refs,list) or not refs or any(not isinstance(x,str) or not x.strip() for x in refs):e.append(f'ACCEPTANCE_CRITERION_{i}_EVIDENCE_INVALID')
 return e

def validate_state_ledger(state_text:str,ledger_text:str,*,sprint:str,next_sprint:str)->list[str]:
 e=[]
 if _top(state_text,'active_sprint')!=sprint:e.append('PROGRAM_STATE_ACTIVE_SPRINT_MISMATCH')
 if not SPRINT_RE.fullmatch(next_sprint):e.append('PROGRAM_STATE_NEXT_SPRINT_INVALID')
 elif int(next_sprint[1:])>=111:e.append('M9_HARD_STOP')
 if not re.search(r'(?m)^\s*M9:\s*NOT_STARTED\s*$',state_text):e.append('PROGRAM_STATE_M9_NOT_NOT_STARTED')
 runtime_values=re.findall(r'(?m)^\s*runtime_authority:\s*([^\n#]+?)\s*$',state_text)
 if not runtime_values or any(v.strip().strip('"\'')!='NONE' for v in runtime_values):e.append('PROGRAM_STATE_RUNTIME_AUTHORITY_NOT_NONE')
 rows=[]
 for i,line in enumerate(ledger_text.splitlines(),1):
  if not line.strip():continue
  try:r=json.loads(line)
  except json.JSONDecodeError:e.append(f'SPRINT_LEDGER_JSON_INVALID:{i}');continue
  if isinstance(r,dict):rows.append(r)
 current=[r for r in rows if r.get('sprint_id')==sprint]
 if not current:e.append('SPRINT_LEDGER_CURRENT_SPRINT_MISSING')
 elif current[-1].get('decision')=='ACCEPTED':e.append('SPRINT_LEDGER_ALREADY_ACCEPTED')
 current_num=int(sprint[1:]) if SPRINT_RE.fullmatch(sprint) else -1
 for r in rows:
  sid=r.get('sprint_id')
  if isinstance(sid,str) and SPRINT_RE.fullmatch(sid) and int(sid[1:])>current_num and r.get('decision') in {'ACTIVE','ACCEPTED','PASS'}:
   e.append('SPRINT_LEDGER_FUTURE_ADVANCEMENT_PRESENT');break
 return e

def load_and_validate_context(*,state_path:Path,ledger_path:Path,acceptance_path:Path,sprint:str,next_sprint:str,candidate_head:str)->list[str]:
 e=[]
 try:state=state_path.read_text(encoding='utf-8')
 except OSError:return ['PROGRAM_STATE_UNREADABLE']
 try:ledger=ledger_path.read_text(encoding='utf-8')
 except OSError:return ['SPRINT_LEDGER_UNREADABLE']
 try:acceptance=json.loads(acceptance_path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):return ['ACCEPTANCE_TRACE_UNREADABLE']
 e.extend(validate_state_ledger(state,ledger,sprint=sprint,next_sprint=next_sprint))
 e.extend(validate_acceptance_trace(acceptance,sprint=sprint,candidate_head=candidate_head))
 return e
