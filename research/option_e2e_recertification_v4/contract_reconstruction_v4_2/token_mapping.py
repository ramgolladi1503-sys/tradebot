from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenMappingEvidence:
    historical_token_mapping_identity: bool
    historical_mapping_source: str
    historical_mapping_asof_ts: str
    historical_mapping_hash: str
    current_master_match: bool
    current_master_fields_used: str

