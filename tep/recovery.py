"""M10 backup verification and fail-closed recovery primitives."""
from hashlib import sha256
from pathlib import Path
import shutil
class RecoveryError(RuntimeError):pass
def file_hash(path):return sha256(Path(path).read_bytes()).hexdigest()
def verified_copy(source,destination,expected_hash):
 if file_hash(source)!=expected_hash:raise RecoveryError('source hash mismatch')
 shutil.copy2(source,destination)
 if file_hash(destination)!=expected_hash:raise RecoveryError('destination verification failed')
 return destination
