# Semantic Gap Audit

## Which parts are syntax-level only?
The current Strategy Truth Engine operates strictly at the syntax and keyword level:
- Extracting docstrings and matching text against keywords (e.g., "VWAP", "RSI").
- Scanning variable and function names for substrings like `rank`, `exec`, `score`.
- Discovering dependencies by reading `ast.Import` lists.
- Auditing parameter constants simply because their names are uppercase.

## Where can keyword matching produce false positives?
Keyword matching will claim a feature is implemented even when it isn't functional. For example:
- A comment saying `# Not using VWAP pullback here` will be matched as having VWAP pullback evidence.
- A variable `vwap_pullback_enabled = False` will trigger a match.
- A function `check_regime()` that just returns `True` will satisfy the regime filter requirement.

## Where can AST extraction miss strategy intent?
- **Nested conditions**: AST doesn't inherently understand that an inner `if` is only reachable if the outer `if` is true. The intent (A AND B) is lost if we only extract that A and B exist somewhere in the file.
- **Early returns/Blockers**: A blocker gate like `if not liquidity_ok(): return` creates a hard requirement for all subsequent code, but raw AST extraction might just see it as an isolated statement, missing its control-flow dominance.
- **Candidate Emission Timing**: If a candidate is emitted *before* a risk check is performed, syntax-level AST won't catch the order of operations, claiming all components exist, miss-ing the fatal flaw.

## Which strategies require semantic/manual review?
All strategies that involve conditional logic flows require semantic review. If a strategy depends on a sequence of events (e.g., Extension -> Pullback -> Confirmation -> Target), keyword extraction is completely insufficient to verify the strategy's true mathematical integrity. Dynamic strategies using `getattr` or `eval` will always require manual review.

## Which reports currently overstate certainty?
- `06_strategy_truth_summary.md` and the `ImplementationVerdict` heavily overstate certainty. A verdict of `IMPLEMENTATION_VERIFIED` currently only proves that the declared vocabulary strings exist somewhere in the script, not that the logic is mathematically sound.
- `04_indicator_inventory.md` claims an indicator is `DECLARED_AND_USED` even if it is only imported or assigned but never actively threshold-checked for an entry/exit decision.

## Which verdicts should be downgraded to `REQUIRES_MANUAL_REVIEW`?
Any strategy that relies on multi-step workflows (like ORB, Mean Reversion, or Trend Following) and currently boasts an `IMPLEMENTATION_VERIFIED` verdict should be downgraded to `REQUIRES_MANUAL_REVIEW` until the Semantic and Mathematical Auditors can reconstruct and verify their execution control-flow graphs.
