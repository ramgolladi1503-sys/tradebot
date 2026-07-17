from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class FileInventory:
    absolute_path: str
    source_root: str
    relative_path: str
    inode: Optional[int]
    size_bytes: int
    pre_scan_mtime: float
    post_scan_mtime: float
    pre_scan_size: int
    post_scan_size: int
    stability: str  # STABLE_INCLUDED, UNSTABLE_CHANGED_DURING_SCAN, UNREADABLE, UNSUPPORTED_SCHEMA, EMPTY_FILE, EXCLUDED_BY_POLICY
    sha256: str = ""
    row_count: int = 0
    row_group_count: int = 0
    schema_dict: Dict[str, str] = field(default_factory=dict)
    schema_fingerprint: str = ""
    min_timestamp: Optional[str] = None
    max_timestamp: Optional[str] = None
    timezone: str = "UNKNOWN"
    instruments: List[str] = field(default_factory=list)
    session_date: str = ""
    data_family: str = "unknown"  # underlying_candles, option_candles, ticks, manifests, unknown
    is_empty: bool = False
    error: str = ""
    duplicate_of: Optional[str] = None  # To identify content-identical files
