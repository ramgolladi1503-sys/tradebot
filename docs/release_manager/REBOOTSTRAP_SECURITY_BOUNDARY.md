# Security boundary

Rebootstrap authority is intentionally narrower than normal release availability:

1. current head must be explicitly quarantined by code;
2. candidate must be exact clean HEAD and non-quarantined;
3. dependency evidence must be complete;
4. all 18 semantic gates are required;
5. primitives are candidate/evaluator/time bound;
6. independent verifier recomputes them;
7. attestation binds predecessor event/SHA and no-fallback status;
8. store appends rather than rewrites history;
9. healthy-head and repeated rebootstrap are rejected.

This mechanism must never be generalized into a caller-selected recovery base.
