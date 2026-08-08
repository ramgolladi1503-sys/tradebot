# MROS S003 ISOLATED AGENT BRIDGE — NON-CERTIFYING SMOKE

You are role `R99` running only to prove fresh isolated model execution through the MROS Mac bridge.

This is NOT an S002 or S003 certification review. Do not issue a sprint PASS/FAIL verdict and do not modify the repository.

Exact candidate under read-only inspection:

`fd16f526842b9f4f27d7fd06859b059812e10796`

Required actions:

1. Verify the current worktree resolves to that exact SHA using repository inspection available to you.
2. Inspect `scripts/mros/validate_s002_fixtures.py` only enough to prove repository read access.
3. Do not edit files, run broker/runtime operations, or create authority.
4. Return a short Markdown artifact containing exactly these fields with truthful values:

```text
MROS_AGENT_BRIDGE_SMOKE
ROLE=R99
CANDIDATE_HEAD=<sha observed>
FRESH_CONTEXT_DECLARATION=YES
REPOSITORY_READ=PASS|FAIL
RUNTIME_AUTHORITY=NONE
BROKER_ACTIONS=NONE
SMOKE_RESULT=PASS|FAIL
```

`SMOKE_RESULT=PASS` is allowed only if the observed HEAD exactly equals the candidate above and repository read succeeded.
