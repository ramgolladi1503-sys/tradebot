"""Versioned mission configuration; secrets are references, never values."""
from dataclasses import dataclass
from .kernel import canonical_hash
@dataclass(frozen=True)
class TEPConfig:
 runtime_root:str;evidence_root:str;state_db:str;secret_refs:tuple[str,...]=();poll_seconds:int=30;lease_seconds:int=120
 @property
 def fingerprint(self):return canonical_hash({'runtime_root':self.runtime_root,'evidence_root':self.evidence_root,'state_db':self.state_db,'secret_refs':self.secret_refs,'poll_seconds':self.poll_seconds,'lease_seconds':self.lease_seconds})
 def validate(self):
  if self.poll_seconds<=0 or self.lease_seconds<=0:raise ValueError('positive timing required')
  for ref in self.secret_refs:
   if '=' in ref or '\n' in ref:raise ValueError('secret_refs must be opaque references')
  return self
