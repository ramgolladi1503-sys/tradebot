"""M5 immutable evidence files plus transactional index-by-hash."""
from pathlib import Path
from hashlib import sha256
import json,os,tempfile
from .kernel import EvidenceRecord
from .evidence import EvidenceError
class FileEvidenceStore:
 def __init__(self,root):self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
 def seal(self,record:EvidenceRecord,payload:bytes):
  if record.producer==record.validator:raise EvidenceError('independent validator required')
  h=sha256(payload).hexdigest()
  if h!=record.artifact_hash:raise EvidenceError('artifact hash mismatch')
  target=self.root/f'{record.evidence_id}.bin';meta=self.root/f'{record.evidence_id}.json'
  if target.exists():
   if sha256(target.read_bytes()).hexdigest()!=h:raise EvidenceError('immutable evidence collision')
   return target
  fd,tmp=tempfile.mkstemp(dir=self.root,prefix='.seal-')
  try:
   with os.fdopen(fd,'wb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
   os.replace(tmp,target)
   m={'evidence_id':record.evidence_id,'claim':record.claim,'producer':record.producer,'validator':record.validator,'source_authority':record.source_authority,'artifact_ref':str(target),'artifact_hash':h,'limitations':list(record.limitations)}
   meta.write_text(json.dumps(m,sort_keys=True,indent=2));return target
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
