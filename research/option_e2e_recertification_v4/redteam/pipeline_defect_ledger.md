# Option E2E Recertification v4 Pipeline Red-Team Defect Ledger

Subagent: C
Scope: read-only shared option pipeline red-team audit
Worktree: `/Users/madhuram/tradebot-option-e2e-pipeline-redteam-v4`
Branch: `audit/option-e2e-pipeline-redteam-v4`
Foundation commit: `b02cc64adf88c9ee876a03469b3f63ad762ccc2b`
Campaign under audit: `all-strategy-option-e2e-recertification-v4`

## Scope Boundaries

Owned write paths:

- `research/option_e2e_recertification_v4/redteam/**`
- `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md`

Prohibited and not modified:

- `core/**`
- `strategies/**`
- shared schemas
- production/runtime wiring
- strategy thresholds
- fixes or repairs
- final certification verdicts

Safety invariants preserved:

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `append=false` for committed foundation artifacts

## Setup Evidence

- Source repo: `/Users/madhuram/tradebot-all-strategy-option-e2e-recertification-v4`
- Worktree create command:
  - `git -C /Users/madhuram/tradebot-all-strategy-option-e2e-recertification-v4 worktree add -b audit/option-e2e-pipeline-redteam-v4 /Users/madhuram/tradebot-option-e2e-pipeline-redteam-v4 b02cc64a`
- Worktree checkout warning:
  - `Encountered 1 file that should have been a pointer, but wasn't: runtime/strategy_validation/resolved_option_ticks_20260702.parquet`
  - This path is outside audit ownership and was not touched.
- Branch evidence:
  - `git rev-parse --abbrev-ref HEAD` -> `audit/option-e2e-pipeline-redteam-v4`
- HEAD evidence:
  - `git rev-parse HEAD` -> `b02cc64adf88c9ee876a03469b3f63ad762ccc2b`
- Required manifest sidecar content:
  - `sed -n '1,80p' research/option_e2e_recertification_v4/foundation_manifest.json.sha256`
  - Output: `118cc813127005e75e6eec94aa197a1795648d70d3311356c61fb9885275c37b  foundation_manifest.json`
- Sidecar file hash:
  - `shasum -a 256 research/option_e2e_recertification_v4/foundation_manifest.json.sha256`
  - Output: `22829c0a1f69e7f249da523df6a9f382e2b8e0e391336940e2a7f4ffeb78250e  research/option_e2e_recertification_v4/foundation_manifest.json.sha256`
- External evidence root from manifest:
  - `/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4`
  - Local check result: `find: /Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4: No such file or directory`

## Validation Run

Focused foundation tests:

```bash
PYTHONPATH=. pytest -q tests/research/option_e2e/test_foundation_contracts.py
```

Result:

```text
11 passed in 3.15s
```

Plain `python` repro snippets were intentionally interrupted after they hung in interpreter startup. The stack shows repo `sitecustomize.py` imports `core/longrun_stability_contract.py`, then `core/torture_test.py`, `core/health_scenarios.py`, `core/review_queue.py`, and `core/orders/**` before the requested research imports run. Repro snippets below therefore use `python -S` as a false-positive control to avoid importing runtime startup hooks during read-only research contract checks.

## Defect Ledger

### RT-C-001: Gate records can pass with invalid or mismatched reason codes

Severity: High
Confidence: High
Affected campaigns: `all-strategy-option-e2e-recertification-v4`; any downstream campaign consuming `GateRecord` as certification evidence.
Evidence:

- `research/option_e2e_recertification_v4/evidence_schema.py:25` defines gate-specific failure reason codes.
- `research/option_e2e_recertification_v4/evidence_schema.py:80` through `110` validates gate id, non-empty hashes, live-safety flags, and optional upstream hash only.
- No check ties `status`, `gate_id`, and `reason_code` together. A `PASS` can carry a failure reason, a `FAIL` can carry a success reason, and a G6 record can carry a G9 failure code.

Minimal reproduction proposal:

```bash
PYTHONPATH=. python -S - <<'PY'
from research.option_e2e_recertification_v4.evidence_schema import GateRecord, GateStatus
record = GateRecord(
    gate_id="G6",
    strategy_id="ORB",
    input_manifest_hash="in",
    output_artifact_hash="out",
    status=GateStatus.PASS,
    reason_code="G9_ECONOMICS_INVALID",
)
record.validate()
print("accepted")
PY
```

Expected audit result: this should fail closed because a G6 `PASS` must not carry a G9 failure reason.
False-positive controls:

- Use `python -S` to avoid runtime `sitecustomize.py` imports.
- Repeat with `status=GateStatus.FAIL` and `reason_code="TRADE_EVALUATED"`; that should also fail under a hardened contract.
- Confirm existing safety flags still reject live/broker/order mutations using the focused pytest command above.

Repair proposal only, not implemented: require a per-gate allowed reason-code map and enforce legal `status`/reason combinations before a gate record can be serialized or consumed.

### RT-C-002: Entry quote validation accepts impossible quote age and incomplete exit-side liquidity

