# Phase 5: Extraction Hardening Report

## Enhancements Implemented
The extraction pipeline (`core/intelligence/extractors/hardened_base.py`) has been formalized into a defensive structural model. It explicitly strips parsing responsibility from strategy generation.

1. **Robust Normalization**: The base class actively strips HTML tags and normalizes whitespace (`normalize_html`) before passing the string to source-specific regex/parsing logic.
2. **Deterministic Hashing**: Implemented MD5 `document_hash` derived from the raw binary fetch body. This acts as the primary key for the persistence duplicate detection layer.
3. **Safe Exceptions**: Subclasses (`RBIExtractor`, `SEBIExtractor`, etc.) throw `ExtractionError` instead of crashing. The base wrapper explicitly catches these, returning a `partial_failure` status which skips TradeBot integration but logs to telemetry.
4. **Parser Versioning**: Every parser class statically declares `PARSER_VERSION = "1.0.1"`, allowing offline replay to filter out older buggy extraction parses.
5. **Canonicalization**: Links are properly domain-prefixed via `canonicalize_link`.
6. **No Impact Forcing**: The output payload explicitly hardcodes `market_impact = None` and `affected_indices = None`. Extractors are structurally banned from guessing market impact. That duty belongs strictly to the Replay Calibration Engine.
