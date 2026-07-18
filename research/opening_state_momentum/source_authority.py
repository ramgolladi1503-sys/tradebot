import json
import hashlib
import os
from dataclasses import dataclass
from typing import Dict, Optional

class SourceAuthorityError(Exception):
    pass

@dataclass
class SourceAuthority:
    manifest_hash: str
    logical_identities: Dict[str, str]  # logical_id -> actual file path
    file_hashes: Dict[str, str]         # logical_id -> sha256 hash
    repo_root: str
    
    @classmethod
    def load(cls, manifest_path: str, repo_root: str) -> "SourceAuthority":
        try:
            with open(manifest_path, "rb") as f:
                content = f.read()
                data = json.loads(content.decode("utf-8"))
        except Exception as e:
            raise SourceAuthorityError(f"Failed to load source manifest: {e}")
            
        manifest_hash = hashlib.sha256(content).hexdigest()
        
        logical_identities = {}
        file_hashes = {}
        
        for record in data.get("stable_files", []):
            instruments = record.get("instruments", [])
            min_ts = record.get("min_timestamp")
            if not instruments or not min_ts:
                continue
                
            date_str = min_ts[:10].replace("-", "")
            
            for inst in instruments:
                logical_id = f"{inst}_{date_str}"
                if logical_id in logical_identities:
                    raise SourceAuthorityError(f"Duplicate logical identity: {logical_id}")
                    
                # Store the absolute_path from the manifest
                logical_identities[logical_id] = record["absolute_path"]
                file_hashes[logical_id] = record["sha256"]
            
        return cls(
            manifest_hash=manifest_hash,
            logical_identities=logical_identities,
            file_hashes=file_hashes,
            repo_root=repo_root
        )
        
    def resolve_source(self, logical_id: str) -> str:
        if logical_id not in self.logical_identities:
            raise SourceAuthorityError(f"Unknown logical identity: {logical_id}")
            
        path = self.logical_identities[logical_id]
        expected_hash = self.file_hashes[logical_id]
        
        if not os.path.exists(path):
            raise SourceAuthorityError(f"Source file missing: {path}")
            
        # Verify hash before returning
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
                
        actual_hash = sha256.hexdigest()
        if actual_hash != expected_hash:
            raise SourceAuthorityError(f"Hash mismatch for {logical_id}. Expected {expected_hash}, got {actual_hash}")
            
        return path
