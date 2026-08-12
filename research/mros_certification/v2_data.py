"""Immutable V2 raw artifacts, causal feature builds, and hypothesis registry."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib,json
from typing import Mapping

@dataclass(frozen=True)
class RawArtifact:
    source: str; session: str; observed_at: str; units: str; timezone: str; value: object; status: str = 'AVAILABLE'
    def seal(self):
        payload=self.__dict__.copy(); return {**payload,'sha256':hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'immutable':True}

def build_causal_features(raw: Mapping[str, Mapping[str, object]], *, cutoff: str, required: tuple[str,...]) -> dict[str,object]:
    out={}
    for name in required:
        row=raw.get(name)
        if row is None: return {'status':'BLOCKED_DATA','missing_source':name}
        if row.get('status') != 'AVAILABLE': return {'status':'BLOCKED_DATA','missing_source':name}
        if row.get('observed_at','') > cutoff: raise ValueError('FUTURE_SOURCE_REJECTED')
        if not row.get('sha256') or not row.get('source') == name: raise ValueError('RAW_PROVENANCE_INVALID')
        out[name]=dict(row)
    result={'status':'FEATURES_BUILT','cutoff':cutoff,'sources':out,'v2_additive':True}
    result['artifact_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result

def freeze_hypotheses(items: tuple[Mapping[str,object],...]) -> dict[str,object]:
    if not items or len({x.get('hypothesis_id') for x in items}) != len(items): raise ValueError('HYPOTHESIS_ID_INVALID')
    required={'features','rationale','targets','benchmark','controls','search_budget'}
    if any(not required.issubset(x) for x in items): raise ValueError('HYPOTHESIS_CONTRACT_INCOMPLETE')
    return {'status':'FROZEN','hypotheses':items,'immutable':True}
