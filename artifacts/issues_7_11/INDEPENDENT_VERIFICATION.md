# Independent Verification — Issues 7–11

## Fresh independent audit — Issue 11 transport contradiction — 2026-10-03

The read-only fresh verifier reproduced a defect where `effective_ws_connected=false` was overridden by `ws_connected=true`. The executor added a Hermes contract and GSD plan addendum requiring exact-true effective status whenever that field exists, retaining the legacy field only when effective status is absent. The producer-to-evaluator regression and isolated mutation are now included in the final validation pass. This closes only the reproduced CAS shared-transport contradiction; campaign acceptance and independent certification remain open.

**Verification date:** 2026-10-03
**Repository HEAD:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**Scope:** bounded read-only review of Issue 8 token repair, Scenario A completed-bar addendum, Scenario C/D observer claims, campaign graph and current evidence statements. This is not a certification of the whole campaign.

## Independent verifier findings

A fresh verifier inspected the current CAS producer/test paths and performed temporary adversarial probes without modifying repository files. A valid positive integer token was accepted. Boolean, float, string, zero, and negative token variants were rejected at capture, persisted-row verification, recomputed event-payload/hash/ID verification, and expected-token validation. No remaining malformed-token identity bypass was found in these paths.

The verifier also checked the Scenario A change against its contract. The test:

1. verifies a pinned synthetic T-1 manifest through the actual loader;
2. creates the real shadow registry from the verified values;
3. persists one deterministic 09:15 fixture bar through `MarketSessionStore.persist_completed_bar` with a 09:16 completion cutoff;
4. opens a distinct store instance, verifies integrity, and reads exactly that bar before the pulse; and
5. dispatches a healthy synthetic pulse through the real registry to each original adapter method.

The store is not passed into or read by the registry/adapters. The test and report explicitly claim coexistence only, not adapter bar consumption, candidate eligibility, live T-1 authority, or a live clean boot. Closed registry authority and zero order counters are asserted. No code or test overclaim was found for this Scenario A change.

At the verifier's first review point, the graph contained 113 unique nodes and 115 edges with no dangling endpoints. After the executor added one captured-blocker evidence node and edge, the verifier reparsed the current graph and confirmed 114 unique nodes, 116 edges, and no dangling endpoints. `I8_MUTATION` is `PASS_PARTIAL`: six targeted identity/type mutants are recorded as killed, while parent/time/provenance and historical-source mutations remain open. Scenario A remains synthetic, C/D remain observer-boundary-only, B/E remain incomplete, and Issues 7/8 source authority remains UNKNOWN. Overall verdict remains `implementation_valid=false`, `issues_7_11_offline_repair_verified=false`, and `live_verified=false`.

## Current focused evidence

- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_cas_primitive_producer.py tests/paper_shadow/test_issue11_scenarios_cd.py tests/test_market_heritage_graph.py::test_scenario_a_verified_t1_clean_boot_reaches_shadow_evaluators tests/paper_shadow/test_t1_scenario_f_missing_manifest.py tests/paper_shadow/test_t1_prerequisites_authority.py tests/core/test_market_session_store.py` → **82 passed, 1 warning**.
- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_market_heritage_graph.py` → **67 passed, 1 warning**.
- `python3 scripts/verify_issues_7_11_issue8_mutations.py` → **6/6 targeted mutants killed** in isolated temporary copies.
- Issues 1–6 protection command recorded in `FINAL_VERDICT.json` → **221 passed, 1 warning**. This specific protection command was last run before the test-only Scenario A change; no Issues 1–6 production files were changed by that addendum.

These checks do not close campaign-wide mutation coverage, all cross-issue scenarios, captured/live parity, or external source authority.

## Captured data authority recheck (executor read-only inspection)

The Oct. 1 session bundle is documented with exact source paths, hashes, schemas, and authority limits in `CAPTURE_CORPUS_RECHECK_20261003.md`. The inspected CAS heritage artifact says EMPTY and `NO_VERIFIED_PRIOR_RUN_INTERVAL`; the primitive attempts are BLOCKED with null source-event IDs/payloads/hashes, source/receive timestamps, and prices. The stitched parquet schema has no original source event ID, event payload hash, or distinct receive timestamp. This confirms the evidence gap; it does not recover the original interval.

## Unresolved acceptance gates

