import json
from dataclasses import dataclass
from typing import List, Dict, Set, Any
from .partition_authority import PartitionAuthority

class DecisionAuthorityError(Exception):
    pass

@dataclass
class AcceptedCandidate:
    session_date: str
    direction: str
    fingerprint: str
    dataset_group_hash: str
    feature_cutoff_timestamp: str

@dataclass
class DecisionAuthority:
    accepted_development_candidates: List[AcceptedCandidate]
    rejected_decision_dates: Set[str]
    
    @classmethod
    def load(cls, decisions_path: str, partition: PartitionAuthority) -> "DecisionAuthority":
        try:
            with open(decisions_path) as f:
                data = json.load(f)
        except Exception as e:
            raise DecisionAuthorityError(f"Failed to load decisions file: {e}")
            
        accepted = []
        rejected = set()
        seen_accepted = set()
        
        for cand in data:
            date = cand.get("session_date")
            if not date:
                raise DecisionAuthorityError("Missing session date.")
                
            is_accepted = cand.get("candidate_accepted")
            
            if is_accepted is True:
                if cand.get("primary_rejection_reason") != "NONE":
                    raise DecisionAuthorityError(f"Accepted candidate {date} has a rejection reason.")
                    
                from .direction_authority import normalize_direction
                direction = normalize_direction(cand.get("direction"))
                    
                if date in partition.holdout_dates:
                    raise DecisionAuthorityError(f"HOLDOUT_LOCKED")
                    
                if date in seen_accepted:
                    raise DecisionAuthorityError(f"Duplicate accepted session {date}")
                seen_accepted.add(date)
                
                accepted.append(AcceptedCandidate(
                    session_date=date,
                    direction=direction,
                    fingerprint=cand.get("candidate_fingerprint"),
                    dataset_group_hash=cand.get("dataset_group_hash"),
                    feature_cutoff_timestamp=cand.get("feature_cutoff_timestamp")
                ))
            elif is_accepted is False:
                rejected.add(date)
            else:
                raise DecisionAuthorityError(f"Unknown candidate_accepted status for {date}")
                
        return cls(
            accepted_development_candidates=accepted,
            rejected_decision_dates=rejected
        )
