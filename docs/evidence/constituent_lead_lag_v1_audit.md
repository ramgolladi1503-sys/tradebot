# Constituent Lead–Lag V1 Certification Repair Audit

## Current status

The source-level certification defects identified after commit
`64294990e4ecda3fa3d345e388faa78f890c5eaf` were repaired in commit
`08da792fd7a5fd50fd6dfc6589f26caf429c6322`. The repository quality-proof
repairs were completed in commit
`e48f10fc03ef1cdca6b350d9b873c5804e512faf`.

The earlier v2 certification claim is **not retained**. Classify it as:

`INVALID_INCOMPLETE_CERTIFICATION_CONTRACT`

The v3 real-data campaign has now been rebuilt from the preserved local Upstox
and proxy inputs under:

`/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v3`

The repaired independent oracle returned `PASS`, so the final frozen taxonomy is:

`NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT`

The following v2 claims must not be presented as currently certified evidence:

- `NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT`;
- completed/eligible/post-warm-up session counts;
- count and weight coverage summaries;
- weighted and unweighted state reasons;
- weighted or unweighted signal counts;
- control, delay, concentration or fold results;
- the previous oracle `PASS`.

The v1 and v2 evidence directories should remain preserved as historical,
invalidated bundles. They must not be overwritten.

## Repaired code contracts

### Exact return-bar ownership

Weighted signals, unweighted signals and membership coverage now share one
exact-bar contract. A return at decision cutoff `T` requires bars at exactly:

- `T - 10 minutes`;
- `T - 5 minutes`;
- `T`.

Stale or merely earlier bars no longer count as valid availability. Missing
required index bars fail closed. Missing constituent timestamps reduce the same
constituent set used by both the signal calculation and coverage calculation.

### Coverage identity

State-level coverage now records and reconciles:

- active point-in-time constituents;
- resolved active constituents;
- constituents with the exact required bars;
- count coverage;
- active and available snapshot weight;
- weight coverage;
- missing constituents and exact missing timestamps.

The oracle compares coverage row identities and numeric coverage values against
weighted state rows. Comparing only row counts is no longer sufficient.

### Session policy

The session audit now distinguishes:

- `REGULAR_SESSION_COMPLETE`;
- `REGULAR_SESSION_PARTIAL`;
- `SPECIAL_SESSION_OUT_OF_FROZEN_CONTRACT`;
- `MISSING_REQUIRED_INDEX_GRID`.

Special sessions are explicit frozen-contract exclusions rather than silently
being called corrupt or partial regular sessions.

### Controls and sensitivities

For non-zero fixtures:

- the matched no-lead control selects unique non-signal state identities and
  preserves side and decision-time distributions;
- delayed-entry analysis performs a real additional one-bar delay and emits
  numeric outcomes and exclusions;
- concentration analysis emits numeric monthly, session, top-five-session,
  decision-time and side concentration measures.

For a genuinely zero-signal weighted campaign these lanes report
`NOT_APPLICABLE_ZERO_SIGNALS`.

### Independent oracle

The v3 oracle imports no strategy implementation. It independently verifies:

- mandatory frozen file ownership and SHA-256 hashes;
- the pre-outcome freeze hash;
- required artifact presence and hashes;
- campaign window and decision times;
- completed-session and theoretical-state arithmetic;
- weighted and unweighted row/reason/signal reconciliation;
- coverage row identity and count/weight reconciliation;
- control, delay and concentration summaries;
- every prerequisite for the final zero-signal taxonomy.

Legacy call compatibility remains fail closed as
`LEGACY_BUNDLE_NOT_CERTIFIABLE`; it cannot produce a v3 `PASS`.

## Validation completed

The GitHub runner successfully applied the allow-listed repair payload,
compiled the repaired modules and passed the complete focused command covering:

```bash
pytest -q \
  tests/research/test_constituent_data_pipeline.py \
  tests/research/test_reconstructed_weight_proxy.py \
  tests/research/test_constituent_lead_lag.py \
  tests/research/test_unweighted_constituent_breadth.py \
  tests/research/test_certification_repair.py \
  tests/research/test_reconstructed_proxy_oracle.py
```

The command collected 48 tests. The first integration run exposed one backward-
compatibility failure (`47 passed, 1 failed`); that defect was repaired without
weakening the oracle, and the identical six-module command then passed.

After strengthening weak assertion patterns and making the research non-action
defaults statically unambiguous, the same 48-test command passed again. The
scoped Minerva test-reality gate, Cerberus safety gate and mandatory agent-review
evidence validator also passed before the quality-repair commit was pushed.

Synthetic certification tests include a complete valid fixture that first
returns oracle `PASS`, followed by independent artifact tampering that forces
`FAIL`.

## Completed v3 evidence run

Evidence was built under:

`/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v3`

The v2 invalidation artifact was created before current certification:

`/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/invalid_64294990_certification_contract/INVALIDATION.json`

with classification:

`INVALID_INCOMPLETE_CERTIFICATION_CONTRACT`

Final v3 facts:

- normalized bars SHA-256: `ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0`;
- session policy SHA-256: `c53a016f5da7791944241efafbe64d945ace83c80297996948f1062aeef59765`;
- session grid SHA-256: `b6916ead1bd4e38596abb6d5081b184a0f0af04eb508abb8c8a47d9318314a37`;
- completed regular sessions: `409`;
- special sessions excluded: `5`;
- post-warm-up sessions: `389`;
- theoretical weighted and unweighted state rows: `4,090`;
- actual weighted and unweighted state rows: `4,090`;
- weighted signals: `0`;
- unweighted signals: `1`;
- coverage gate pass rate: `1.0`;
- control, delay and concentration: `NOT_APPLICABLE_ZERO_SIGNALS`;
- oracle report: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v3/oracle/oracle_report.json`.

Tamper proof was run against copied fixtures only. The baseline copy returned
`PASS`; mutating the persisted coverage summary and mutating the persisted
summary weighted-signal prerequisite each forced oracle `FAIL`. The tampered
copies were removed, and the proof is recorded at:

`/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v3/tamper/tamper_proof_report.json`

## Safety

Research only. PR #709 must remain draft and unmerged. No broker calls, order
actions, production strategy registration, execution/risk/feed changes,
dashboard changes, threshold tuning or commercial use are authorized.
