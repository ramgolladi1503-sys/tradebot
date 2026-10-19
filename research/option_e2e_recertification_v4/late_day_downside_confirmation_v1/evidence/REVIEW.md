# PR #718 Deep Logic Audit

## What was missing

The option archive contained many candles but not broad signal-date ATM coverage. The acquisition selected a small strike wing around the expiry-day opening price and then fetched those contracts for the preceding seven days. The pre-resume run also contributed 539,076 rows from materially mis-centred strikes.

The signal campaign introduced a separate distortion: it stopped after the first eligible raw candidate in each strategy/session. Historical option premium change, spread, depth and freshness were not supplied, while raw candidates were still converted into replay intents. The strategy's stated option-confirmation trigger was therefore not tested.

## Frozen exploratory lane

The deep audit isolates Late-Day Momentum bearish proposals and requires causal option confirmation from completed PE candles. The frozen comparison uses the nearest corrected PE within 100 NIFTY points of signal-time ATM, a positive five-minute premium change, minimum entry premium of INR 30, next-minute entry within 120 seconds, a fixed 20-minute exit and 5 bps per side.

Development produced 37 observations with PF 1.5719. The previously observed validation period produced 13 observations with PF 2.3152. The opposite-option control lost in both partitions, with PF 0.4938 and 0.5118. Results remained above one after 25 and 50 bps cost stress, a three-minute delay and removal of the single largest winner.

## Independent integrity review

The result is not robust enough for certification:

- removing the two largest winners reduces development PF to 0.9599 and the previously observed validation PF to 0.6950;
- the validation partition has only 13 trades;
- the validation period was examined while choosing bearish side, strike distance, premium confirmation, entry floor and holding period;
- all source intents are `RAW_CANDIDATE`, not historical executable-strategy truth;
- the 20-minute exit is a newly frozen research overlay, not the production strategy's native outcome contract;
- the compact evidence does not include the full 50-trade ledger, so the published metrics require external-ledger reproduction before publication-grade closure;
- the runner accepts a caller-supplied inventory and does not itself prove that only the stated 820 corrected/post-resume contracts were supplied.

The older underlying directional-PF package has separately been marked `INVALID_IMPLEMENTATION` because its current entrypoint explicitly removes proxy PnL and cannot reproduce the retained leaderboards.

## Required next gate

Do not tune this hypothesis further. Freeze it exactly as documented and evaluate it only on untouched future data or on holdout after explicit authorization. The next evidence package must include:

1. immutable intent, inventory and archive hashes;
2. a compact but independently reconcilable trade ledger;
3. proof that the inventory contains only corrected/post-resume contracts;
4. an independent oracle for expiry, strike, confirmation, entry and exit;
5. a minimum sample gate defined before outcomes are read;
6. no additional side, threshold, holding-period or strike-distance search.

## Verdict

`PROMISING_RESEARCH_HYPOTHESIS_NOT_CERTIFIED`

No profitable strategy or production readiness is claimed. Holdout remains sealed.
