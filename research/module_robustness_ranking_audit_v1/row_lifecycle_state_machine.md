# Row Lifecycle State Machine

Discovered states and buckets include `RAW_CANDIDATE`, `VALIDATED_CANDIDATE`, `BLOCKED_CANDIDATE`, `NO_TRADE`, `EXECUTABLE_CANDIDATE`, `NEAR_EXECUTABLE_CANDIDATE`, `ADVISORY_CANDIDATE`, `SUPPRESSED_CANDIDATE`, and `NO_TRADE_CANDIDATE`.

Canonical audit model mapping:

- observed/generated: strategy/feed/adapters create candidate or market evidence.
- normalized: `candidate_normalizer`.
- eligible/ineligible/rejected: `candidate_classifier`, `hard_downgrade_engine`.
- degraded: downgrade reasons and fallback/feed-risk flags.
- scored: `opportunity_scoring`.
- ranked: `candidate_ranking`.
- selected/displayed: top opportunity projection and dashboard.
- approved/submitted/filled/failed: NOT_VERIFIED by this audit without broker/manual approval replay.

Finding: lifecycle is partially explicit, but displayed fallback rows can exist outside ranked-snapshot identity.
