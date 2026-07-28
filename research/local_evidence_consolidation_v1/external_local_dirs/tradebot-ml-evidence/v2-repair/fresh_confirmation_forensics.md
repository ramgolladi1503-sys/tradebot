# Fresh Confirmation Forensics

## Verdict
`FRESH_CONFIRMATION_OUTCOMES_CONSUMED`

## Summary
The previous run of the ML Strategy Discovery V2 pipeline accessed the `FRESH_CONFIRMATION_V2_LOCKED` data explicitly during candidate filtering before freezing. `label_return_r` and `expectancy` were loaded and evaluated.

1. **Were labels generated for fresh rows?** Yes.
2. **Were fresh outcomes loaded into memory?** Yes.
3. **Were fresh rows used for selection, rejection...** Yes, candidates with non-positive fresh expectancy were rejected.
4. **Were fresh results serialized or logged?** Yes, as `fresh_oos_expectancy_r` in the report.
5. **Was candidate freeze completed before fresh access?** No, access occurred during the selection filter loop.
6. **Was a candidate-bound acknowledgement required?** No.
7. **Was a one-time token consumed?** No.
8. **Can the same fresh data be evaluated repeatedly?** Yes, under the old code.
9. **Did both LONG and SHORT inspect fresh outcomes?** Yes.
10. **What exact dates/rows were accessed?** Any dates matching `FRESH_CONFIRMATION_V2_LOCKED` (> 2026-07-10) present in the `ml_strategy_discovery_v2_1_source_manifest.json`.

Because these outcomes were evaluated during the candidate filter step rather than locked behind an acknowledgement token, the previous data set is permanently compromised. Future verification runs must use newer data.

`NEED_NEW_FRESH_CONFIRMATION_DATA`