- Issue 7: actual prior-session futures/calendar/source authority and valid positive admission remain UNKNOWN.
- Issue 8: original source-event-bound interval is absent; restart/corrupt/ambiguous parent and broader mutation attacks remain incomplete.
- Issue 9: deterministic offline primary runtime persistence/restart path is covered; actual running-service restart and captured/live parity remain UNKNOWN.
- Issue 10: offline route and EOD row-set parity are covered; captured/live parity and concurrent writer behavior remain unverified.
- Issue 11: read-only observer consumer normalization and quote freshness are covered; candidate-level isolation, initiating transport/auth failure, and live behavior remain UNKNOWN. Captured feed/runtime snapshots identify terminal recovery or auth blockers at the saved times; they do not explain the initiating fault.
- Scenarios B/E are not composed. C/D are not proven through a governed candidate/evaluator pipeline. Scenario A/F proofs are offline synthetic/negative-path only.
- Campaign-wide code mutations, complete differential token-universe comparison, performance/soak checks on current source, and applicable CI remain open or unverified.

**Independent disposition:** BOUNDED_PASS for the reviewed identity guards and Scenario A claim; campaign acceptance remains OPEN. No live process, broker, order, credentials, or external capture files were modified. PR #936 is excluded.


## Broad regression result (executor run)

Current-source command `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'` completed with **8650 passed, 9 skipped, 29 deselected, 1474 warnings in 871.60s** at SHA `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`. This is an executor-run broad offline regression, not part of the independent verifier's bounded review; exclusions and limits are recorded in `FINAL_VERDICT.json`.


## Subsequent captured-feed state addendum (executor recheck)

After the independent review above, executor read-only inspection of all four Oct. 1 session run directories found three run-matched health/runtime artifacts with canonical `RECOVERY_BLOCKED` / `WS1006_PROCESS_RESTART_REQUIRED` and one `AUTH_BLOCKED` / websocket-disconnected state; all candidate-decision ledgers were empty. Exact hashes and limits are in `CAPTURE_CORPUS_RECHECK_20261003.md`. This narrows the saved global-block state but does not identify the initiating transport/auth event or establish candidate-level isolation. A fresh independent read-only review confirmed the new node/edge counts and that its wording preserves UNKNOWN for the initiating transport/auth fault and candidate-level isolation; the reviewer did not independently hash or inspect the external source files during this pass.


## Final independent graph/verdict recheck

The prior 114-node/116-edge figures above are a historical snapshot from the earlier review and are superseded. The fresh full-scope audit at the same repository HEAD reparsed the current graph: 135 unique nodes, 142 edges, zero dangling references. It confirmed `implementation_valid=false`, `issues_7_11_offline_repair_verified=false`, and `live_verified=false`. It independently exercised the transport gate with `effective_ws_connected="true"` plus legacy `ws_connected=true`; the actual producer blocked with `cas_shared_feed_unhealthy_or_unknown` and emitted no CAS input. The adversarial test module passed 22 tests and the old-OR mutation was killed. This is bounded offline verification; Issues 7/8 source authority, Issue 9 service restart/captured parity, Issue 10 external writer/captured parity, generic Issue 11 candidate isolation/initiating fault, B/E composition, campaign-wide mutations, Issues 1–6 exact-current-source rerun, and applicable CI remain open or UNKNOWN.

The verifier confirmed the worktree manifest’s tracked hashes/diff digest after it was refreshed. The manifest excludes its own file hash to avoid self-reference and lists 139 other non-ignored untracked paths. Its separate live-universe parity and generated-file provenance remain unverified.


## Issue 11 persisted ranking truth — independent follow-up

A fresh read-only verifier attacked the live-worktree classifier/ranking boundary after each repair iteration. It first defeated exact-source-only recognition with unsupported version, contradictory component flags, and arbitrary source-label changes; those attacks were added as regressions. It then confirmed that source/freshness marker removal with the canonical writer/component markers blocks as unsupported, and that empty or transport-only input blocks for missing authority. The verifier checked compatibility for an explicitly scoped healthy symbol despite unrelated stale-symbol degradation and verified that removing required symbol-age evidence blocks. On the timestamp hardening, the verifier confirmed stale, missing, malformed, boolean, future, and invalid-age-config snapshots fail closed while explicit-symbol scoped behavior remains.

Parent-run exact file-loader/ranking regression covers `_load_cycle_feed_truth_payload` reading an actual temporary `feed_truth_latest.json`. The final focused health/ranking/runtime compatibility run before broad rerun passed **84 tests**; the broader related boundary suite passed **131 passed, 1 deselected** before the final two compatibility adjustments. A current-source campaign-wide run then found two failures: legacy hysteresis decision compatibility and a runtime integrity conflict caused by missing-authority classification. The classifier now permits legacy no-aggregate inputs only when finite LTP-age evidence and an explicit SLA are both supplied; nested hysteresis alone is not accepted as authority. Both formerly failing tests pass in focused rerun. The campaign-wide rerun on this current patch is pending.

Independent scope is limited to the Issue 11 offline mapping/classifier/ranking boundary. It does not prove captured/live parity, execution authority, candidate-level isolation, or the other open Issues 7–10 gates.


