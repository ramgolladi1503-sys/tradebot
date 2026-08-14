# PR813 feed epoch migration blueprint

## Status

This is a blueprint only. No production or test source is changed by this task.

`e6195ce531b7f26777cd88ca18b0fff0c8bbdbe1` is the required clean base.

## Proposed authority

- Session: existing `run_id + boot_epoch`, owned by `core/runtime_boot_identity.py`.
- Feed currentness: new process/session-scoped monotonic `feed_epoch`, owned by one thread-safe `core/feed/epoch_authority.py` API.
- Storage: in-memory authority for currentness; every canonical artifact persists the value with session identity.
- API: `current_feed_epoch()` and `advance_feed_epoch(reason, metadata)`.
- Persistence: atomic canonical artifact writers; persisted artifacts are never queried to determine the current epoch.

## Legacy disposition

- `recovery_generation_id`: `INTERNAL_ONLY` during M1-M7; after M8 it may remain as diagnostic/recovery metadata or be derived, but never authorizes currentness.
- `_FEED_RECONNECT_GENERATION`: `DEPRECATED_READ_ONLY` for diagnostics during migration; remove or derive during M8. It cannot authorize currentness.
- `subscription_generation_id`: retain as subscription evidence identity, not feed currentness.
- intended/subscribed token sets: retain as an independent exact-set safety invariant; not replaced by feed_epoch.

## Lifecycle contract

| Event | Epoch action | Owner/callsite | Reason |
|---|---|---|---|
| runtime boot/start | advance once before first current artifact | `start_depth_ws` | new feed authority begins |
| initial connect | advance before publishing connected truth if socket identity changes | websocket lifecycle | prior disconnected truth is not current |
| reconnect | advance before new socket/subscription truth | reconnect callback/restart path | old socket state invalid |
| recovery begin | advance before recovery mutation | recovery coordinator integration | old health truth is provisional |
| recovery completion | preserve if no further identity mutation; otherwise advance at mutation | recovery completion callsite | avoid double advancement |
| subscription rebuild | advance before rebuild | canonical subscription mutation wrapper | old exact-set truth invalid |
| intended-set mutation | advance only after intended identity actually changes | ATM/token reconciliation | no-op mutation preserves epoch |
| ATM rebalance with membership change | advance before applying new target | ATM rebalance wrapper | prior option universe invalid |
| freshness observation only | preserve | freshness evaluator | observation is not mutation |
| freshness refresh with token/state mutation | advance before mutation | refresh subscription wrapper | prior subscription truth invalid |
| provider/feed replacement | advance before replacement | supervisor/provider boundary | source identity changes |
| forced supervisor reset | advance before reset | supervisor reset boundary | prior health cannot be assumed |
| health polling/snapshot persistence | preserve | readers/writers | no semantic identity change |

The implementation must prove every row with focused tests before cutover.

## Artifact and loader contract

`feed_truth_latest.json` is primitive feed evidence. `feed_runtime_latest.json` is derived runtime health. Both require session identity, `feed_epoch`, writer, schema version, and produced-at equivalent. Runtime additionally requires explicit `feed_ok` and derived readiness/full-feed blockers.

The canonical loader validates schema, writer, session, epoch, integrity, and—when both artifacts participate—source truth hash/session/epoch. It returns only `VALID_CURRENT` or an explicit invalid result that consumers convert to fail-closed health/readiness.

## Cutover

Cutover is M8, after M4-M7 have passed. Before M8, legacy fields may be emitted as metadata but no new consumer may compare them for currentness. After M8, a stale `recovery_generation_id` cannot make an old artifact current, and a current legacy value cannot rescue an old `feed_epoch`.

## Verification gates

Each slice must leave the branch valid independently. Required gates include focused slice tests, existing live-proven repair regressions, compile, `git diff --check`, and an inventory audit. M9 requires independent exact-SHA review before any live certification.

## Preservation requirements

Every slice must preserve watchdog free-variable and exact-set behavior, minute startup candle seed, 120-second freshness threshold, no synthetic one-minute bars, explicit `feed_ok`, snapshot integrity, warmup/full-feed proof, and all broker/order safety flags. Strategy, ranking, risk, execution, MEG, and H1 files are prohibited.
