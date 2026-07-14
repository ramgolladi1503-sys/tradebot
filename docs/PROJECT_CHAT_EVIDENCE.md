# Tradebot Project Chat Evidence

This document captures Tradebot lessons that came from project chats, debugging sessions, handoff summaries, and design discussions.

GitHub issues and PRs show the formal record. Project chats explain why those issues and PRs existed in the first place.

Use this document together with:

- [Historical engineering log](HISTORICAL_ENGINEERING_LOG.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [Branch protection policy](BRANCH_PROTECTION.md)

---

## 1. Core operating principle

Repeated project-chat rule:

```text
engine produces truth -> snapshots publish truth -> dashboard reads truth
```

Why this matters:

- The dashboard must not invent, recompute, or silently mutate trading truth.
- Runtime artifacts should be the source of truth for feed state, trade state, decision status, blockers, and health.
- If the dashboard disagrees with engine logs, the dashboard is not the authority.

Release impact:

- Dashboard changes must be reviewed as persistence/schema changes, not cosmetic UI changes.
- Any dashboard crash or missing column should trigger schema and runtime-artifact review.

---

## 2. Path and artifact consistency problems

Past chat diagnosis:

- Empty dashboard states such as `No trades logged yet` were often caused by wiring/path inconsistency, not strategy failure.
- The project needed one consistent path contract for logs and trade databases.

Important path-contract guidance from project chats:

- Use `core.paths.logs_dir()`.
- Use configured trade DB paths such as `cfg.TRADE_DB_PATH`.
- Use a resolver such as `core.trade_log_paths.resolve_trade_log_path()`.
- Avoid hardcoded paths such as `Path("logs/...")` and `Path("data/...")` in runtime-critical paths.

Release impact:

- Any change touching logs, SQLite, review queue, dashboard loaders, or reports must check path consistency.
- Dashboard bugs must not be assumed frontend-only until artifact paths are verified.

---

## 3. Deterministic health gate design

Project-chat design target:

```bash
python -m core.health_gate --desk DEFAULT --strict
```

Expected health-gate scope from chats:

- Path contract check.
- Golden-path synthetic trade using mock broker and simulated feed.
- Assert event flow contains intent, submitted, and fill-style lifecycle evidence.
- Run reconciliation projection.
- Validate dashboard loaders can read artifacts.
- Block live readiness on P0 failures.

Release impact:

- `ci / health_gate` is not optional process decoration.
- Health-gate artifacts are release evidence.
- A release is weak if health gate passes but dashboard loaders or runtime artifacts are broken.

---

## 4. Feed runtime and websocket failures

Repeated chat findings:

- `kite_depth_ws` was seen with runtime state stopped/down.
- Some runs had no websocket messages and no subscribed tokens.
- Other runs showed live runtime with connected websocket and subscribed option tokens, but clean restarts later produced subscribe failures.
- Feed blocks appeared as `NO_LIVE_OPTION_FEED`, stale feed, disconnected feed, or blocked readiness.

Operational evidence patterns discussed in chats:

```text
.runtime/logs/feed_runtime_latest.json
decision stream
ws_connected
subscribed_option_tokens_count
option_feed_block_reason_by_symbol
```

Release impact:

- Feed work must validate both startup state and sustained runtime state.
- A successful old run does not prove the next clean restart works.
- Runtime logs must be checked after restart, not only after hot patches.

---

## 5. Websocket startup, lock, and tick-reset lessons

Past chat findings:

- `run_live.sh` and websocket startup behavior were not always aligned.
- Engine and websocket components could conflict through shared lock behavior.
- Startup/reset paths could reset last tick epoch to zero and make the system think live feed was dead.
- A safer feed-age computation needed to use an effective timestamp from websocket, depth data, or DB evidence instead of blindly trusting one global variable.

Release impact:

- Startup/reconnect changes require clean-start validation.
- Feed-age logic must not be clobbered by startup resets.
- Locks for engine and feed components must be reviewed when runtime state is stopped/down.

---

## 6. Feed-health contradiction and single-source rule

Past chat finding:

- Feed-health contradictions happened when readiness used one snapshot while gating used another cached or secondary source.
- Some checks incorrectly required index depth when option feed was the real execution dependency.

Project-chat invariant:

```text
compute feed_health once per cycle and consume it everywhere
```

Release impact:

- Do not allow readiness, execution gate, dashboard, and reports to compute conflicting feed states.
- If the system says both recovered and blocked, feed-health source ownership is broken.

---

## 7. Depth subscription window design

Past chat design:

- NIFTY depth window: ATM plus/minus 6 strikes, step 50.
- BANKNIFTY depth window: ATM plus/minus 6 strikes, step 100.
- SENSEX depth window: ATM plus/minus 4 strikes, step 100.
- Expected upper token range around 73 to 80 tokens.
- Always include underlying tokens.
- Keep sticky active-trade tokens.
- Respect `DEPTH_SUBSCRIPTION_MAX_TOKENS`.
- Drop farthest OTM first if budget is exceeded.

Release impact:

- Feed subscription changes must prove option-token coverage and token-budget behavior.
- Never drop underlying tokens to make room for noisy contracts.

---

## 8. Contract resolution and option instrument lessons

Past chat work:

- Option instrument matching needed to accept CE/PE-style rows, not only old labels such as OPTIDX/OPTSTK.
- Diagnostics needed counters such as total rows scanned, matched option rows, expiry matches, strike-window matches, and final token count.
- Zero-token outcomes needed explicit failure reasons.

Release impact:

- Contract-resolution work must include diagnostic counters.
- Miss-ing strike, expiry, right, token, or instrument identity must block execution or downgrade candidate stat-us.
- Resolver fallback must stay bounded and visible.

---

## 9. No executable trades and blocker visibility

Repeated chat theme:

- The system sometimes produced rows but not executable trades.
- Root causes included stale feed, no live option feed, contract failures, confidence/execution gap, and risk-budget failure.

Concrete past example from chats:

- A candidate could be downgraded to queue-only because the risk engine lacked stop-distance geometry.
- Missing entry, stop, target, or risk/reward geometry means scoring is premature.

Release impact:

- Trade geometry must exist before execution scoring.
- Bug reports for no executable trades must include blocker counts and candidate-status transitions.
- A row being displayed is not proof that the system has a tradable opportunity.

---

## 10. Candidate soft-reject and recoverable candidate split

Past chat finding:

- `candidate_soft_reject` behavior could make soft rejects advisory-only too early.
- That caused real-ranked counts to collapse and synthetic/advisory rows to dominate.

Project-chat fix direction:

- Split recoverable softened candidates from advisory-only synthetic artifacts.
- Use a separate prefix and lifecycle for promotable softened candidates.
- Preserve `strategy_family` and `source_flags`.

Release impact:

- Soft reject does not always mean permanently advisory-only.
- Recoverable weak-signal candidates and synthetic artifacts need different lifecycles.

---

## 11. Fallback execution and ranking quality problems

Past chat evidence:

- Fallback execution flags were used during forced live experiments.
- Ranking quality suffered when many candidates had similar confidence and fallback-derived data.
- A UI screenshot/review highlighted weak score separation, many BUY rows, `recovered_fallback`, and lack of real prioritization.

Release impact:

- Fallback-derived data must not be treated as equal to real executable market data.
- Ranking must separate real opportunities from fallback, planning, synthetic, advisory, and softened rows.
- A top-ranked row must explain why it is better, not merely survive filters.

---

## 12. Dashboard field drift and UI runtime failures

Past chat/UI issues:

- Dashboard crashes occurred from missing runtime variables or fields.
- Examples included missing selected-column variables, incomplete symbol display, missing entry/stop/target, and date parsing warnings.
- Dashboard warnings were a symptom of schema drift, not harmless noise.

Release impact:

- Dashboard checks must verify key fields such as symbol, strike, right, side, entry, stop, target, confidence, blocker, status, and timestamp.
- Missing fields must degrade gracefully.
- The dashboard should not silently recompute persisted trading truth.

---

## 13. Scorecard and daily regression semantics

Past chat findings:

- Scorecards could report many failures during phases where checks should have been skipped.
- A missing trade log should not always be treated as a hard failure.

Project-chat rules:

- Use phase-aware scorecards: PREMARKET, INTRADAY, POSTMARKET.
- Treat no trades as a sentinel state when appropriate.
- Differentiate `HASH_SKIPPED_NO_TRADES` from `HASH_FAILED`.
- Daily regression reports should rank issues by priority and blast radius.

Release impact:

- Reporting scripts must distinguish failure, skipped, no-data, and no-trades states.
- Governance docs should not incentivize fake green checks.

---

## 14. Backtesting and execution reality

Project-chat requirement:

A realistic backtest needs four data layers:

1. Index or spot data.
2. Option contract daily data.
3. Intraday option-chain data with bid, ask, and OI when possible.
4. Execution reality: slippage, partial fills, and rejections.

Release impact:

- Backtest claims are weak if they ignore bid/ask and execution reality.
- Strategy improvements should not be called production-grade without realistic execution assumptions.

---

## 15. Pro strategy layer and shadow-only evidence

Recent chat context:

- A pro strategy evidence pipeline was introduced in discussion with shadow logging, outcome labeling, lifecycle, conflict analysis, alpha report, and tests.
- The important constraint was that it remained shadow-only and not wired into live execution.

Release impact:

- Shadow evidence is useful but must not be marketed as live execution proof.
- Any future wiring from shadow-only to live must go through strict PR and release checks.

---

## 16. Current clean-run constraint from chats

Recent project-chat constraint:

- Do not merge additional runtime changes until a clean run proves either stable websocket subscription or a clearly explained feed block.

Release impact:

- Documentation-only PRs are safe to review separately.
- Runtime PRs that claim feed/live readiness need clean-run evidence.

---

## 17. Chat-derived issue categories

Use these categories when opening future issues based on past project chats:

- `feed-runtime`
- `stale-feed`
- `contract-resolution`
- `no-executable-trades`
- `execution-truth`
- `fallback-candidate`
- `risk-geometry`
- `dashboard-schema`
- `path-contract`
- `health-gate`
- `scorecard-semantics`
- `backtest-reality`
- `shadow-strategy`
- `release-readiness`

---

## 18. Chat-derived release evidence checklist

For fixes based on project-chat history, capture:

```text
Chat-derived problem:
Formal issue/PR link if available:
Subsystem:
Observed artifact/log:
Root cause:
Fix or mitigation:
Validation command:
Health-gate status:
Runtime artifact checked:
Remaining risk:
```

---

## Bottom line

The project chats add the miss_ing reasoning layer behind the GitHub history.

The most important chat-derived lessons are:

- runtime artifacts beat dashboard assumptions
- feed health must have one owner
- fallback data is not execution truth
- contract identity is mandatory
- no-executable-trades needs blocker visibility
- dashboard bugs often expose schema/runtime drift
- health-gate evidence matters
- clean restart validation matters more than a lucky hot run
