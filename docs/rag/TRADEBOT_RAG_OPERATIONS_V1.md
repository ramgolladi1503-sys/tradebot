# TradeBot Evidence RAG — Index Operations Hardening V1.1

## Objective

Harden the existing local evidence RAG against concurrent index builds and silent SQLite/FTS inconsistency without changing retrieval, ranking, answer synthesis, source scope, or trading behavior.

## Included

- Atomic build lock adjacent to the SQLite index.
- Fail-closed behavior when another supported build owns a fresh lock.
- Stale-lock recovery after a configurable threshold.
- Protection against reclaiming an old lock owned by a live process on the same machine.
- Unique lock ownership tokens so cleanup cannot delete a replacement lock.
- Safe cleanup when lock creation succeeds but lock metadata cannot be written.
- Read-only `status` inspection that cannot create schema or rebuild FTS rows.
- `doctor` CLI command using a read-only SQLite connection.
- Integrity checks for:
  - SQLite `quick_check`.
  - required schema tables.
  - schema version.
  - non-empty document and chunk inventory.
  - global and per-document chunk counts.
  - orphan chunks.
  - metadata chunk count.
  - FTS table presence and row correspondence when FTS is enabled.
  - foreign-key violations.
  - active build lock presence.
- Streamlit build action routed through the safe builder.
- Streamlit inventory/status display routed through the read-only status path.
- Streamlit integrity scan available only on demand.
- CI evidence artifact for the doctor report.

## Excluded

- Embeddings, vector databases, rerankers, agents, or generative answers.
- Retrieval-scoring changes.
- New source formats or source directories.
- Automatic database repair by the doctor or status commands.
- Broker, strategy, risk, execution, approval, or live runtime changes.
- Background schedulers or remote services.

## Operational Contract

1. Supported CLI and Streamlit builds must acquire the atomic lock before invoking the existing index builder.
2. A competing build must fail with `rag_build_in_progress`; it must not wait indefinitely or modify the index.
3. A stale lock may be reclaimed only when no live same-host owner is detected.
4. Lock cleanup must remove only the lock carrying the current build token.
5. `status` and `doctor` must never create or repair an index.
6. `doctor` exits successfully only when every configured invariant passes.
7. Existing retrieval evaluation thresholds and refusal behavior remain unchanged.

## Acceptance Commands

```bash
PYTHONPATH=. pytest -q -o addopts='' tests/test_tradebot_rag.py tests/test_tradebot_rag_operations.py
PYTHONPATH=. python scripts/tradebot_rag.py build
PYTHONPATH=. python scripts/tradebot_rag.py doctor
PYTHONPATH=. python scripts/tradebot_rag.py status
PYTHONPATH=. python scripts/tradebot_rag.py evaluate --min-hit-at-k 0.80 --min-refusal-accuracy 1.00
```

## Failure Recovery

- `rag_build_in_progress`: inspect the reported lock owner and start time. Do not delete a fresh or live-owner lock.
- Clearly stale lock with no live same-host owner: the next supported build reclaims it automatically.
- Doctor failure: retain the database for investigation, rebuild through the supported build command, then rerun `doctor`. The doctor itself performs no mutation.

## Production Boundary

This hardening makes local index operations observable and fail-closed. It does not make the RAG a network service, multi-user system, or semantic LLM application.
