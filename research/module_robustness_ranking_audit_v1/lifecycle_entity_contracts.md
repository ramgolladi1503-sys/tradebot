# Lifecycle Entity Contracts

| Entity | Current contract | Identity status | Timestamp status | Persistence |
| --- | --- | --- | --- | --- |
| raw market event | broker/ws payload dict | AMBIGUOUS | broker/exchange/local mixed | runtime/log dependent |
| normalized tick/quote/depth event | tick/quote/depth dict or store row | DERIVABLE_ONLY | local receipt and quote ts vary | tick/runtime stores |
| candle/bar event | candle dict/DataFrame row | DERIVABLE_ONLY | candle cutoff must be proven per aggregator | runtime/data artifacts |
| option-chain snapshot | option-chain dict/list | DERIVABLE_ONLY | quote refresh ts mixed risk | cache/runtime |
| market-state/regime snapshot | regime dataclass/dict | PRESENT_BUT_MUTABLE | processing ts mostly local | evidence/runtime |
| strategy signal | strategy candidate / legacy dict | DERIVABLE_ONLY | generated_epoch/local | candidate reports |
| TradeBuilder result | trade/candidate dict | AMBIGUOUS | processing/local | runtime/review artifacts |
| Phase 1 result | gate dict/reason fields | AMBIGUOUS | processing/local | logs/evidence |
| Phase 2 result | candidate dict with phase2 fields | DERIVABLE_ONLY | processing/local | runtime/evidence |
| candidate | StrategyCandidate or candidate dict | PRESENT_BUT_MUTABLE | generated_epoch/local | candidate pool/ranked reports |
| ranked candidate/snapshot | CandidateRankRecord/CandidateRankingReport | PRESENT_BUT_PARTIAL | generated_epoch/local | ranked snapshots/jsonl |
| displayed opportunity | dashboard DataFrame row | AMBIGUOUS | snapshot/cache dependent | UI/session/runtime |
| approval decision | approval_store/review_queue record | DERIVABLE_ONLY | approval epoch/local | approved_trades/review queue |
| order intent | core/orders/order_intent.py payload | PRESENT_BUT_NOT_E2E_PROVEN | submission/local | order intent store/logs |
| broker request/update/fill/reconciliation | broker/reconciler dicts | NOT_PROVEN | broker/local mixed | broker truth/reconciliation artifacts |
