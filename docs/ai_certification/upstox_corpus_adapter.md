# Upstox corpus certification adapter

## Objective

Classify an existing Upstox replay directory or ZIP without copying raw market data or assuming every file is eligible for the same claim.

## Evidence lanes

| Classification | Permitted use |
|---|---|
| `FUTURES_VOLUME_ELIGIBLE` | Futures-level price structure, truthful volume and VWAP research. |
| `POSITIVE_VOLUME_IDENTITY_UNCONFIRMED` | Quarantined until futures contract identity is proven. |
| `PRICE_STRUCTURE_ONLY` | OHLC, ATR, support/resistance and causal chronology only; no volume/VWAP claim. |
| `OPTION_QUOTE_REPLAY_CANDIDATE` | Candidate for strict option replay after contract, expiry, freshness and executable-side validation. |
| `TICK_QUOTE_CONTROL` | Runtime ordering, freshness and bounded quote controls. |
| `MANIFEST_OR_METADATA` | Provenance and acquisition metadata. |
| `INVALID` | Unreadable, empty, unsafe or missing required chronology. |

## Fail-closed rules

- Positive volume does not prove futures identity.
- Zero-volume index candles cannot support VWAP certification.
- Bid/ask columns only create an option-replay candidate; they do not prove fresh executable fills.
- Unsafe ZIP member paths are rejected and never extracted.
- Every scanned file is hashed.
- The adapter writes only a manifest; it never mutates the source corpus.

## Run

```bash
python scripts/build_upstox_certification_manifest.py \
  /Users/madhuram/tradebot/runtime/upstox_candidate_replay \
  --output .runtime/ai_certification/upstox_manifest.json
```

A ZIP can be supplied instead of a directory. The resulting manifest should be reviewed before any dataset is passed to `OptionBacktestEngine` or a structural research tool.
