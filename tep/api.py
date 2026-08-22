"""M9 in-process API facade. Mutation methods always traverse authority evaluator."""
from dataclasses import asdict
from .authority import AuthorityEvaluator,AuthorityContext,require_authority
class TEPAPI:
    def __init__(self,store,evaluator=None):self.store=store;self.evaluator=evaluator or AuthorityEvaluator()
    def snapshot(self):return self.store.snapshot()
    def request_mutation(self,capability,ctx:AuthorityContext,action):
        d=self.evaluator.evaluate(capability,ctx);require_authority(d,capability,ctx.target_fingerprint)
        return action(),d
