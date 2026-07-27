# PR #718 Deep Logic Audit

## What was missing

The option archive contained many candles but not broad signal-date ATM coverage. The acquisition selected a small strike wing around the expiry-day opening price and then fetched those contracts for the preceding seven days. The pre-resume run also contributed 539,076 rows from materially mis-centred strikes.

The signal campaign introduced a separate distortion: it stopped after the first eligible raw candidate in each strategy/session. Historical option premium change, spread, depth and freshness were not supplied, while raw candidates were still converted into replay intents. The strategy's stated option-confirmation trigger was therefore not tested.

## Frozen exploratory lane

The deep audit isolates Late-Day Momentum bearish proposals and requires causal option confirmation from completed PE candles. The frozen comparison uses the nearest corrected PE within 100 NIFTY points of signal-time ATM, a positive five-minute premium change, minimum entry premium of INR 30, next-minute entry within 120 seconds, a fixed 20-minute exit and 5 bps per side.

Development produced 37 observations with PF 1.5719. The previously observed validation period produced 13 observations with PF 2.3152. The opposite-option control lost in both partitions, with PF 0.4938 and 0.5118. Results also remained above one after 25 and 50 bps cost stress and after removing the single largest winner.

## Limitation

This is exploratory evidence only. The prior validation period was examined while selecting the hypothesis and is no longer untouched certification evidence. The sample is small and loses robustness after removing the two largest winners. Holdout remains sealed.

Verdict: `PROMISING_RESEARCH_HYPOTHESIS_NOT_CERTIFIED`.
