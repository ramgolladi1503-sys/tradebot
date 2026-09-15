# CAS Regulatory Guardrails — 2026-09-15

## Why this change exists

The 2026-09-15 Indian session combined two different phenomena that TradeBot must not conflate:

1. a normal continuous-market macro risk-off repricing; and
2. expiry/closing-auction microstructure volatility.

The NIFTY 50 closed at 23,118.6, down 1.19%, after an early positive move. Contemporary reporting attributed the broad risk-off pressure to elevated crude oil, rising global bond yields, rupee pressure and rate expectations. This is contextual evidence, not a new trading rule.

Separately, SEBI published a consultation paper on 2026-09-12 reviewing Closing Auction Session mechanics, market timings and derivative-settlement methodology. The consultation is not an effective rule and therefore must not mutate TradeBot runtime authority.

## TradeBot decisions

### 1. Do not turn consultation proposals into runtime rules

The following items are recorded only as proposals:

- blended expiry settlement using the last 30 minutes of continuous trading plus closing-auction trades;
- temporary use of the final 30 minutes of continuous trading for expiry settlement;
- possible reduction of the post-auction derivatives window to five minutes;
- possible restrictions on order cancellation outside a 1% reference band;
- possible suppression of estimated index closing levels during the auction.

All proposal-derived execution flags remain false.

### 2. Quarantine auction observations from ordinary directional training

TradeBot's already-frozen research contract is preserved:

```text
14:45–15:15  NORMAL_LATE_SESSION
15:15–15:20  CAS_REFERENCE_TRANSITION
15:20–15:30  CAS_ORDER_DISCOVERY
15:30–15:35  CAS_MATCHING
15:35–15:40  DERIVATIVE_CONVERGENCE
```

Only `NORMAL_LATE_SESSION` is eligible to be treated as ordinary continuous-market late-session training evidence. Closing-auction and convergence observations are explicitly quarantined from ordinary directional-model training.

This does **not** claim that the above research windows are permanent exchange rules. They remain the frozen TradeBot study contract until authoritative effective circulars are separately reviewed.

### 3. Keep macro context diagnostic-only for now

The 2026-09-15 session supports collecting macro context such as crude oil, US yields, USD/INR, domestic yields and breadth. It does not justify inventing thresholds and promoting them directly into trade authorization.

Examples of evidence we want to preserve in future research:

- positive index open while breadth and rate-sensitive sectors deteriorate;
- rising crude + rising yields + weakening INR during an index rally.

No broker, execution, strategy-selection, risk-limit or order path is changed by this PR.

## Attack model

The tests intentionally attack the policy by:

- flipping every consultation-derived runtime flag to true and requiring a hard failure;
- testing every phase boundary to the second;
- testing timezone conversion at the 15:15 boundary;
- testing naive timestamps;
- verifying that no auction/convergence phase can become ordinary continuous-training evidence;
- verifying that pre-consultation dates do not receive future proposal metadata.

## Promotion rule

A future SEBI/NSE circular may change runtime behavior only after all of the following are available:

1. authoritative circular identity and publication date;
2. explicit effective date;
3. exact exchange/segment applicability;
4. settlement/timing semantics represented in a new policy version;
5. boundary and adversarial tests;
6. PR review and green CI.

Until then the September 12 consultation is governance metadata only.

## Sources reviewed

- SEBI, 2026-09-12 consultation paper: `Review of certain aspects of the Closing Auction Session, Market Timings and Settlement Methodologies for Derivative Contracts`.
- Reuters, 2026-09-12 and 2026-09-15 reporting on the SEBI derivatives-settlement proposals.
- Reuters, 2026-09-15 reporting on the Indian market sell-off, crude oil, bond yields and rupee pressure.
