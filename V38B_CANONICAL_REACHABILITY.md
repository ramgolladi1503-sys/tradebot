# V38B canonical reachability

CANONICAL_RUNTIME_REACHABILITY_PASS=true
MARKET_STATE_SIDECAR_REACHABILITY_PASS=true
MARKET_STATE_SIDECAR_MODE=EXPLICIT_READ_ONLY_SIDECAR

The canonical chain remains `run_observation` → normalized tick sink →
persistence/snapshots → `CanonicalCycleCoordinator` → `run_consumer_cycle` →
CAS evaluator → candidate/funnel/ranking. #885 is an explicit observer of
authoritative snapshots and is not wired into canonical eligibility or
execution.