Final malformed-age follow-up: age parsing now requires exact finite nonnegative numeric JSON values for LTP/depth/option evidence; bool, negative, string, and NaN values fail closed. Parent-run cross-boundary regression passes **143 passed, 1 deselected, 1 warning**. A fresh independent review confirmed no boolean, negative, nonfinite, or string-age bypass; targeted verifier suite passed **41 passed, 1 deselected, 1 warning**. The final exact-current-source broad offline rerun completed: **8670 passed, 9 skipped, 29 deselected, 1474 warnings in 674.72s**, with three explicit exclusions recorded in `FINAL_VERDICT.json`. This remains bounded offline evidence; Issues 7/8 source authority, candidate-level Issue 11 isolation, capture/live parity, and campaign acceptance remain open.

## Current continuation addendum — 2026-10-03

This pass did not create a new independently executed agent verifier; the checks below are executor-observed and should not be represented as fresh independent certification.

- Exact current broad command, rerun without overlapping test jobs: **8671 passed, 9 skipped, 29 deselected, 1474 warnings in 902.81s**. A previous loaded run failed two tests after their inner `git log --all -S VWAP_RECLAIM` subprocesses exceeded 60 seconds; both tests passed as an isolated pair in 80.71s and the subsequent broad run passed. The initial failure remains preserved in `FINAL_VERDICT.json`.
- Focused Issues 7–11 surface: **341 passed, 1 warning in 13.44s**.
- Issue 9 mutation proof: baseline 2 passed; 2/2 temporary-copy source mutants killed; source/test hashes unchanged. Details: `ISSUE9_MUTATION_RESULTS_20261003.md`.
- Existing targeted mutation runners report Issue 7 3/3, Issue 8 6/6, Issue 10 2/2, and Issue 11 loader-origin 1/1 killed. These are not full issue-wide mutation closure.
- Machine graph reparsed after updates: **121 unique nodes, 124 edges, zero dangling endpoints**. This graph-structure check does not establish every semantic edge independently.
- The Issues 1–6 protection command was not rerun in this continuation. The previously recorded 221-pass result is unchanged by the newly added verifier and evidence files, but its freshness is bounded to the prior run.

Campaign remains OPEN: Issues 7/8 source authority, Issue 9 actual service restart and captured parity, Issue 10 captured/live and multi-process writer semantics, Issue 11 candidate-level isolation and initiating transport/auth cause, Scenarios B/E, campaign-wide mutations, and independent full-scope verification are unproven.


## Continuation trace — Issue 10/11 acceptance boundaries — 2026-10-03

This is a bounded executor read-only repository trace, not a new independent verifier run.

- Issue 10 writer: the canonical observer appends complete LF-terminated rows to its session ledger. The ordinary `main.py` entry point holds a governed `InstanceLock` for its lifetime. Repository search found no production callsite beyond the wrapper/implementation and tests, but there is no deployment evidence that direct calls or separate processes cannot share a root. The descriptor-based reader does not serialize writers. Multi-process atomicity remains UNKNOWN.
- Issue 11 candidate path: `runtime_snapshot_producer` bridges validated CAS source-event primitives into `cas_short_horizon_inputs` when shared websocket connectivity is true; `_evaluate_cas` invokes the advisory evaluator with that input. The candidate dependency registry declares exact NIFTY `INDEX_SPOT` identity, but repository search found no producer of candidate `feed_health_by_identity` evidence and no health binding in the CAS input bridge. Existing Scenario C/D tests stop at read-only observer snapshots. Candidate/evaluator isolation remains UNKNOWN; do not infer it from those tests.
- The graph now records both boundaries and preserves `implementation_valid=false`, `issues_7_11_offline_repair_verified=false`, and `live_verified=false`. No source, test, config, broker, order, or live authority changed in this continuation.


## Issue 10 canonical writer follow-up — executor verification — 2026-10-03

After discovering three repository entry paths converging on the same observer writer, the executor added an exclusive file lock around each candidate-decision batch. The lock is held through flush; a failed append is truncated to its pre-batch offset before unlock. This is an executor-run check, not a new independent review.

- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_read_only_observation_runtime.py::test_candidate_decision_batches_are_serialized_across_processes` → **1 passed**. Two subprocesses each append 32 large rows; all 64 parse and each batch remains contiguous.
- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_read_only_observation_runtime.py tests/core/test_runtime_snapshot_producer.py tests/analytics/test_issues_7_11_eod_row_parity.py` → **36 passed, 1 warning**.
- Scope limit: only callers using the canonical helper cooperate with its lock. A separate writer bypass, actual deployment overlap, captured/live parity, and campaign completion remain UNKNOWN/open.


