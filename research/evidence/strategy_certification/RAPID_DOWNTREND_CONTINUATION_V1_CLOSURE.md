# RAPID_DOWNTREND_CONTINUATION_V1 — CLOSURE

Status: CLOSED_FAILED_LOCKED_VALIDATION

Runtime authority: NONE
Broker actions permitted: false
Edge claimed: false

## Frozen family

Family: `RAPID_DOWNTREND_CONTINUATION_V1`
Candidate tested: `RAPID`

Frozen definition:
- `formation_bars <= 16`
- `middle_to_second_bars <= 10`
- `confirmation_delay_bars <= 4`

No post-lock retuning is permitted under this family identity.

## Development evidence

Development parent episodes: 104
Development RAPID episodes: 22

Parent down-30-bps rate: 0.3627450980392157
RAPID down-30-bps rate: 0.6363636363636364

Parent down-20-bps rate: 0.49019607843137253
RAPID down-20-bps rate: 0.8181818181818182

Development verdict: PASS and single nomination of `RAPID`.

## One-time locked validation

Locked sessions consumed: 99
Locked outcomes accessed: true
Locked parent episodes: 43
Locked RAPID episodes: 11

Locked parent down-30-bps rate: 0.3333333333333333
Locked RAPID down-30-bps rate: 0.3333333333333333

Locked parent down-20-bps rate: 0.4358974358974359
Locked RAPID down-20-bps rate: 0.3333333333333333

RAPID 6-bar return on locked sample:
- n: 9
- mean: +10.36786503800359 bps
- median: +8.311571778620852 bps

RAPID 12-bar return on locked sample:
- n: 7
- mean: +5.503432266374476 bps
- median: +2.257806319081457 bps

Locked verdict: `LOCKED_VALIDATION_FAIL`

Reasons:
- `INSUFFICIENT_LOCKED_EPISODES`
- `PRIMARY_RATE_BELOW_CHARACTERIZATION_PARENT`

## Scientific interpretation

The temporal-compactness pattern observed during characterization did not replicate in the one-time locked period. The locked sample did not show improved 30-bps downside excursion versus the locked parent, showed a worse 20-bps downside excursion rate, and the available 6/12-bar return summaries were positive rather than negative.

Therefore this family does not establish a reproducible structural edge and must not be promoted, certified, traded, or retuned against the consumed locked period.

The correct result is negative evidence, not rescue.

## Reuse prohibition

The final 99-session block has now been consumed for this family. It must not be treated as pristine validation data for any descendant that materially reuses this same rapid-downtrend hypothesis or tunes thresholds/features in response to this locked result.

A future successor would require a materially new causal question and a new untouched validation source.
