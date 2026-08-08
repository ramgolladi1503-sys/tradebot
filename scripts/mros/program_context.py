#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,re,subprocess
from pathlib import Path

SPRINT_RE=re.compile(r'^S[0-9]{3}$')
SHA256_RE=re.compile(r'^[0-9a-f]{64}$')
ROOT=Path(__file__).resolve().parents[2]
QUEUE_REF='origin/automation/mros-agent-queue-v1'

def _top(text:str,key:str):
 m=re.search(rf'(?m)^{re.escape(key)}:\s*([^\n#]+?)\s*$',text);return m.group(1).strip().strip('"\'') if m else None

def _contract_ids(contract:object,*,sprint:str)->tuple[list[str],list[str]]:
 e=[]
 if not isinstance(contract,dict):return [],['ACCEPTANCE_CONTRACT_OBJECT_REQUIRED']
 if contract.get('sprint')!=sprint:e.append('ACCEPTANCE_CONTRACT_SPRINT_MISMATCH')
 if contract.get('status')!='FROZEN':e.append('ACCEPTANCE_CONTRACT_NOT_FROZEN')
 rows=contract.get('criteria');ids=[]
 if not isinstance(rows,list) or not rows:return [],e+['ACCEPTANCE_CONTRACT_CRITERIA_INVALID']
 for i,row in enumerate(rows):
  cid=row.get('id') if isinstance(row,dict) else None
  if not isinstance(cid,str) or not cid.strip():e.append(f'ACCEPTANCE_CONTRACT_CRITERION_{i}_ID_INVALID')
  else:ids.append(cid)
 if len(ids)!=len(set(ids)):e.append('ACCEPTANCE_CONTRACT_DUPLICATE_IDS')
 return ids,e

def _expected_s003_refs(data:dict,*,sprint:str)->tuple[list[str],list[str]]:
 e=[];rr=data.get('review_round');ar=data.get('audit_round')
 if not isinstance(rr,str) or not re.fullmatch(r'R[0-9]{3}',rr):e.append('ACCEPTANCE_TRACE_REVIEW_ROUND_INVALID')
 if not isinstance(ar,str) or not re.fullmatch(r'A[0-9]{3}',ar):e.append('ACCEPTANCE_TRACE_AUDIT_ROUND_INVALID')
 if e:return [],e
 base=f'research/evidence/sprints/{sprint}'
 return [
  f'{base}/{sprint}_AUTONOMOUS_NATIVE_EVIDENCE.json',
  f'{base}/{sprint}_{rr}_REVIEW_AGGREGATE.json',
  f'{base}/{sprint}_{ar}_AUDIT_AGGREGATE.json',
  f'{base}/agent_queue/manifests/{sprint}_{rr}_REVIEW_POPULATION.json',
  f'{base}/agent_queue/manifests/{sprint}_{ar}_AUDIT_POPULATION.json',
  f'{base}/{sprint}_ACCEPTANCE_CONTRACT.json',
 ],[]

def _safe_ref(ref:str)->bool:
 p=Path(ref)
 return bool(ref) and not p.is_absolute() and '..' not in p.parts and p.as_posix()==ref

def _sha256_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def _sha256(path:Path)->str:return _sha256_bytes(path.read_bytes())
def _queue_blob(authority_root:Path,ref:str)->bytes|None:
 p=subprocess.run(['git','show',f'{QUEUE_REF}:{ref}'],cwd=authority_root,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False)
 return p.stdout if p.returncode==0 else None