## Exact current-tree broad regression after Issue 10 writer change — executor run — 2026-10-03

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'` completed **8672 passed, 9 skipped, 29 deselected, 1474 warnings in 925.16s; exit code 0** at `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`. Exclusions: unavailable `upstox_client`, large external stitched-capture test, and `test_v5_verifier_deep_primitive_validation` after its prior capture-backed stall. This is broad offline regression, not fresh independent certification, external-writer proof, or live/capture parity.


## Issue 10 second-writer and lock mutation follow-up — executor verification — 2026-10-03

A further writer search found `core/reject_shadow.py` writes the per-desk candidate decision ledger. Both that path and the read-only observer now use the shared `core.locked_jsonl.append_jsonl_batch` lock owner. The multiprocess test forces repeated short writes and staggered scheduling. `python3 scripts/verify_issues_7_11_issue10_writer_mutation.py` removes `LOCK_EX` in a temporary package copy; the intended test failed, and the runner confirmed source/test hashes in the checkout were unchanged. This is executor-run adversarial evidence, not a fresh independent agent review. Full results and hashes: `artifacts/issues_7_11/ISSUE10_WRITER_MUTATION_RESULTS_20261003.md`. External writers bypassing the helper and captured/live parity remain UNKNOWN.


## Issue 11 CAS dependency gate — executor verification — 2026-10-03

This is executor-run verification, not a fresh independent review. A Hermes contract and GSD plan were added before the implementation. The bridge now requires exact NIFTY quote symbol/token matching both captured primitives, `is_fresh is True`, `is_executable_quote is False`, `feed_health.status == HEALTHY`, finite nonnegative age within the existing SLA, and a recent aware market snapshot. It preserves the shared WebSocket gate and emits `cas_input_gate` reason codes.

- Focused producer/CAS/evaluator/feed set: **176 passed, 1 deselected, 1 warning**, including the V23 production-equivalent harness.
- Scenario C composes the actual runtime snapshot producer and `_evaluate_cas`: fresh NIFTY plus stale unrelated option reaches ADVISORY_ONLY with closed paper/live/order authority.
- Scenario D covers stale spot, bool/string age, mismatched token, false freshness, and stale snapshot; the evaluator emits no CAS artifact.
- `scripts/verify_issues_7_11_issue11_cas_dependency_mutation.py`: required-spot predicate removal killed; checkout hashes unchanged.
- Existing config reused; no new config key. No broker, order, risk, strategy, or live authority changes.

Limits: this proves only the declared CAS spot dependency in offline fixtures. It does not prove generic candidate-registry dependency isolation, original initiating transport/auth cause, historical source authority, deployment wiring, or captured/live parity. Overall campaign remains OPEN and `implementation_valid=false`.


## Issue 11 CAS dependency gate — executor verification — 2026-10-03

This is executor-run verification, not a fresh independent review. A Hermes contract and GSD plan were added before implementation. The bridge now requires exact NIFTY quote symbol/token matching both captured primitives, `is_fresh is True`, `is_executable_quote is False`, `feed_health.status == HEALTHY`, finite nonnegative age within the existing SLA, and a recent aware market snapshot. It preserves the shared WebSocket gate and emits `cas_input_gate` reason codes.

- Focused producer/CAS/evaluator/feed set: **176 passed, 1 deselected, 1 warning**, including the V23 production-equivalent harness.
- Scenario C composes the actual runtime snapshot producer and `_evaluate_cas`: fresh NIFTY plus stale unrelated option reaches ADVISORY_ONLY with closed paper/live/order authority.
- Scenario D covers stale spot, bool/string age, mismatched token, false freshness, and stale snapshot; the evaluator emits no CAS artifact.
- `scripts/verify_issues_7_11_issue11_cas_dependency_mutation.py`: required-spot predicate removal killed; checkout hashes unchanged.
- Existing config reused; no new config key. No broker, order, risk, strategy, or live authority changes.

Limits: this proves only the declared CAS spot dependency in offline fixtures. It does not prove generic candidate-registry dependency isolation, original initiating transport/auth cause, historical source authority, deployment wiring, or captured/live parity. Overall campaign remains OPEN and `implementation_valid=false`.

The executor then validated the correction: the focused producer/adversarial suite completed with 51 passed; the transport-OR mutant and required-spot-predicate mutant were both killed. Exact-source broad offline regression completed with 8702 passed, 9 skipped, 29 deselected, and 1474 warnings in 942.56 seconds. The broad command excludes the unavailable Upstox dependency, large external stitched capture, and prior capture-backed verifier stall. No live or captured parity is certified by these results.

