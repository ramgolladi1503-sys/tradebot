# Rebootstrap V1 reviewer checklist

Do not merge or use against `/Volumes/TradeBotData/release_store` until all boxes are supported by fresh evidence on this branch SHA.

- [ ] compile succeeds
- [ ] existing release tests pass
- [ ] rebootstrap tests pass
- [ ] existing release mutation campaign remains 15/15
- [ ] all 22 rebootstrap behavioral attacks are implemented and detected
- [ ] independent verifier recomputes candidate/predecessor/gates/primitives/dependency graph/certification
- [ ] normal promotion attestation regression is green after dependency-graph binding repair
- [ ] original release-store manifest is unchanged before controlled recovery
- [ ] dry-run certification/verification succeeds on a copy of the store
- [ ] recovery event preserves all old history byte-for-byte
- [ ] recovery event has no trusted fallback to quarantined history
- [ ] broker/order counters remain zero

Current state is implementation-for-review only. The placeholder mutation campaign intentionally exits non-zero until the 22 behavioral mutators exist.