def validate_acceptance_trace(data:object,*,sprint:str,candidate_head:str,contract:object|None=None,authority_root:Path|None=None,queue_root:Path|None=None,strict_contract:bool=False,verify_evidence:bool=False)->list[str]:
 e=[]
 if not isinstance(data,dict):return ['ACCEPTANCE_TRACE_OBJECT_REQUIRED']
 if data.get('schema_version')!='mros-sprint-acceptance-trace-v1':e.append('ACCEPTANCE_TRACE_SCHEMA_INVALID')
 if data.get('sprint')!=sprint:e.append('ACCEPTANCE_TRACE_SPRINT_MISMATCH')
 if data.get('candidate_head')!=candidate_head:e.append('ACCEPTANCE_TRACE_HEAD_MISMATCH')
 if data.get('authority')!='Research / R':e.append('ACCEPTANCE_TRACE_AUTHORITY_INVALID')
 if data.get('runtime_authority')!='NONE':e.append('ACCEPTANCE_TRACE_RUNTIME_AUTHORITY_INVALID')
 if data.get('m9_status')!='NOT_STARTED':e.append('ACCEPTANCE_TRACE_M9_INVALID')
 criteria=data.get('criteria');trace_ids=[]
 if not isinstance(criteria,list) or not criteria:e.append('ACCEPTANCE_TRACE_CRITERIA_INVALID')
 else:
  ids=set()
  for i,c in enumerate(criteria):
   if not isinstance(c,dict):e.append(f'ACCEPTANCE_CRITERION_{i}_INVALID');continue
   cid=c.get('id')
   if not isinstance(cid,str) or not cid.strip():e.append(f'ACCEPTANCE_CRITERION_{i}_ID_INVALID')
   elif cid in ids:e.append(f'ACCEPTANCE_CRITERION_{i}_DUPLICATE_ID')
   else:ids.add(cid);trace_ids.append(cid)
   if c.get('status')!='PASS':e.append(f'ACCEPTANCE_CRITERION_{i}_NOT_PASS')
   refs=c.get('evidence_refs')
   if not isinstance(refs,list) or not refs or any(not isinstance(x,str) or not _safe_ref(x) for x in refs):e.append(f'ACCEPTANCE_CRITERION_{i}_EVIDENCE_INVALID')
 if strict_contract:
  contract_ids,ce=_contract_ids(contract,sprint=sprint);e.extend(ce)
  if contract_ids and (len(trace_ids)!=len(contract_ids) or set(trace_ids)!=set(contract_ids)):e.append('ACCEPTANCE_TRACE_CONTRACT_IDS_MISMATCH')
  expected_refs,ref_errors=_expected_s003_refs(data,sprint=sprint);e.extend(ref_errors)
  if expected_refs and isinstance(criteria,list):
   expected_set=set(expected_refs)
   for i,c in enumerate(criteria):
    refs=c.get('evidence_refs') if isinstance(c,dict) else None
    if isinstance(refs,list) and (len(refs)!=len(expected_refs) or set(refs)!=expected_set):e.append(f'ACCEPTANCE_CRITERION_{i}_EVIDENCE_REFS_MISMATCH')
  if verify_evidence and expected_refs:
   bindings=data.get('evidence_bindings')
   if not isinstance(bindings,list):e.append('ACCEPTANCE_TRACE_EVIDENCE_BINDINGS_REQUIRED');bindings=[]
   by_path={}
   for i,b in enumerate(bindings):
    if not isinstance(b,dict):e.append(f'ACCEPTANCE_EVIDENCE_BINDING_{i}_INVALID');continue
    path=b.get('path');source=b.get('source');digest=b.get('sha256')
    if not isinstance(path,str) or not _safe_ref(path):e.append(f'ACCEPTANCE_EVIDENCE_BINDING_{i}_PATH_INVALID');continue
    if path in by_path:e.append(f'ACCEPTANCE_EVIDENCE_BINDING_{i}_DUPLICATE_PATH');continue
    if source not in {'authority','queue'}:e.append(f'ACCEPTANCE_EVIDENCE_BINDING_{i}_SOURCE_INVALID')
    if not isinstance(digest,str) or not SHA256_RE.fullmatch(digest):e.append(f'ACCEPTANCE_EVIDENCE_BINDING_{i}_SHA256_INVALID')
    by_path[path]=b
   if set(by_path)!=set(expected_refs):e.append('ACCEPTANCE_TRACE_EVIDENCE_BINDING_SET_MISMATCH')
   auth_root=Path(authority_root or ROOT).resolve()
   for ref in expected_refs:
    b=by_path.get(ref)
    if not isinstance(b,dict):continue
    expected_source='queue' if '/agent_queue/' in ref else 'authority'
    if b.get('source')!=expected_source:e.append(f'ACCEPTANCE_EVIDENCE_SOURCE_MISMATCH:{ref}')
    actual_digest=None
    if expected_source=='queue':
     if queue_root is not None:
      root=Path(queue_root).resolve();path=(root/ref).resolve()
      try:path.relative_to(root)
      except ValueError:e.append(f'ACCEPTANCE_EVIDENCE_PATH_ESCAPE:{ref}');continue
      if path.is_file():actual_digest=_sha256(path)
     else:
      blob=_queue_blob(auth_root,ref);actual_digest=_sha256_bytes(blob) if blob is not None else None
    else:
     path=(auth_root/ref).resolve()
     try:path.relative_to(auth_root)
     except ValueError:e.append(f'ACCEPTANCE_EVIDENCE_PATH_ESCAPE:{ref}');continue
     if path.is_file():actual_digest=_sha256(path)
    if actual_digest is None:e.append(f'ACCEPTANCE_EVIDENCE_FILE_MISSING:{ref}')
    elif isinstance(b.get('sha256'),str) and SHA256_RE.fullmatch(b['sha256']) and actual_digest!=b['sha256']:e.append(f'ACCEPTANCE_EVIDENCE_SHA256_MISMATCH:{ref}')
 return sorted(set(e))

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

def load_and_validate_context(*,state_path:Path,ledger_path:Path,acceptance_path:Path,sprint:str,next_sprint:str,candidate_head:str,contract_path:Path|None=None,authority_root:Path|None=None,queue_root:Path|None=None,strict_contract:bool=True,verify_evidence:bool=True)->list[str]:
 e=[]
 try:state=state_path.read_text(encoding='utf-8')
 except OSError:return ['PROGRAM_STATE_UNREADABLE']
 try:ledger=ledger_path.read_text(encoding='utf-8')
 except OSError:return ['SPRINT_LEDGER_UNREADABLE']
 try:acceptance=json.loads(acceptance_path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):return ['ACCEPTANCE_TRACE_UNREADABLE']
 contract=None
 if strict_contract:
  cp=contract_path or (ROOT/f'research/evidence/sprints/{sprint}/{sprint}_ACCEPTANCE_CONTRACT.json')
  try:contract=json.loads(Path(cp).read_text(encoding='utf-8'))
  except (OSError,json.JSONDecodeError):e.append('ACCEPTANCE_CONTRACT_UNREADABLE')
 e.extend(validate_state_ledger(state,ledger,sprint=sprint,next_sprint=next_sprint))
 e.extend(validate_acceptance_trace(acceptance,sprint=sprint,candidate_head=candidate_head,contract=contract,authority_root=authority_root or ROOT,queue_root=queue_root,strict_contract=strict_contract,verify_evidence=verify_evidence))
 return sorted(set(e))
