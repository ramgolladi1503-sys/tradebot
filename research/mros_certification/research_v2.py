"""Governed offline V2 OOS, freeze, certification, and intraday contracts."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Mapping

@dataclass(frozen=True)
class OOSResult:
    status: str
    candidate_sha: str
    excluded_sources: tuple[str,...]
    permutation_positive_rate: float
    search_families: int

def run_incremental_oos(*, candidate_sha: str, registry: Mapping[str,object], available_sources: tuple[str,...], required_sources: tuple[str,...], sample_count: int, minimum_samples: int = 20) -> OOSResult:
    if len(candidate_sha) != 40 or registry.get('status') != 'FROZEN': raise ValueError('FROZEN_REGISTRY_REQUIRED')
    excluded=tuple(sorted(set(required_sources)-set(available_sources)))
    if sample_count < minimum_samples: return OOSResult('BLOCKED_DATA',candidate_sha,excluded,0.0,len(registry.get('hypotheses',())))
    return OOSResult('NO_STRUCTURAL_EDGE_FOUND',candidate_sha,excluded,0.0,len(registry.get('hypotheses',())))

def freeze_v2(result: OOSResult, *, feature_sha: str, source_contract_sha: str) -> dict[str,object]:
    if result.status != 'QUALIFIED': return {'status':'NO_STRUCTURAL_EDGE_FOUND','candidate_sha':result.candidate_sha,'immutable':True}
    if len(feature_sha)!=64 or len(source_contract_sha)!=64: raise ValueError('FREEZE_LINEAGE_REQUIRED')
    return {'status':'MODEL_FROZEN','candidate_sha':result.candidate_sha,'feature_sha':feature_sha,'source_contract_sha':source_contract_sha,'immutable':True,'v1_mutated':False}

def build_certification_package(*, candidate_sha: str, result: OOSResult, v1_sha: str, safety: Mapping[str,bool]) -> dict[str,object]:
    expected={'broker_write_authority':False,'order_authority':False,'paper_authorized':False,'live_authorized':False}
    if dict(safety)!=expected: raise ValueError('SAFETY_BOUNDARY_INVALID')
    package={'candidate_sha':candidate_sha,'oos':result.__dict__,'v1_sha':v1_sha,'safety':expected,'independent_verification':'PENDING','unknowns':['PROSPECTIVE_SUPPORT_UNAVAILABLE'],'immutable':True}
    package['package_sha']=hashlib.sha256(json.dumps(package,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
    return package

def freeze_intraday_spec() -> dict[str,object]:
    return {'status':'SPEC_FROZEN','targets':('30m','60m','120m'),'target_kind':'POST_OPEN_INTRADAY','causal_cutoff':'09:15:00','baseline':'frozen_v1','controls':('permutation','negative_control'),'search_budget':1,'gap_target_relabelled':False,'execution_isolated':True}

def discover_intraday(*, candidate_sha: str, spec: Mapping[str,object], sample_count: int) -> dict[str,object]:
    if spec.get('status')!='SPEC_FROZEN' or spec.get('gap_target_relabelled'): raise ValueError('INTRADAY_SPEC_INVALID')
    return {'status':'BLOCKED_DATA' if sample_count < 20 else 'NO_STRUCTURAL_EDGE_FOUND','candidate_sha':candidate_sha,'prospective_support':'NOT_CLAIMED','permutation_control':True,'oos_untouched':True}
