# Opening Range Retest Causal Replay Phase 1

mode: RESEARCH_REPLAY_REVIEW
candidate_id: opening_range_retest_causal_replay_phase1_review
decision: OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY
reason: Two full-corpus ensembles on frozen clean commit d977e69efecfe7c9702e6b57290616e491671773 converged on identical replay semantics and both independent audits passed on Saturday, July 18, 2026.
timestamp: 2026-07-18
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/opening_range_retest_causal_replay_phase1.md

**Agent Work Contract**
source_agent: Codex
action: HARDEN_PR
title: Complete ORB replay certification hardening and bounded evidence publication for PR #668
scope: Opening Range Retest replay contract hardening, shard certification, oracle reconciliation proof, independent audit strictness, bounded evidence publication, and PR/body/check follow-through only
requested_paths: research/opening_range_retest, scripts/generate_opening_range_retest_causal_replay.py, scripts/audit_opening_range_retest_causal_replay.py, tests/test_four_strategy_contract_freeze.py, tests/test_opening_range_retest_*.py, docs/agent_reviews/opening_range_retest_causal_replay_*
allowed_paths: docs/agent_reviews, research/opening_range_retest, scripts/generate_opening_range_retest_causal_replay.py, scripts/audit_opening_range_retest_causal_replay.py, tests/test_four_strategy_contract_freeze.py, tests/test_opening_range_retest_causal_replay.py, tests/test_opening_range_retest_temporal_fixture_contract.py, tests/test_opening_range_retest_oracle_reconciliation.py, tests/test_opening_range_retest_merge_certification.py
forbidden_paths: strategies/, core/, config/, broker adapters, runtime execution paths, live credentials, shared corpus roots, main.py, run_live.sh
expected_tests: ORB replay suites three times, ORB contract/oracle/merge/audit coverage, py_compile, ruff, git diff --check, agent review evidence, Minerva, Evidence, Cerberus, unified CE, full repo pytest
acceptance_proof: Replay artifacts must certify a clean frozen SHA, strict shard completeness, strict oracle reconciliation, ledger sidecars, independent audit recomputation, and cross-topology semantic equality.

**Scope Guard**
In scope: research-only ORB replay contract identity, shard merge strictness, oracle/control proofs, bounded evidence artifacts, and PR evidence updates.
Out of scope: production strategy logic, broker calls, risk/feed/runtime wiring, live or paper execution behavior, strategy threshold changes, fills, slippage, or profitability claims.
Files not touched: strategies/, core/, config/, credentials, live runtime paths, broker code, and authoritative corpus roots.

**Grill Me Review**
Original failure: commit `f743620eda4eafccaff43a1ae70a7a7336f839d2` was diagnostic only because it did not fully certify code SHA/clean-state identity, profile identity resolution, ledger sidecars, or the independent merge/audit proof set.
Final proof: diagnostic ensembles on `f743620e` were stopped, the missing hardening was added, two new frozen commits were created, and the final clean checkpoint `d977e69efecfe7c9702e6b57290616e491671773` produced matching 12-shard and 13-shard results with successful independent audits.
Remaining risk: this proves causal replay integrity only for the selected historical corpus and frozen manifest, not execution truth or economic edge.

**Hermes Review**
Boundary status: pass. The work stayed under research, tests, scripts, and `docs/agent_reviews`.
Architecture result: shard partitioning is deterministic by SHA-256 canonical session key, merge rejects incomplete or mixed identity, and the auditor independently recomputes semantic evidence before accepting READY.
Constraint kept: Child B oracle hardening was integrated by exact patch equivalence, not by broad file similarity or runtime wiring.

**GSD Review**
Implementation result: replay contract identity was completed, merge fail-closed conditions were tightened, ledger sidecars were enforced before parse, the auditor was upgraded to recompute ledger and execution metadata evidence, and negative tests were added for mixed SHA, dirty shard, absent ledger sidecar, ledger count mismatch, and ledger tampering boundaries.
Frozen implementation commits: `e17b7e54457b508cc0a02948ff42b2f7431d3583` closed the main certification gap set, and `d977e69efecfe7c9702e6b57290616e491671773` fixed the auditor ledger-order defect that invalidated the prior rerun.
Published evidence: contract, source manifest, summary, and bounded candidate ledger were regenerated from the converged `d977e69e` ensemble output.

