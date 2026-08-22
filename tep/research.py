"""M8 governed structural-edge research primitives. Evidence gates are explicit and fail closed."""
from dataclasses import dataclass,field
from .kernel import canonical_hash
@dataclass(frozen=True)
class FrozenHypothesis:
 hypothesis_id:str;family:str;mechanism:str;specification:str;dev_range:str;holdout_range:str;data_authority:str=''
 @property
 def fingerprint(self):return canonical_hash(self.__dict__)
@dataclass
class SearchPressureLedger:
 trials:int=0;families:set[str]=field(default_factory=set);failures:list[str]=field(default_factory=list);fingerprints:set[str]=field(default_factory=set)
 def record(self,h:FrozenHypothesis,verdict):
  if h.fingerprint in self.fingerprints:raise ValueError('duplicate hypothesis trial')
  self.fingerprints.add(h.fingerprint);self.trials+=1;self.families.add(h.family)
  if verdict!='PASS':self.failures.append(h.hypothesis_id)
 @property
 def selection_pressure(self):return {'trials':self.trials,'families':len(self.families),'failed':len(self.failures)}
@dataclass(frozen=True)
class CostModel:
 spread_bps:float;slippage_bps:float;fees_bps:float;taxes_bps:float;impact_bps:float=0
 @property
 def round_trip_bps(self):return self.spread_bps+self.slippage_bps+self.fees_bps+self.taxes_bps+self.impact_bps
@dataclass(frozen=True)
class ResearchGate:
 leakage_audit:bool=False;negative_controls:bool=False;oos:bool=False;walk_forward:bool=False;realistic_costs:bool=False;regime_robustness:bool=False;parameter_robustness:bool=False;multiple_testing_control:bool=False;independent_verification:bool=False;prospective:bool=False
 def historical_supported(self):return all((self.leakage_audit,self.negative_controls,self.oos,self.walk_forward,self.realistic_costs,self.regime_robustness,self.parameter_robustness,self.multiple_testing_control,self.independent_verification))
 def structural_certified(self):return self.historical_supported() and self.prospective
@dataclass(frozen=True)
class ResearchVerdict:
 implementation_valid:bool=False;historical_edge_supported:bool=False;out_of_sample_supported:bool=False;execution_viable:bool=False;prospective_supported:bool=False;structural_edge_certified:bool=False
 def validate(self):
  if self.structural_edge_certified and not all((self.implementation_valid,self.historical_edge_supported,self.out_of_sample_supported,self.execution_viable,self.prospective_supported)):raise ValueError('certification exceeds evidence')
  if self.prospective_supported and not self.out_of_sample_supported:raise ValueError('prospective support without OOS authority')
  return self