The Issues 1–6 scoped protection suite was rerun on this exact worktree after the fresh full-scope audit: **221 passed, 1 warning in 25.67s**. Command: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_depth_ws_stability.py tests/test_depth_subscription_tokens.py tests/test_market_event_graph_live_observation_registry.py tests/test_market_event_graph_live_launch_plan.py tests/test_depth_persistence_batching.py tests/test_depth_store_accounting.py tests/test_market_event_graph_live_runtime_bridge.py tests/test_governed_morning_orchestrator.py tests/test_feed_recovery_coordinator.py tests/test_check_option_pipeline_health.py tests/test_subscription_truth_contract.py tests/test_pulse_issues_and_feed_consistency.py`. This is offline regression only; captured/live status remains UNKNOWN.

## Independent Scenario B review — 2026-10-03

Fresh read-only review at `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95` by `/root/scenario_b_independent_verify`:

- Independently reran `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_issues_7_11_scenario_b_restart.py`: **4 passed, 1 warning**.
- Confirmed the bounded Scenario B contract/test alignment: future-dated persisted row cutoff, incomplete cutoff, pre-cutoff CAS, conflicting same-session captures, cross-date/corrupt heritage, stale/mismatched spot, and closed authority fields are covered. C1 remains `C1_OUT_OF_WINDOW` at 15:14.
- Parsed all seven campaign JSON artifacts and checked `defect_graph.json`: **137 unique nodes, 145 edges, zero dangling endpoints**. These checks do not prove campaign-wide semantic closure.
- The reviewer did not rerun the recorded 201-test combined regression; that result remains executor-reported.
- Reviewer identified `WORKTREE_SOURCE_MANIFEST_20261003.json` as stale: missing new Scenario B plan/contract/test and hash mismatches for updated evidence files. The manifest is refreshed after this review entry.

Bounded independent verdict: Scenario B synthetic/offline composition verified. Overall Issues 7–11 campaign remains OPEN; live/source authority and other acceptance gates remain unproven.


## Scenario E execution evidence — 2026-10-03 (executor run)

Scenario E now composes the existing restart fixture with an actual stale required NIFTY spot block and actual advisory builder over an explicit valid-empty ledger. Focused Scenario E: **1 passed, 1 warning in 8.18s**. Direct Scenario B/E + store/producer/heritage/CAS/observer/advisory regression: **217 passed, 1 warning in 9.98s**. The test proves only offline synthetic behavior; this is not independent verification. Source authority, live service restart/parity, generic candidate isolation and campaign-wide mutation closure remain open.


## Independent Scenario E verifier attack and repair — 2026-10-03

The first fresh review found two evidence gaps: permissive authority assertions passed when fields were absent, and the pending CAS readiness receipt/result did not explicitly carry the full authority tuple. The executor narrowed the repair to additive authority metadata on `_evaluate_cas` missing-input and malformed-input pending paths, then strengthened Scenario E to compare every exact field on the producer gate, returned PENDING states, and both readiness receipts. The CAS decision/reason and successful path are unchanged.

Fresh read-only re-review at `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95` reran Scenario E: **1 passed, 1 warning**. The reviewer confirmed direct indexing makes missing fields fail, both pending paths and no-artifact outcomes are covered, and the graph has **139 unique nodes, 150 edges, zero dangling references**. The reviewer did not rerun the 217-test combined regression; that broader result remains executor-run. Overall campaign remains open with source authority, actual service restart, generic candidate isolation and captured/live parity unresolved.


## Scenario E authority omission finding, repair, and re-verification — 2026-10-03

The verifier initially found the pending CAS receipt/result lacked explicit authority markers and the test accepted missing fields. The Hermes/GSD scope was extended narrowly before the production patch. `core/read_only_consumer_cycle.py` now adds only the closed-authority tuple on missing-input and malformed-input pending receipts/results; verdict/reason behavior and successful CAS path are unchanged. Exact-key assertions cover both paths. An isolated temporary-copy mutant omitting `is_order_action` was killed at the exact assertion; checkout files were unchanged. The fresh independent re-review reran Scenario E (**1 passed**) and confirmed missing fields cannot pass. The reviewer did not rerun the 217-test combined set, which remains executor evidence. Campaign remains open.


## Exact current-tree broad offline regression after Scenario E receipt repair — executor run — 2026-10-03

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'` completed **8707 passed, 9 skipped, 29 deselected, 1474 warnings in 1027.42s; exit code 0** at `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`. Exclusions: unavailable Upstox capture dependency, large external stitched-capture scan, and the capture-backed verifier stalled in a previous run. This is executor broad offline evidence; it does not establish excluded paths, live/captured parity, or independent campaign closure.

## Scenario E CAS authority output follow-up