**QA / Safety Review**
Safety boundary: read-only replay only; no order placement, no broker calls, no live execution permission, and no writes into source corpus roots.
Certifying identity now recorded and checked: code SHA `d977e69efecfe7c9702e6b57290616e491671773`, clean worktree, production file SHA-256 `06be67cf8bac5b4d4901929b77e638c726a6b4910f646d20780e584327144b2e`, contract hash `6c0a9f1a5bee45e9404b54de86eecadfb1861561a3eee0aa76f03bf217a2e1a8`, requested profile `opening_range_retest_v1`, resolved profile `opening_range_breakout_v1`, resolution source `COMPATIBILITY_ALIAS`, runtime profile hash `80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064`, dataset manifest SHA-256 `cdba301fa89cfe428d4fd143dda99595e7f8044e681b393731c0e10e0ae18a88`, inventory SHA-256 `29f29443cf99606081f4276132e9747f1dcc1671a061093af8c8b8dc26c1902e`, and source-universe hash `cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc` over 1512 selected records.
Cross-topology semantics: both ensembles converged to candidate hash `53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24` and canonical summary hash `e8012eaa521e6bfa90491cb4d244c49055cc4be21fa2d480a0acc0fb45d9a9eb`.

**Acceptance Proof**
Current status: satisfied for the stated replay boundary.
Topology A: 12 shards, root `/tmp/opening-range-retest-certifying-a-d977e69e`, merge READY, audit READY, elapsed runtime `24981.367823582957` seconds.
Topology B: 13 shards, root `/tmp/opening-range-retest-certifying-b-d977e69e`, merge READY, audit READY, elapsed runtime `25850.240662290133` seconds.
Independent bounded evidence: `docs/agent_reviews/opening_range_retest_causal_replay_candidate_ledger_v1.json` publishes all 2215 candidate records plus counts by symbol, direction, session, duplicate-setup scan results, and proposal-ready bounds for independent recomputation.

**Post-Merge Verification**
Status: complete for exact merged `origin/main=140025d8fc288c2a1c24351e1b242a54bd6a0576`.
Post-merge smoke: `/tmp/orb-postmerge-final-140025d8-smoke-1784401556`, verdict READY, independent audit READY.
Post-merge 12-shard replay: `/tmp/orb-postmerge-final-140025d8-12shard-1784401606`, merged verdict READY, independent audit READY.
Post-merge invariants: selected source count `1512`, source-universe hash `cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc`, candidate count `2215`, candidate semantic hash `53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24`, partition assignments `1512`, malformed sessions `0`, oracle mismatches `0`, future-mutation failures `0`, and source mutations `0`.
New commit-bound canonical summary semantic hash: `34b7c8628e28c436a2b18a1d9598077d2e08e0eab09009748e06c2ed41eb9074`.
Final ORB Phase 1 verdict: `ORB_POSTMERGE_VERIFIED`.

**Runtime Proof Required After Merge**
No additional ORB Phase 1 replay proof is required for current merged `origin/main=140025d8fc288c2a1c24351e1b242a54bd6a0576`.
If `origin/main` advances with ORB replay code, source-manifest logic, audit logic, strategy behavior, profile identity, or corpus selection changes, rerun post-merge replay verification for that new exact commit.
Still not proven by this replay boundary: live runtime stability, regenerated-manifest byte identity from changing source roots, or any live execution property.

**What This PR Does Not Prove**
This PR proves causal signal replay integrity only.
It does not prove structural trading edge, exact VWAP truth, option execution truth, fills, spread behavior, latency, slippage, paper readiness, live readiness, or profitability.
It also does not prove the historical manifest can be regenerated byte-for-byte from future source roots; reproducibility remains bounded to the published manifest and inventory artifacts used by the certified rerun.

**Human Approval**
Human approval is still required before merge because this PR republishes certifying replay evidence and changes the acceptance boundary for ORB research artifacts.
Current merge recommendation: do not merge PR #668 automatically; merge only after the exact remote-head workflows are green and the review state is explicitly accepted by a human.
