from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class FileInventory:
    absolute_path: str
    source_root: str
    relative_path: str
    filename: str
    extension: str
    size_bytes: int
    pre_scan_mtime: float
    post_scan_mtime: float
    stability: str
    sha256: str = ""
    row_count: int = 0
    columns: Dict[str, str] = field(default_factory=dict)
    row_group_count: int = 0
    embedded_metadata: Dict[str, str] = field(default_factory=dict)
    min_timestamp: Optional[str] = None
    max_timestamp: Optional[str] = None
    timezone: str = "UNKNOWN"
    instruments: List[str] = field(default_factory=list)
    session_date: str = ""
    data_family: str = "unknown"
    schema_fingerprint: str = ""
    is_empty: bool = False
    error: str = ""
