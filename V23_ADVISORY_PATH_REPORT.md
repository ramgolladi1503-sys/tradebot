# V23 Advisory Path Report

For the valid A/B/C cases, the production path reaches the CAS evaluator and
persists `cas_v2_artifact.json`, `cas_readiness_latest.json`, and the consumer
cycle artifact. The CAS result is advisory-only and carries zero broker/order
calls. No order-capable path was invoked.

```text
CAS_TO_CANDIDATE_POOL_REACHABLE=PARTIAL
CAS_TO_ADVISORY_PATH_REACHABLE=true
ORDER_CAPABLE_PATH_REACHABLE=false
```

Candidate-pool reachability for every D–X production-chain case remains
unproven.