A fresh read-only source audit at the same repository HEAD verified that every `_evaluate_cas` return carries the exact closed-authority tuple, every readiness-receipt writing branch includes it, and the success CAS artifact includes it. Duplicate and completion-failure/status branches are included; completion-failure returns before readiness or CAS artifact writes. Exact focused assertions cover PASS result/readiness/artifact, duplicate PENDING result/readiness, completion failure PENDING result/no files, and Scenario E missing/malformed outputs. The Scenario E Hermes contract and GSD plan consistently authorize this metadata-only scope. Independent status is a bounded source audit, not a test run or campaign certification. Executor-run adjacent B/E regression: 219 passed, 1 warning; direct CAS/restart tests after adding the no-readiness-on-completion-failure assertion: 15 passed, 1 warning. Generic candidate isolation, source authority, captured/live parity, and campaign acceptance remain open.

## Exact-current-worktree broad regression after Scenario E CAS authority output change

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'` completed against repository SHA `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`: **8709 passed, 9 skipped, 29 deselected, 1474 warnings in 768.59s; exit code 0**. The exclusions are (1) Upstox capture module because its dependency is unavailable, (2) a large external stitched-capture scan, and (3) a prior capture-backed stall. This is executor-run exact-current-worktree offline evidence. It does not verify those excluded inputs, source authority, captured/live parity, generic candidate-level isolation, or campaign acceptance.

## Exact-current-worktree broad regression after Scenario E CAS authority output change

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'` completed against repository SHA `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`: **8709 passed, 9 skipped, 29 deselected, 1474 warnings in 768.59s; exit code 0**. The exclusions are (1) Upstox capture module because its dependency is unavailable, (2) a large external stitched-capture scan, and (3) a prior capture-backed stall. This is executor-run exact-current-worktree offline evidence. It does not verify those excluded inputs, source authority, captured/live parity, generic candidate-level isolation, or campaign acceptance.

## Issue 7 acquired futures report source-authority recheck

A fresh read-only reviewer confirmed hashes for `FINAL_REPORT.json` (`e62107d74c78612f85dd2bd65c0e99cc3172d2bebdfeafe4c7e4f06cc78748e8`), `SPOT_FUTURES_SYNC_MANIFEST.json` (`06d9c5d59d8dddbf5a54d4e568c0259f0b779840c04e776cc136cb7cdf85579d`), `SPOT_FUTURES_SYNC_AUTHORITY.json` (`a77b8642aff547d22d2eae7a11e9e4ba9c7e603fd7db2a9fa2afaf1b1ae01a2f`), and the contract inventory (`a6f391bbcece00582d09cf8de07f02b22845aabe2cc7ff1c967d81e41ca02b46`). The report declares `SOURCE_SHA=UNKNOWN` and ends 2026-08-25; the sync manifest contains no payload hash; the inspected directory has 15 top-level files and no parquet at any depth. The target T-1 date is 2026-09-30. The reviewer confirms the authority declaration cannot be reproduced without the absent data payload. This read-only audit keeps Issue 7 source authority UNKNOWN; no data files or live processes were modified.


### Issue 9 abrupt writer termination test — executor evidence

At current worktree HEAD before this test-only addition (`d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`), a child process exercised the real `MarketSessionStore.persist_completed_bar` method, asserted that the inserted row was visible inside its uncommitted transaction, then called `os._exit(73)` before SQLite context exit. A fresh store found no row; `PRAGMA integrity_check` returned `ok`. The test module passed 19 tests. This is executor-run offline evidence, not an independent verifier pass and not proof of actual service restart, power-loss behavior, or captured/live parity.


### Issue 9 fresh-interpreter restart replay — executor evidence

Two-process offline replay passed. The writer installed the existing bridge and persisted 30 completed `deterministic_test` bars to a temporary database. A distinct interpreter initialized a fresh store/bridge, restored the exact first/last timestamps and count, and invoked the actual C1/C2 evaluator with separately provided fresh synthetic cycle-time data; C1 returned `C1_QUALIFIED` and one candidate. Targeted test: 1 passed; `tests/core/test_market_session_runtime_bridge.py tests/core/test_market_session_store.py`: 29 passed, 1 warning. This is not independent certification, captured/live parity, managed-service lifecycle proof, or order authority.


Issue 7 calendar edge regression — executor evidence

The existing explicit eligible-session resolver was tested with Monday/weekend and post-NSE-holiday cases. The full `tests/test_market_heritage_graph.py` file passed 69 tests. The Issue 7 temporary-copy mutation harness killed five guards, including the naive target-minus-one-calendar-day mutant under each new calendar case. This is executor-run offline contract evidence; it does not independently verify the external exchange calendar's completeness or Issue 7 source/data authority.


Issue 7 shared NSE F&O calendar alignment — executor evidence

