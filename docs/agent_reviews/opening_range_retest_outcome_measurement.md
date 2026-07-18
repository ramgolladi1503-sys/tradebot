# Opening Range Retest Outcome Measurement

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Publish ORB underlying outcome measurement evidence
- scope: Bounded evidence summary for research-only descriptive underlying outcome measurement on the certified ORB candidate ledger.
- requested_paths: `docs/agent_reviews/opening_range_retest_outcome_measurement.md`, `docs/agent_reviews/opening_range_retest_outcome_measurement_v1.json`, `docs/agent_reviews/opening_range_retest_outcome_measurement_v1.json.sha256`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: full-corpus generation A/B, independent audit A/B comparison, evidence JSON validation, SHA-256 sidecar validation
- acceptance_proof: `AUDIT_INVALID`

## Scope Guard

This evidence is bounded PR documentation only. It does not include full per-candidate ledgers in git, does not modify source data, does not calculate option P&L, does not modify production files, and does not call brokers.

## Evidence Verdict

`AUDIT_INVALID`

## Scope

This is research-only underlying-price outcome measurement for the certified ORB candidate ledger. It does not claim strategy edge, profitability, option P&L, fills, slippage, latency, broker correctness, paper readiness, live readiness, capital allocation readiness, or production promotion.

## Repository Evidence Fields

- mode: RESEARCH_UNDERLYING_OUTCOME_MEASUREMENT_EVIDENCE
- candidate_id: opening_range_retest_outcome_measurement_v1
- decision: AUDIT_INVALID
- reason: Superseded: prior outcome certification is withdrawn pending corrected horizon, source-integrity, overlap, and independent-oracle repairs.
- timestamp: 2026-07-19T04:35:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/opening_range_retest_outcome_measurement.md

## Frozen Execution

- Code SHA: `648da6914959925ca1d10775aad3ce3f5c269f93`
- Run A: `/tmp/orb-certified-outcomes-648da691-a`
- Run B: `/tmp/orb-certified-outcomes-648da691-b`
- Run A summary hash: `790393a7e3a9ffc615f189f8497eaa9bcf421924d57f61000221bc7ce8ea7a1d`
- Run B summary hash: `790393a7e3a9ffc615f189f8497eaa9bcf421924d57f61000221bc7ce8ea7a1d`
- Outcome semantic hash: `84d031bf046fcc35c4abd2c8554e0042a94873a05d057f45b651fc139426380a`
- A/B semantic equality: `true`

## Certified Inputs

- Candidate count: `2215`
- Candidate semantic hash: `53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24`
- Source count: `1512`
- Source-universe hash: `cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc`
- Certified merged-main summary hash: `34b7c8628e28c436a2b18a1d9598077d2e08e0eab09009748e06c2ed41eb9074`

## Candidate Accounting

- `MEASURED`: `2206`
- `NO_LEGAL_ENTRY`: `9`
- Duplicate directional exposure count: `1`

`NO_LEGAL_ENTRY` candidates are retained because their proposal time has no strictly later underlying bar in the certified source session. They are not dropped or counted as measured entries.

## Grill Me Review

This evidence proves deterministic underlying movement accounting only. The `NO_LEGAL_ENTRY` rows are explicit terminal statuses for candidates whose proposal time has no strictly later bar, not silent exclusions.

## Hermes Review

The measurement contract preserves the Phase 1 signal identity and source universe. It binds each candidate to certified read-only underlying bars by session and symbol, enforces first-bar-after-proposal entry timing, and records path events without changing strategy behavior.

## GSD Review

The generator and auditor now support full-corpus execution, deterministic semantic hashing, explicit candidate statuses, and A/B artifact comparison. The published JSON is bounded evidence; the full run directories remain external artifacts under `/tmp`.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

- Run A verdict: `ORB_OUTCOMES_MEASURED`
- Run B verdict: `ORB_OUTCOMES_MEASURED`
- Independent audit verdict: `ORB_OUTCOME_AUDIT_READY`
- A/B semantic equality: `true`
- Candidate accounting: `2215`
- Published JSON sidecar validation: `opening_range_retest_outcome_measurement_v1.json: OK`

## Runtime Proof Required After Merge

If this PR is merged, repeat the bounded evidence verification on exact merged `origin/main` before making any downstream claim that depends on ORB outcome artifacts. Do not treat this PR as production promotion or edge certification.

## What This PR Does Not Prove

This PR does not certify structural edge, profitability, option P&L, option fills, spread realization, slippage, latency, paper readiness, live readiness, execution readiness, capital allocation readiness, broker correctness, or production promotion.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.

## Safety Fields

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false
