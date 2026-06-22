# Candidate Outcome Calibration Plan

Future paper outcomes will automatically resolve using the `resolve_candidate_outcomes.py` script. The `calibrate_ranking_scores.py` script will group candidates by score buckets and calculate their empirical edge. 

## Edge Proof
`execution_ok` does not prove an edge. It only proves the gate passed. True edge is proven by analyzing `outcome_label` across statistically significant sample sizes in the calibration report.
