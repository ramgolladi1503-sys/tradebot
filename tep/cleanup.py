"""M6 cleanup safety predicates. Age/disk pressure never prove deletion safety."""
from dataclasses import dataclass
@dataclass(frozen=True)
class CleanupCandidate:
 path:str;tracked_elsewhere:bool;untracked_files:bool;local_only_commits:bool;active_process_role:bool;unresolved_pr_mapping:bool;unique_evidence:bool;credential_material:bool
 @property
 def safe(self):return self.tracked_elsewhere and not any((self.untracked_files,self.local_only_commits,self.active_process_role,self.unresolved_pr_mapping,self.unique_evidence,self.credential_material))
def require_safe(c):
 if not c.safe:raise PermissionError('destructive cleanup not proven safe')
 return c
