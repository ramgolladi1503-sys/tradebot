# Independent Audit of Real NIFTY ML Discovery Runs (No Holdout)

## Repository-Required Fields
- **mode**: ML_STRATEGY_DISCOVERY_AUDIT_V1
- **candidate_id**: tree_rule_edb855245d2f, tree_rule_7a6855962eee
- **decision**: AUDIT_FAILED
- **reason**: Failed exact source record identity checks
- **timestamp**: 2026-07-21T13:30:00Z
- **source**: agent-independent-reconstruction
- **read_only**: true
- **is_order_action**: false
- **broker_api_called**: false
- **allowed_for_live_execution**: false
- **append**: false

## Artifact Provenance & Inputs
- **LONG Evidence**: `/Users/madhuram/tradebot-ml-evidence/nifty-long`
- **SHORT Evidence**: `/Users/madhuram/tradebot-ml-evidence/nifty-short`
- **Certified source manifest**: `/Users/madhuram/tradebot-ml-evidence/certified-source/opening_range_retest_causal_replay_source_manifest_v2.json` (SHA-256: 3390fad00ae40f0ab77eb05386fb8e04af3127081843dba63b8a3af050b40926)

## Exact Source Counts
The source record audit evaluated the certified manifest and the LONG/SHORT source adapters. The expected dataset record count (1,512) failed to match across the pipeline due to path escapes or missing exact SHA matches in the adapter manifests.

## Exact Candidate Metrics & Validation Folds
Unable to complete the rigorous metric, fold, or control comparisons on validation datasets because the core audit aborted early in Phase 4 due to invalid evidence / missing candidates (`candidate.json` absent). 

## Rule-Oracle Result
The independent deterministic rule reconstruction was attempted but aborted prior to oracle evaluation due to missing valid candidate inputs.

## Holdout Proof
Holdout outcomes were **never accessed**. The dataset structures enforced block-level ignorance of `HOLDOUT_LOCKED` data. `holdout_consumed` remains explicitly `false`.

## Exact Verdict
**SOURCE_PROVENANCE_INVALID**

## Limitations
The audit could not evaluate base-rate lift or temporal concentration due to the failure in the data ingestion pipeline (Stage 1-4).

## Conclusion
**NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN**
