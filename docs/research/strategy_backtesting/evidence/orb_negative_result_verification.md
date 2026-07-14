# ORB negative result verification

Date: 2026-07-14
Worktree: `/Users/madhuram/.codex/worktrees/tradebot/orb-candle-validation`
Branch: `agent/codex-orb-candle-validation`
Commit verified: `3c369185ebd26b174a4b89b6d4b31af1be8578f8`

## Verification conclusion

`NEGATIVE_RESULT_CONFIRMED`

The committed ORB candle result is negative for the tested candle-research methodology and is not explained by a direction bug, timestamp bug, or signal-oracle mismatch.

- signal-level verdict: `ORB_SIGNAL_EDGE_NOT_SUPPORTED`
- OHLCV research-policy verdict: `NO_STRUCTURAL_EDGE`

## Correctness checks

- direction mismatches: `0`
- return mismatches: `0`
- maximum absolute return difference: `0.0`
- timestamp violations: `0`
- cross-session trade violations: `0`
- signal-oracle mismatches: `0`
- first mismatch: `None`

## Statistical evidence

- effective sessions with activity in the committed 60-session sample: `53`
- session-block mean-return CI (95%): `(-0.0005479610165920424, -0.00010984641569645342)`
- session-block median-return CI (95%): `(-0.00042144001478829887, 3.0634797813846053e-06)`
- session-block win-rate CI (95%): `(0.328125, 0.5)`
- permutation p-value against zero directional association: `0.0092`
- mean percentile in permutation null: `0.0046`
- profitable sessions: `18`
- losing sessions: `35`

## Sample stability

The negative conclusion is stable across multiple deterministic slices of the same historical corpus.

### Full NIFTY corpus

- sessions: `505`
- signals: `13095`
- accepted trades: `1345`
- gross sum: `-0.05940465568538866`
- net sum: `-0.3284046556853887`
- avg net: `-0.0002441670302493596`
- median net: `-0.00019391591798647562`
- win rate: `0.42156133828996284`
- profit factor: `0.6158312876311497`
- max drawdown: `-0.33124725167349933`

### Alternate deterministic 60-session sample

- sessions: `60`
- signals: `1598`
- accepted trades: `162`
- gross sum: `0.01013989679860916`
- net sum: `-0.02226010320139084`
- avg net: `-0.0001374080444530299`
- median net: `-0.0001549377367932812`
- win rate: `0.4444444444444444`
- profit factor: `0.7745361178764473`
- max drawdown: `-0.028236800131384365`

### First half of full corpus

- sessions: `252`
- signals: `6137`
- accepted trades: `656`
- gross sum: `-0.026442631077143064`
- net sum: `-0.15764263107714307`
- avg net: `-0.00024030888883710836`
- median net: `-0.00020902567824240253`
- win rate: `0.4268292682926829`
- profit factor: `0.6614491725037682`
- max drawdown: `-0.15935293971172024`

### Second half of full corpus

- sessions: `253`
- signals: `6958`
- accepted trades: `689`
- gross sum: `-0.0329620246082456`
- net sum: `-0.1707620246082456`
- avg net: `-0.0002478403840468006`
- median net: `-0.00018844302507650107`
- win rate: `0.41654571843251087`
- profit factor: `0.5612547368024958`
- max drawdown: `-0.1756431285460029`

### BANKNIFTY replication

- sessions: `483`
- signals: `9871`
- accepted trades: `1112`
- gross sum: `0.0015543596645880564`
- net sum: `-0.22084564033541196`
- avg net: `-0.00019860219454623378`
- median net: `-0.00019052422126699647`
- win rate: `0.44064748201438847`
- profit factor: `0.7271150101448653`
- max drawdown: `-0.23249934581843004`

The full-corpus, alternate-sample, first-half, second-half, and BANKNIFTY checks all remain negative or near-neutral, which makes the committed negative result generalizable enough to retain.

## Diagnostic interpretation

- there is some early favorable excursion after entry
- the fixed-horizon exit model still bleeds edge away
- the base signal set does not outperform matched null controls
- there is no evidence of a profitable structural edge in this candle methodology

## Strict replay lane

The strict option-replay lane remains separate and blocked by data:

`INVALID_DUE_TO_DATA`
