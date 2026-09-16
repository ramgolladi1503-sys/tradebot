# TradeBot Operator Cockpit V1

## Status

Implementation branch: `ui/operator-cockpit-v1`
Base: PR #912 head `19686be1ebcbb5fffcc6006fe9b3a2fb1fbdd340` (stacked intentionally so the Upstox capture contract is present without pretending PR #912 is merged to main).

## Frozen source boundaries

- **Kite / TradeBot** remains the operational market-data, strategy, candidate, risk and advisory path.
- **Upstox** remains an independent read-only full-mode capture/archive path.
- The UI may observe both sources but MUST NOT average, reconcile into a synthetic price, fail over, or substitute one source for the other.
- Upstox health MUST NOT make Kite health green, and Kite health MUST NOT make Upstox health green.
- No broker write authority, order authority, paper authority or live execution authority is introduced by this UI.

## V1 primary cockpit

1. System health strip
2. NIFTY / BANKNIFTY / SENSEX market cards
3. Market state + trend/reversal levels
4. Feed/tick health
5. Pipeline pulse
6. Top opportunities
7. Candidate funnel
8. Strategy monitor
9. Risk/safety state
10. Session analytics

## Secondary surfaces

- Upstox option-chain drawer: read-only, source-labelled.
- Engineering diagnostics drawer: reconciliation, raw depth, events, raw artifacts and debug details are demoted from primary navigation.

## Upstox UI contract

The dashboard reader accepts only the repository-owned daily snapshot named `upstox_live_option_chain_snapshot.json` beneath the existing Upstox capture date directory. It never authenticates with Upstox, creates subscriptions, reconnects the streamer, changes the strike window, writes capture chunks or controls stitching.

A missing, malformed or stale snapshot fails closed in the UI.

## Non-claims

- UI health is not structural-edge evidence.
- A displayed candidate is not proof of profitability or execution viability.
- Upstox capture health is not Kite runtime health.
- A WebSocket connection alone is not proof that ticks are fresh or complete.
- V1 does not create a new ranking formula.
