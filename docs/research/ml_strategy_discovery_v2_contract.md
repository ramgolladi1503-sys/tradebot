# ML Strategy Discovery V2 Research Contract

## V1 Evidence
- V1 Audit Verdict: `BOTH_CANDIDATES_UNSTABLE`
- V1 LONG Candidate ID: `tree_rule_edb855245d2f`
- V1 SHORT Candidate ID: `tree_rule_7a6855962eee`

## Validation Rules
- V1 Validation split has been completely consumed and is strictly forbidden for V2 candidate selection, tuning, or threshold setting.
- Existing `HOLDOUT_LOCKED` dataset remains untouched and is not to be used.
- The V1 LONG candidate (`tree_rule_edb855245d2f`) may be retained only as a fixed benchmark rule and must never be retuned.
- The V1 SHORT candidate (`tree_rule_7a6855962eee`) is entirely rejected.
- Any fresh OOS data identified during the inventory phase must remain outcome-locked until a stable V2 rule is successfully frozen.

## Safety and Edges
- This research contract strictly adheres to safety boundaries; no structural edge or profitability claims are made here.
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `append=false`
