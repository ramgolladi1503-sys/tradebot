# ORB Option Bid/Ask Recoverability Verdict

Primary verdict: NO_LOCAL_TRUSTED_OPTION_BID_ASK

Answer: the local TradeBot data corpus does not already contain trustworthy, timestamped option-level entry ask and exit bid data for the current certified corrected candidate universe of 2215 candidates.

Evidence: local option-named and option-symbol tick files expose bid/ask columns, but the inspected option-symbol rows had zero positive non-crossed bid/ask values. Zero bid/ask and empty depth are not executable top-of-book evidence.

Additional blocker: the candidate ledger only identifies underlying symbol, direction, session date, and proposal-ready timestamp. It does not identify expiry, strike, CE/PE, instrument key/token, or required exit timestamps. Without those owners, matching local option quotes to the 2215 candidates would require inventing a selector, which this task forbids.

Quote freshness authority: strict option replay defaults to a 60-second maximum quote age, rejects quote timestamps after candle timestamps, rejects stale rows, and rejects invalid/crossed bid/ask rows. No executable bid/ask rows exist to apply that policy to the candidate universe.

Economic verdict preserved: INSUFFICIENT_TRUSTED_OPTION_DATA.

No economic calculation, replay, data fetch, strategy change, or source dataset mutation was performed.
