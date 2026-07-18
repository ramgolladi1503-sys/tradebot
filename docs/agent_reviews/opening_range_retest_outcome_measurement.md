# Opening Range Retest Outcome Measurement

## Evidence Verdict

`ORB_OUTCOMES_MEASURED`

## Scope

This is research-only underlying-price outcome measurement for the certified ORB candidate ledger. It does not claim strategy edge, profitability, option P&L, fills, slippage, latency, broker correctness, paper readiness, live readiness, capital allocation readiness, or production promotion.

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

## Safety Fields

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false
