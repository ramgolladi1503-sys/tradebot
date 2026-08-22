"""M7 read-only live planning contracts."""
from dataclasses import dataclass
from datetime import datetime
@dataclass(frozen=True)
class LaunchPlan:
 session_id:str;market_date:str;candidate_sha:str;static_instruments:tuple[str,...];dynamic_instruments:tuple[str,...]=();stop_at:str='15:30';timezone:str='Asia/Kolkata'
 def validate(self):
  if not self.candidate_sha or len(self.candidate_sha)<7:raise ValueError('candidate SHA required')
  datetime.strptime(self.market_date,'%Y-%m-%d')
  if not self.static_instruments:raise ValueError('subscription seed required')
  return self

def derive_subscriptions(plan,candidates):
 plan.validate();return tuple(sorted(set(plan.static_instruments)|set(plan.dynamic_instruments)|set(candidates)))
@dataclass(frozen=True)
class DurabilityCounters:
 attempted:int;written:int;rejected:int
 def validate(self):
  if min(self.attempted,self.written,self.rejected)<0 or self.written+self.rejected!=self.attempted:raise ValueError('invalid durability accounting')
  return self
 @property
 def lossless(self):return self.validate().rejected==0
@dataclass(frozen=True)
class SessionEvidence:
 session_id:str;candidate_sha:str;producer_id:str;validator_id:str;feed_messages:int;durability:DurabilityCounters;graceful_stop:bool
 def live_verified(self):return bool(self.candidate_sha and self.producer_id and self.validator_id and self.producer_id!=self.validator_id and self.feed_messages>0 and self.durability.lossless and self.graceful_stop)