Severity: High
Confidence: High
Affected campaigns: all option replay/economics gates G6-G9 in `all-strategy-option-e2e-recertification-v4`; any strategy whose option fill is certified from `ExecutableQuote`.
Evidence:

- `research/option_e2e_recertification_v4/replay_bridge.py:15` stores `quote_age_seconds`.
- `research/option_e2e_recertification_v4/replay_bridge.py:18` through `28` rejects quote age only when greater than max age; negative ages pass.
- Entry validation requires positive `ask_qty` but does not require positive `bid_qty`, even though the same quote object exposes `long_exit_fill()` from bid at `research/option_e2e_recertification_v4/replay_bridge.py:35`.
- This can let replay accept an entry quote that cannot prove coherent executable bid-side liquidity for the same option snapshot.

Minimal reproduction proposal:

```bash
PYTHONPATH=. python -S - <<'PY'
from research.option_e2e_recertification_v4.replay_bridge import ExecutableQuote
quote = ExecutableQuote(
    ts="2024-01-01T10:00:02+05:30",
    bid=99.0,
    ask=100.0,
    bid_qty=0,
    ask_qty=1,
    volume=1,
    oi=1,
    quote_age_seconds=-999.0,
    symbol="NIFTY24JAN22000CE",
)
quote.validate_for_long_entry("2024-01-01T10:00:01+05:30", max_quote_age_seconds=60.0)
print("accepted")
PY
```

Expected audit result: this should fail closed for negative quote age and incomplete executable liquidity.
False-positive controls:

- Compare with current positive test `tests/research/option_e2e/test_foundation_contracts.py::test_executable_quote_uses_ask_for_entry_bid_for_exit_and_rejects_stale_quotes`.
- Verify a valid quote with non-negative age and positive bid/ask quantities still passes.

Repair proposal only, not implemented: require `0 <= quote_age_seconds <= max_quote_age_seconds`, positive `ask_qty` for entry, and either positive `bid_qty` at entry certification time or a separate validated exit quote contract before any evaluated trade can be counted.

### RT-C-003: Decision reconciliation accepts negative row counts and does not require complete stage inventory

Severity: Medium
Confidence: High
Affected campaigns: G10 reconciliation for `all-strategy-option-e2e-recertification-v4`; downstream dashboards or selection gates that trust aggregate counts.
Evidence:

- `research/option_e2e_recertification_v4/reconciliation.py:4` through `22` coerces missing keys to zero and does arithmetic equality checks only.
- Negative counts are accepted if totals balance.
- Missing stage keys are accepted as zero, which can mask an omitted pipeline stage in an artifact writer.

Minimal reproduction proposal:

```bash
PYTHONPATH=. python -S - <<'PY'
from research.option_e2e_recertification_v4.reconciliation import reconcile_decision_counts
reconcile_decision_counts({"signals": -1, "direction_rejected": -1, "replay_attempted": 0})
print("accepted")
PY
```

Expected audit result: this should fail closed because row counts must be non-negative and required stage keys must be present.
False-positive controls:

- Run the existing reconciliation positive test to confirm valid non-negative counts still pass.
- Add a control case with all required keys present and `signals == 0`; decide explicitly whether empty campaigns are `BLOCKED` or valid no-op evidence.

Repair proposal only, not implemented: validate required keys, non-negative integer counts, and stage coverage before aggregate equality checks.

### RT-C-004: Canonical signal validation does not reject non-finite signal strength or inconsistent session/date identity

Severity: Medium
Confidence: Medium
Affected campaigns: G1 signal contract and all candidate-building stages for `all-strategy-option-e2e-recertification-v4`.
Evidence:

- `research/option_e2e_recertification_v4/signal_contract.py:20` through `32` defines `signal_strength`, `session`, and timestamps.
- `research/option_e2e_recertification_v4/signal_contract.py:34` through `49` checks required string fields and lexicographic timestamp ordering only.
- No check rejects NaN or infinite `signal_strength`.
- No check requires `session` to match the local trading date of `signal_ts`, so cross-session leakage can enter as long as timestamp strings are ordered.

Minimal reproduction proposal:

```bash
PYTHONPATH=. python -S - <<'PY'
from math import nan
from research.option_e2e_recertification_v4.signal_contract import CanonicalSignal, Direction
signal = CanonicalSignal(
    strategy_id="ORB",
    signal_id="s1",
    session="2024-01-02",
    feature_cutoff_ts="2024-01-01T09:59:59+05:30",
    signal_ts="2024-01-01T10:00:00+05:30",
    earliest_entry_ts="2024-01-01T10:00:01+05:30",
    direction=Direction.BULLISH,
    signal_strength=nan,
    params_hash="p",
    source_hash="s",
    is_oos=False,
    fold_id="dev",
)
signal.validate()
print("accepted")
PY
```

Expected audit result: this should fail closed for non-finite strength and session/date mismatch.
False-positive controls:

- Verify a finite-strength signal with same local session date remains valid.
- Use timezone-aware timestamp parsing in any future reproducer; lexicographic examples should not be the only evidence source.

Repair proposal only, not implemented: require finite numeric strength and explicit parsed timestamp/session consistency.

