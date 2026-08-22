from tep.evidence_store import FileEvidenceStore
from tep.kernel import EvidenceRecord
from tep.recovery import *
from hashlib import sha256
import pytest
def test_evidence_seal_and_verified_recovery(tmp_path):
 b=b'proof';h=sha256(b).hexdigest();r=EvidenceRecord('e','claim','p','v','sha','ref',h);p=FileEvidenceStore(tmp_path/'e').seal(r,b);verified_copy(p,tmp_path/'copy',h);assert file_hash(tmp_path/'copy')==h
def test_bad_recovery_hash_fails(tmp_path):
 p=tmp_path/'x';p.write_bytes(b'x')
 with pytest.raises(RecoveryError):verified_copy(p,tmp_path/'y','0'*64)
