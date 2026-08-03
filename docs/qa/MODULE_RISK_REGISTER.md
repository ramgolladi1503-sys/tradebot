# TradeBot MEG Shadow Module Risk Register

## Certification target

Supervised, read-only Market Event Graph shadow operation. Strategy profitability, broker connectivity, and paper/live execution are outside this register.

| Area | Tier | Principal failure | Required control | Certification gate |
|---|---|---|---|---|
| Authentication | A | Missing, invalid, or unknown credentials presented as usable | Canonical token precedence; invalid-session classification; `UNKNOWN_NETWORK ok=false` | Authentication and startup |
| Kite subscription plan | A | Requested/acknowledged tokens diverge or observation universe is incomplete | Frozen launch plan, generation identity, budget and exact constituent coverage | Feed and subscription truth |
| Packet callbacks | A | Blocking writes, data loss, or false FULL-mode evidence | Worker-owned persistence, reconciliation, callback SLA, saturation fail-closed | Feed and subscription truth; persistence |
| Tick/depth/runtime persistence | A | Acknowledged evidence is lost or corrupt across shutdown/restart | Exact enqueue/write/drain accounting, hashes, terminal rejection, reconstruction | Persistence and shutdown; restart |
| MEG completed bars | B | Partial/future/gapped bars masquerade as causal sequence | Right-closed completed intervals, coverage thresholds, gap stop, provenance | MEG observation |
| MEG traversal | B | Candidate emitted without required graph sequence | Explicit traversal evidence and shadow-only output | MEG observation |
| Canonical execution authority | A | Fallback/stale/unknown row inherits execution permission | One immutable `EXECUTABLE / ADVISORY_ONLY / BLOCKED` decision | Authority, ranking, and UI |
| Ranking and capital | A | Non-executable row outranks valid row or receives capital | `selection_score=0`, zero capital/slot, executable-only selector input | Authority, ranking, and UI |
| Operator UI | B | Advisory/debug row appears executable | Separate executable, advisory, and blocked/debug buckets | Authority, ranking, and UI |
| Manual approval | A | Duplicate, expired, or invalid approval creates intent | Exactly-once approval contract and late authority revalidation | Manual approval and broker firewall |
| Execution router | A | Stamped blocked candidate reaches simulation or broker path | Final authority preflight before approval/fill work | Manual approval and broker firewall |
| Broker/order boundary | A | Deterministic tests or shadow mode reach write APIs | Broker firewall, read-only configuration, no order authority | Manual approval and broker firewall |
| Restart/reconciliation | A | Duplicate supply, lost ledger state, or inconsistent recovery | Durable identity, idempotency, exact state reconstruction | Restart and reconciliation |
| Evidence sealing | A | Partial, mixed, or modified artifacts accepted | One fresh root, manifest/SHA authority, undeclared-file rejection | AI reliability and evidence integrity |
| Reliability sidecar | B | Unsupported explanation or fabricated completion claim | Evidence IDs, deterministic assertions, rejected unsupported findings | AI reliability and evidence integrity |
| Certification runner | C | Missing gate silently omitted or tests alone imply live success | Fixed eight-gate list and separate live certificate dependency | All offline gates |

## Release blockers

The following are release-blocking for the read-only shadow target:

- authentication state is not verified;
- subscription registry or observation generation is inconsistent;
- no real post-mode FULL NIFTY packets;
- no completed constituent bars or required MEG traversal;
- persistence drain or evidence sealing is incomplete;
- any fallback, synthetic, stale, unknown, or contradictory row has executable authority, positive selection score, or capital;
- any broker-write or order authority is present;
- any required offline gate is missing, timed out, skipped, or nonzero;
- PR #772 post-market certificate is absent or not passing.

## Non-blocking research questions

These do not block engineering completion of the shadow system:

- profitability and structural edge;
- optimal strategy parameters;
- historical bid/ask execution performance;
- model calibration or ML uplift;
- unattended execution or production deployment.