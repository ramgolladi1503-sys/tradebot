# TEP M1–M10 Single-PR Implementation Authority — 2026-08-22

User-authorized execution policy: build the coherent TEP v1 implementation candidate in PR #860 rather than serially waiting for remote CI after every milestone.

Frozen architecture authority remains `9cdc21b2270d924daaf860443e57f39df4b0cc93`. This document does not rewrite that constitution; it authorizes implementation work across M1–M10 on the existing branch/PR with internal milestone gates.

## Rules
- one implementation PR: #860;
- milestone contracts and validation remain separate even though development is continuous;
- remote CI is a checkpoint, not a serial development lock;
- a failed foundational milestone invalidates dependent claims;
- no validator weakening, fake PASS, evidence fabrication or code-volume target;
- no new successor PR unless separately authorized;
- GitHub merge, destructive cleanup, broker write, order, paper and live execution authority remain false;
- read-only adapters may be implemented but real live sessions require their separate authority/evidence gates;
- final merge requires integrated tests, adversarial/failure-injection tests, independent review, required CI green and exact-head/base JIT recheck.

`M1_TO_M10_IMPLEMENTATION_CANDIDATE_AUTHORIZED=true`
`M1_TO_M10_CERTIFICATION_AUTHORIZED=false`
`GITHUB_MERGE_AUTHORITY=false`
`DESTRUCTIVE_CLEANUP_AUTHORITY=false`
`BROKER_WRITE_AUTHORITY=false`
`ORDER_AUTHORITY=false`
`PAPER_AUTHORIZED=false`
`LIVE_AUTHORIZED=false`
