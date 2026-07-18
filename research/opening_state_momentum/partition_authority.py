import json
from dataclasses import dataclass
from typing import List, Set

class PartitionAuthorityError(Exception):
    pass

@dataclass
class PartitionAuthority:
    ordered_dates: List[str]
    development_dates: Set[str]
    holdout_dates: Set[str]
    partition_hash: str
    
    @classmethod
    def load(cls, path: str) -> "PartitionAuthority":
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            raise PartitionAuthorityError(f"Failed to load partition file: {e}")
            
        if "metadata" not in data:
            raise PartitionAuthorityError("Missing 'metadata' key in partition schema.")
            
        metadata = data["metadata"]
        if "ordered_session_list_hash" not in metadata:
            raise PartitionAuthorityError("Missing 'ordered_session_list_hash' in metadata.")
            
        partition_hash = metadata["ordered_session_list_hash"]
        
        if "development" not in data or not isinstance(data["development"], list):
            raise PartitionAuthorityError("Missing or invalid 'development' list.")
            
        if "holdout" not in data or not isinstance(data["holdout"], list):
            raise PartitionAuthorityError("Missing or invalid 'holdout' list.")
            
        development_dates = set(data["development"])
        holdout_dates = set(data["holdout"])
        ordered_dates = data["development"] + data["holdout"]
        
        # Verify non-overlapping
        if not development_dates.isdisjoint(holdout_dates):
            raise PartitionAuthorityError("Development and holdout dates overlap.")
            
        return cls(
            ordered_dates=ordered_dates,
            development_dates=development_dates,
            holdout_dates=holdout_dates,
            partition_hash=partition_hash
        )
