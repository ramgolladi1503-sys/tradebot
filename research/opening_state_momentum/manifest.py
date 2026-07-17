import hashlib
import json
from typing import List, Dict, Any

def compute_portable_hash(stable_files: List[Dict[str, Any]]) -> str:
    # Sort files by relative path for determinism
    sorted_files = sorted(stable_files, key=lambda x: x.get("relative_path", ""))
    manifest_lines = []
    for f in sorted_files:
        line = (
            f"{f.get('data_family', 'unknown')}|"
            f"{f.get('relative_path', '')}|"
            f"{f.get('sha256', '')}|"
            f"{f.get('size_bytes', 0)}|"
            f"{f.get('row_count', 0)}|"
            f"{f.get('min_timestamp', '')}|"
            f"{f.get('max_timestamp', '')}|"
            f"{f.get('schema_fingerprint', '')}"
        )
        manifest_lines.append(line)
    manifest_content = "\n".join(manifest_lines)
    return hashlib.sha256(manifest_content.encode("utf-8")).hexdigest()

def compute_local_hash(stable_files: List[Dict[str, Any]]) -> str:
    sorted_files = sorted(stable_files, key=lambda x: x.get("absolute_path", ""))
    manifest_lines = []
    for f in sorted_files:
        line = (
            f"{f.get('absolute_path', '')}|"
            f"{f.get('source_root', '')}|"
            f"{f.get('inode', '')}|"
            f"{f.get('pre_scan_mtime', 0.0)}|"
            f"{f.get('size_bytes', 0)}|"
            f"{f.get('sha256', '')}"
        )
        manifest_lines.append(line)
    manifest_content = "\n".join(manifest_lines)
    return hashlib.sha256(manifest_content.encode("utf-8")).hexdigest()
