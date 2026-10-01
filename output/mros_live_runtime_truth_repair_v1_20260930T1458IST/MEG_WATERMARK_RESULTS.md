# MEG watermark results

- A required completed constituent appearing after approximately 700 ms within an 800–900 ms configured grace was accepted by the synthetic offline test.
- A permanently missing identity timed out; no output row was written or synthesized.
- A snapshot over the configured decision freshness cap was rejected.
- The existing bridge suite was made process-isolated around `feed_epoch`; no behavior assertion was removed.
- Metrics now expose attempted/emitted/rejected, incomplete/timeout, rejection rate, max consecutive rejection, missing identities, and maximum observed completion latency.

Focused tests passed. Grace is synchronous and can add up to the configured (runtime-clamped) 2 seconds to the bridge call; production downstream latency suitability remains unverified. The specified 20-second-missing-source live/replay case was represented by timeout behavior but no real-time 20-second wait was executed; the synthetic timeout unit test uses 50 ms.