Repository inspection found duplicated calendar authority: live preflight listed the 2026 NSE F&O dates while `core.market_calendar.IN_HOLIDAYS` omitted Jan 15 (subsequent amendment), Mar 3, Mar 26, Apr 14, and Nov 10. NSE official circular FAOP/71777 lists Mar 3 and the other base dates; FAOP/72262 adds Jan 15. The canonical set now lives in `core.market_calendar`, is unioned into existing shared holiday membership, and is imported by preflight with the amendment-specific source retained. Focused session/preflight/expiry/heritage tests passed 81; targeted Issue 7 mutation harness passed 5/5. This is executor-run offline verification, not an independent calendar authority audit or T-1 data/source verification.


## Independent Issue 11 registry identity-coverage re-review — 2026-10-03

The read-only reviewer rechecked the Issue 11 registry validator, eligibility property, regression cases, and mutation harness. Empty, whitespace-only, and padded identity values fail closed through the helper/eligibility path, registry validation, and resolver even when the corresponding health-map key is marked healthy. The reviewer independently probed trailing whitespace as well. The mutation runner requires each mutant to fail its specific named assertion sentinel, with validator and eligibility checks attacked separately. Reviewer-run scoped tests: **16 passed**; both mutants were killed and checkout hashes remained unchanged. No blocker was found in this bounded scope. This does not certify generic dynamic identity-health production, Issue 11 as a whole, or campaign acceptance.


## Current-worktree broad regression — executor run, 2026-10-04

`PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'` completed on branch `ram/issues-7-11-graph-repair` at base HEAD `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`: **8724 passed, 9 skipped, 29 deselected, 1474 warnings in 985.62s; exit code 0**. This supersedes prior lower-count broad results for the current worktree. Exclusions: unavailable Upstox dependency module, large external stitched-capture scan, and the previously stalled capture-backed verifier. This is executor-run offline regression, not independent campaign certification, target-date source authority, captured/live parity, external writer inventory, or live behavior.

## Issue 10 rollback TOCTOU re-review — 2026-10-04

A fresh independent review found that the previous `fstat` then `ftruncate` rollback guard could still delete a bypass append interposed between those operations. The Hermes contract and implementation were revised: failed append handling now never truncates the shared JSONL file. The focused tests prove foreign bytes are not truncated, partial tails are reported, original errors propagate, and actual advisory parsing emits `parse_error` and admits zero rows when the incomplete prefix and foreign bytes form malformed JSONL. The destructive-truncate mutant is killed. Independent reviewer confirmed no remaining in-scope deletion blocker and verified the new consumer assertion. A bypass writer can still make its own record unparseable by appending after an incomplete prefix; external atomicity and row salvage remain UNKNOWN.

Exact focused Issue 10 suite: **53 passed, 1 warning in 10.25s**. The broad offline run passed **8724 passed, 9 skipped, 29 deselected, 1474 warnings in 966.72s** against the final runtime source. Its pytest test module was collected before the last consumer-assertion-only test edit; the exact final focused suite and mutation runner were rerun after that edit. Remote CI was not run, no PR was raised, and campaign acceptance remains OPEN.

## Fresh verifier review of 2026-10-04 bounded additions

A read-only fresh-context verifier reviewed the new Issue 11 homogeneous-score guard and Issue 7 adapter-input proof. It found no fail-open in the mixed-symbol guard, but identified that Scenario A passed `opening_drive_target_expiry` without checking the adapter field and that both new mutation scripts accepted a generic single failure as a kill. The expiry is not a T-1 loader value: the corrected fixture uses a nonempty synthetic launch-plan expiry, tests it separately from verified prior-session fields, and still asserts invocation of all three actual adapters. Both mutation harnesses now require their specific intended assertion plus an `AssertionError`. The verifier's two findings were repaired; the expiry mutant was killed at its exact assertion and the mixed-symbol mutant was also killed at its exact ranking-count assertion. These are bounded offline reviews and attacks only. Target-date source authority, exact candidate contract identity, captured/live parity, and campaign acceptance remain UNKNOWN/open.

## Exact-source campaign regression and final focused rerun — 2026-10-04

The broader offline suite completed on HEAD `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`: **8734 passed, 9 skipped, 29 deselected, 1474 warnings in 972.11s**, exit 0. Explicit exclusions: `tests/test_upstox_daily_live_capture.py` (Upstox dependency unavailable), `tests/trade_truth/test_raw_tick_expected_separation.py` (large external stitched-capture scan), and `test_v5_verifier_deep_primitive_validation` (prior capture-backed stall). Runtime source did not change during this run; a test-only addition/refinement to Scenario A expiry routing and stricter mutation-output assertions made during the run was then tested directly. Exact changed test files rerun after those changes: **92 passed, 1 warning in 5.64s**. This is offline evidence only, not source-authority/live-parity proof or campaign certification.

## Path-triggered Feed Smoke gate — 2026-10-04

