import os
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple, Optional
from .models import FileInventory
from .schema_detection import detect_parquet_metadata
from .quality_checks import check_ohlcv_file

def hash_file_streaming(filepath: Path) -> Tuple[str, int]:
    sha256 = hashlib.sha256()
    size = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
            size += len(chunk)
    return sha256.hexdigest(), size

def scan_single_file(absolute_path: str, source_root: str, relative_path: str) -> FileInventory:
    path = Path(absolute_path)
    
    # 1. Pre-read stats
    try:
        stat_pre = path.stat()
        pre_mtime = stat_pre.st_mtime
        pre_size = stat_pre.st_size
        inode = stat_pre.st_ino
    except Exception as e:
        return FileInventory(
            absolute_path=absolute_path,
            source_root=source_root,
            relative_path=relative_path,
            inode=None,
            size_bytes=0,
            pre_scan_mtime=0.0,
            post_scan_mtime=0.0,
            pre_scan_size=0,
            post_scan_size=0,
            stability="UNREADABLE",
            error=str(e)
        )
        
    if pre_size == 0:
        return FileInventory(
            absolute_path=absolute_path,
            source_root=source_root,
            relative_path=relative_path,
            inode=inode,
            size_bytes=0,
            pre_scan_mtime=pre_mtime,
            post_scan_mtime=pre_mtime,
            pre_scan_size=0,
            post_scan_size=0,
            stability="EMPTY_FILE",
            is_empty=True
        )

    # 2. Hashing (Streaming)
    try:
        sha_hash, read_size = hash_file_streaming(path)
    except Exception as e:
        return FileInventory(
            absolute_path=absolute_path,
            source_root=source_root,
            relative_path=relative_path,
            inode=inode,
            size_bytes=pre_size,
            pre_scan_mtime=pre_mtime,
            post_scan_mtime=pre_mtime,
            pre_scan_size=pre_size,
            post_scan_size=pre_size,
            stability="UNREADABLE",
            error=str(e)
        )

    # 3. Read metadata/schema
    parquet_meta = detect_parquet_metadata(absolute_path) if path.suffix == ".parquet" else {}
    
    # 4. Post-read stats
    try:
        stat_post = path.stat()
        post_mtime = stat_post.st_mtime
        post_size = stat_post.st_size
    except Exception as e:
        return FileInventory(
            absolute_path=absolute_path,
            source_root=source_root,
            relative_path=relative_path,
            inode=inode,
            size_bytes=pre_size,
            pre_scan_mtime=pre_mtime,
            post_scan_mtime=pre_mtime,
            pre_scan_size=pre_size,
            post_scan_size=pre_size,
            stability="UNREADABLE",
            error=str(e)
        )

    # 5. Stability check
    if pre_mtime != post_mtime or pre_size != post_size:
        return FileInventory(
            absolute_path=absolute_path,
            source_root=source_root,
            relative_path=relative_path,
            inode=inode,
            size_bytes=post_size,
            pre_scan_mtime=pre_mtime,
            post_scan_mtime=post_mtime,
            pre_scan_size=pre_size,
            post_scan_size=post_size,
            stability="UNSTABLE_CHANGED_DURING_SCAN"
        )
        
    stability = "STABLE_INCLUDED"
    if parquet_meta.get("error"):
        stability = "UNSUPPORTED_SCHEMA"
        
    # Extract session date from filename or metadata
    from .quality_checks import parse_date_from_filename
    session_date = parse_date_from_filename(path.name) or ""
        
    return FileInventory(
        absolute_path=absolute_path,
        source_root=source_root,
        relative_path=relative_path,
        inode=inode,
        size_bytes=post_size,
        pre_scan_mtime=pre_mtime,
        post_scan_mtime=post_mtime,
        pre_scan_size=pre_size,
        post_scan_size=post_size,
        stability=stability,
        sha256=sha_hash,
        row_count=parquet_meta.get("row_count", 0),
        row_group_count=parquet_meta.get("row_group_count", 0),
        schema_dict=parquet_meta.get("schema_dict", {}),
        schema_fingerprint=parquet_meta.get("schema_fingerprint", ""),
        min_timestamp=parquet_meta.get("min_timestamp"),
        max_timestamp=parquet_meta.get("max_timestamp"),
        timezone=parquet_meta.get("timezone", "UNKNOWN"),
        instruments=parquet_meta.get("instruments", []),
        session_date=session_date,
        data_family=parquet_meta.get("data_family", "unknown"),
        error=parquet_meta.get("error", "")
    )
