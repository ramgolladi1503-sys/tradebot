"""M8 research governance primitives; no edge claims are computed here."""
from dataclasses import dataclass,field
from .kernel import canonical_hash
@dataclass(frozen=True)
class FrozenHypothesis:
    hypothesis_id:str; mechanism:str; specification:str; dev_range:str; holdout_range:str
    @property
    def fingerprint(self):return canonical_hash(self.__dict__)
@dataclass
class SearchPressureLedger:
    trials:int=0; families:set[str]=field(default_factory=set); failures:list[str]=field(default_factory=list)
    def record(self,family,verdict,hypothesis_id):
        self.trials+=1;self.families.add(family)
        if verdict!='PASS':self.failures.append(hypothesis_id)
    @property
    def selection_pressure(self):return {'trials':self.trials,'families':len(self.families)}
@dataclass(frozen=True)
class ResearchGate:
    leakage_audit:bool=False; negative_controls:bool=False; oos:bool=False; realistic_costs:bool=False; robustness:bool=False; independent_verification:bool=False; prospective:bool=False
    def historical_supported(self):return all((self.leakage_audit,self.negative_controls,self.oos,self.realistic_costs,self.robustness,self.independent_verification))
    def structural_certified(self):return self.historical_supported() and self.prospective
