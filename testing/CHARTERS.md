**Adhoc Charters**
Each charter is a guided exploration. Capture findings, anomalies, screenshots, and timestamps.

Market data ingestion
1. Simulate a mid‑session disconnect, reconnect, and verify no duplicate ticks and no missing candles.
2. Inject 5 minutes of ticks with a different timezone and confirm session mapping.

Feature engineering
1. Feed only 10 candles and confirm all indicators degrade safely without NaN spillover.
2. Create a zero‑volume segment and verify ATR and VWAP behave safely.

Strategy logic and scoring
1. Force regime flip near boundaries and confirm strategy selection stability.
2. Validate entry trigger logic on a rising option price with strict BUY_ABOVE.

Risk and position sizing
1. Drive daily loss to the threshold and verify the lockout is enforced immediately.
2. Run a volatility spike and confirm size scales down across all strategies.

Order lifecycle
1. Approve a trade, simulate a partial fill, and verify PnL and SL/target updates.
2. Force stale quotes and confirm the order is blocked before approval.

State and persistence
1. Restart during an open trade and ensure no duplicate suggestion occurs.
2. Corrupt a log entry and verify the system skips safely without crash.

Performance and reliability
1. Replay high‑frequency ticks and monitor CPU and memory for leaks.
2. Force websocket reconnect loop and verify backoff is applied.

Security and compliance
1. Trigger an exception and confirm secrets are masked in logs.
2. Review logs for accidental PII or API keys.

Observability
1. Inspect every suggested trade and confirm a reason trail exists.
2. Validate alert throttling under repeated failures.
