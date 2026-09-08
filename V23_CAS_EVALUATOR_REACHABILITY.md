# V23 CAS Evaluator Reachability

Independent A/B/C harness cases invoke `CanonicalCycleCoordinator.run()` and
observe persisted consumer/CAS/readiness artifacts. The production evaluator
is reached without a direct evaluator call in the test path.

```text
CAS_EVALUATOR_REACHABILITY_PASS=true
CAS_EVALUATOR_FUNCTION=core.cas_morning_reversal_advisory:evaluate
```
