# MEG Shadow Offline Certification — 2026-08-04

- Verdict: `PASS_OFFLINE_MEG_SHADOW_CONTRACTS`
- Tested branch head: `a2cf86b5ca624e179661f68394d7cd47548f9abb`
- Tested PR merge SHA: `5cb34cfdbf66846d9b991b7d223f0fc7019abf4e`
- Source report semantic SHA-256: `d7b6d8051949bf1a56e306f5e6c13f4da1be54a2a60b19aabd24a6fb81ccd3c4`
- Retained certificate semantic SHA-256: `9e0ed483fac3aab25468f4a86c160af21d1181a10f965033ea7f8b4432ba9345`
- Workflow run: `30849955485`
- Workflow artifact SHA-256: `9cb74603045ff2133b383f2c10185bad5a2ffce759ce74be66a35d191beadf07`
- Read only: `true`
- Order authority: `false`
- Broker-write authority: `false`
- Paper execution allowed: `false`
- Live execution allowed: `false`

## Eight gates

| Gate | Result | Test invocations |
|---|---:|---:|
| Authentication and startup | PASS | 20 |
| Feed and subscription truth | PASS | 43 |
| Persistence and shutdown | PASS | 57 |
| Market Event Graph observation | PASS | 40 |
| Authority, ranking and UI | PASS | 24 |
| Manual approval and broker firewall | PASS | 16 |
| Restart and reconciliation | PASS | 62 |
| AI reliability and evidence integrity | PASS | 170 |

Total gate test invocations: `432`. Some files intentionally appear in more than one gate; this is not a unique-test count.

## Restart isolation evidence

The restart gate passed in five independent processes:

- websocket restart suite: `53 passed`;
- PR #763 reconciliation suite: `6 passed`;
- three terminal runtime-store lifecycle tests: `1 passed` each.

This preserves the runtime contract that shutdown is terminal within a process while preventing one successful shutdown test from contaminating an independent startup test.

## Remaining gate

`FRESH_PR763_MARKET_SESSION`

A governed market-hours session must still prove post-mode FULL NIFTY packets, completed constituent bars, Market Event Graph traversal, clean persistence drain and shutdown, and immutable evidence sealing.

This certificate does not claim profitability, structural edge, broker connectivity, real fills, paper/live execution readiness, or unattended autonomy.