The `.github/workflows/feed-smoke.yml` command passed on this worktree with isolated temp paths: **18 passed, 5 deselected, 1 warning in 227.16s**, exit 0. These are deterministic synthetic lifecycle/resource profiles; no live feed or broker call. The general workflow's `health_gate` job was deliberately not run: source inspection shows `core.health_gate.run_health_gate()` calls `run_golden_path()`, which invokes `MockBroker.place_order`; repository `AGENTS.md` prohibits agent order actions, including synthetic/mock actions. No PR was raised, so remote CI is not available. Campaign acceptance remains false.

## Independent Issue 9 same-process session boundary review — 2026-10-04

Fresh read-only review of `core/market_session_memory_contract.py` found no P1/P2 correctness issue. It confirmed aware timestamps convert to IST, naive timestamps are treated as IST, current-date filtering is applied to both merge inputs, and same-date ordering/deduplication remains unchanged. The reviewer reran the bridge/store suite (30 passed) and the local-filter-only mutation (killed at its exact timestamp-set assertion with source/test hashes unchanged). The reviewer identified a P3 test coverage gap for aware UTC and naive date conventions; three direct tests were added and passed, and the focused final bridge/store rerun passed **33 tests**. Supported 5-minute history is now explicitly verified after fresh store reopen as a derivation from canonical persisted 1-minute rows. Broad exact-source regression was still in progress at the time of this entry; no captured/live or managed-service claim is made.

The exact-source broad offline regression completed afterward: **8736 passed, 9 skipped, 29 deselected, 1474 warnings in 796.90s**, exit 0, using the three explicit exclusions recorded in `FINAL_VERDICT.json`. Final test-only timezone and reopened 5-minute assertions were run in the exact 33-test focused suite after broad collection. This does not prove running-service restart or captured/live parity.

The applicable path-triggered Feed Smoke gate was rerun after the session-memory bridge repair using isolated Issue 9 temp paths: **18 passed, 5 deselected, 1 warning in 214.14s**, exit 0. It exercises synthetic feed/resource behavior only. The separate CI health gate remains unrun because it calls `MockBroker.place_order`, prohibited by the repository agent rules.

## Independent MEG shadow-date boundary review — 2026-10-04

A fresh read-only reviewer confirmed the MEG completed-bar helper normalizes aware inputs to IST, preserves the persistence-before-read order, and filters only the returned projection without deleting shadow-buffer rows. The D-to-D+1 regression passes, and the mutation harness removes only the output filter and is killed at the exact timestamp assertion with checkout hashes unchanged. No P1/P2 finding. The reviewer noted that restore/persist helpers rely on runtime tick ingress being IST-canonical; that ingress converts source epochs to IST, so arbitrary direct non-IST internal calls are outside the tested live boundary.

The exact-current-source broad regression completed after the MEG patch: **8740 passed, 9 skipped, 29 deselected, 1474 warnings in 910.84s**, exit 0. The three explicit exclusions remain unchanged. The post-MEG Feed Smoke gate then passed **18 passed, 5 deselected, 1 warning in 216.45s** with isolated `/tmp` paths. Neither result establishes captured/live or deployment parity.

## PR-scoped worktree verification — 2026-10-04

A clean PR worktree was prepared at base SHA `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95` on `ram/issues-7-11-campaign`. It contains only the Issues 7–11 campaign patch, tests, and evidence artifacts. The two modified `TRADE_TRUTH_PROSPECTIVE_*` report files and 77 untracked files named from `MagicMock` representations were excluded from this PR. The source worktree remains untouched by this extraction.

`WORKTREE_SOURCE_MANIFEST_20261004.json` records the PR-scoped file inventory and exact SHA-256 values. It is a pre-commit snapshot bound to the base SHA and branch; it proves byte identity of this proposed patch, not authorship, runtime truth, or campaign acceptance. A second verifier recomputes the manifest after generation. Existing open PR #957 overlaps `core/kite_depth_ws.py` and feed readiness; this PR remains unmerged and requires exact-head hosted CI and conflict/review checks.

The clean PR-scoped regression command recorded in `FINAL_VERDICT.json` passed **459 tests in 40.60s**. All 15 checked-in Issue 7–11 mutation harnesses also passed, killing **27/27 targeted mutants** (Issue 7: 5, Issue 8: 6, Issue 9: 5, Issue 10: 4, Issue 11: 7). These are executor-run results in the clean PR worktree, not hosted CI or a fresh independent certification. The campaign verdict stays open: `implementation_valid=false`, `issues_7_11_offline_repair_verified=false`, `live_verified=false`. Issues 7/8 source authority, Issue 9 deployed restart/capture parity, Issue 10 external-writer/capture parity, Issue 11 generic candidate dependency isolation and initiating cause, and complete campaign mutations remain unresolved or `UNKNOWN`. No live, broker, order, risk, strategy-threshold, or token-universe authority is inferred from this source audit.