### RT-C-005: Point-in-time contract validation does not prove contract identity hashes or expiry/metadata consistency

Severity: Medium
Confidence: Medium
Affected campaigns: G3 contract universe, G4 expiry, G5 strike, and G8 replay linkage.
Evidence:

- `research/option_e2e_recertification_v4/point_in_time_contract_universe.py:8` through `23` stores `trading_symbol`, `instrument_token`, `expiry`, `dataset_hash`, `metadata_hash`, and `point_in_time_source`.
- `research/option_e2e_recertification_v4/point_in_time_contract_universe.py:25` through `35` checks identity presence, NIFTY underlying, positive terms, source presence, and listing interval only.
- It does not check that `dataset_hash` or `metadata_hash` are present/non-empty.
- It does not tie `expiry` to `listed_until` or to the trading symbol.
- `reject_current_master_as_historical_authority()` at lines `38` through `40` rejects only exact `current_instrument_master`, so case, spacing, or provider aliases can bypass the helper unless callers normalize source kinds.

Minimal reproduction proposal:

```bash
PYTHONPATH=. python -S - <<'PY'
from research.option_e2e_recertification_v4.point_in_time_contract_universe import OptionContractMetadata
from research.option_e2e_recertification_v4.signal_contract import OptionRight
contract = OptionContractMetadata(
    trading_symbol="NIFTY24JAN22000CE",
    instrument_token="123",
    underlying="NIFTY",
    option_right=OptionRight.CE,
    strike=22000.0,
    expiry="2099-01-01",
    tick_size=0.05,
    lot_size=50,
    listed_from="2024-01-01T09:15:00+05:30",
    listed_until="2024-01-25T15:30:00+05:30",
    provider="fixture",
    dataset_hash="",
    metadata_hash="",
    point_in_time_source=" Current_Instrument_Master ",
)
contract.validate_at("2024-01-01T10:00:00+05:30")
print("accepted")
PY
```

Expected audit result: this should fail closed for missing hashes, expiry/listing mismatch, and unnormalized current-master source.
False-positive controls:

- Repeat with valid non-empty hashes and matching expiry/listing date.
- Test known allowed historical source kinds to avoid rejecting legitimate archived masters.

Repair proposal only, not implemented: normalize source kind, require non-empty content hashes, require a provider-specific symbol/expiry identity check, and encode the exact historical source authority in the artifact.

### RT-C-006: WFA partition validation only checks chronological date strings and a boolean flag

Severity: Medium
Confidence: Medium
Affected campaigns: G12-G14 WFA, selection freeze, and holdout contamination checks.
Evidence:

- `research/option_e2e_recertification_v4/wfa.py:6` through `14` stores partition bounds and `holdout_opened`.
- `research/option_e2e_recertification_v4/wfa.py:16` through `27` checks lexical chronology and `holdout_opened`.
- There is no immutable selection hash, artifact access ledger, or dataset identity proving the holdout was not loaded under another code path before selection freeze.

Minimal reproduction proposal:

```bash
PYTHONPATH=. python -S - <<'PY'
from research.option_e2e_recertification_v4.wfa import WFAPartition
partition = WFAPartition(
    development_start="2024-01-01",
    development_end="2024-06-01",
    validation_start="2024-06-02",
    validation_end="2024-12-01",
    holdout_start="2024-12-02",
    holdout_end="2025-01-01",
    holdout_opened=False,
)
partition.validate_before_selection_freeze()
print("accepted_without_selection_or_access_hashes")
PY
```

Expected audit result: this object alone should be insufficient to certify G13/G14.
False-positive controls:

- Treat this as a contract incompleteness finding, not proof that holdout contamination occurred.
- Require artifact-access evidence from future subagents before escalating from potential defect to confirmed contamination.

Repair proposal only, not implemented: require selection-freeze hash, partition dataset hash, and holdout access audit hash in the WFA evidence contract.

## Campaign-Level Risk Summary

The current committed foundation is a useful contract skeleton, but it is not yet a certifying option E2E pipeline. The main red-team risk is false certification: artifacts can appear structured and safety-flagged while still accepting invalid gate reasons, incomplete executable quote evidence, negative/missing counts, weak signal identity, weak contract provenance, and insufficient WFA contamination proof.

This audit does not assert that any strategy is profitable, paper-ready, live-ready, or fully recertified. It also does not assert that defects occurred in a downstream campaign run because the external evidence root recorded in the manifest is absent locally.

## Commands for Reviewers

```bash
cd /Users/madhuram/tradebot-option-e2e-pipeline-redteam-v4
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
sed -n '1,80p' research/option_e2e_recertification_v4/foundation_manifest.json.sha256
shasum -a 256 research/option_e2e_recertification_v4/foundation_manifest.json.sha256
PYTHONPATH=. pytest -q tests/research/option_e2e/test_foundation_contracts.py
git status --short
```

## Files Modified or Created

- Created `research/option_e2e_recertification_v4/redteam/pipeline_defect_ledger.md`
- Created `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md`

## Rollout Notes

No rollout. This is a read-only audit artifact and must not be wired into runtime, strategy selection, broker adapters, or live/paper execution paths.
