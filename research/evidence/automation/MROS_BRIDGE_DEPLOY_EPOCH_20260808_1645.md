# MROS Bridge Deploy Epoch — 2026-08-08

Purpose: force the persistent Mac bridge autoupdater to consume the current `research/mros-agent-bridge-v1` revision after the S003 review-transport hardening.

Required deployed behavior:

- supervisor routes S003 through `scripts/mros/mros_autonomous_cycle_v2.py`;
- review/audit transport identity is controller-owned via `scripts/mros/mros_review_transport.py`;
- invalid review envelopes do not contribute implementation repair findings;
- malformed transport roles are retried individually;
- stdout/stderr remain separated for Git porcelain checks;
- 15-minute durable supervisor checkpoints remain enabled;
- runtime authority remains `NONE`;
- M9 remains `NOT_STARTED`.

This artifact grants no program authority and changes no acceptance criterion, review quorum, trading behavior, runtime behavior, broker behavior, strategy logic, risk logic, or execution logic.
