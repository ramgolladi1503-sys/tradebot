# Agent 3 Report: Market Intelligence Architecture

## Overview
The Market Intelligence Platform (MIP) acts as an independent, side-channel ingestion system. It processes raw external data from public markets and context domains (e.g., RBI, SEBI, NSE) and funnels it down to purely advisory context objects. At no point in this architecture does the flow intersect directly with trading execution pipelines or manipulate the risk/ranking metrics unless formally replay-calibrated.

## Data Flow & Components

### 1. Source Registry
A typed configuration registry mapping out all allowed public intelligence sources, their required parse types, schedule limits, and extraction schemas.

### 2. Scheduler
A lightweight cron/event-driven trigger layer ensuring fetches respect target-defined delays, rate limits, and allowed hours.

### 3. Fetch Layer (Robots Guarded)
The core ingestion unit. Fetches raw HTML/JSON over standard HTTP or specialized clients (e.g., Crawl4AI, Firecrawl, Scrapy).
*Must include a strict robots.txt adherence module and graceful degradation on failures.*

### 4. Browser Layer
Handles JS-heavy sites via tools like Browser Use / Playwright, specifically designated in the Source Registry. Fails closed if tools are missing.

### 5. Parser Layer
Converts raw web output (HTML, PDFs, DOCs) into standardized clean text/markdown. Includes schema translation if structured JSON is provided by the fetcher (like Firecrawl).

### 6. Schema Validator
Validates that the parsed structure strictly matches the expected `EventSchema` for the targeted source. Drops data if the schema breaks (fail closed).

### 7. Entity Resolver
Identifies key financial entities (e.g., `BANKNIFTY`, `HDFC`, `SEBI`) within the validated text and normalizes them against TradeBot's internal instrument symbol registry.

### 8. Knowledge Extractor
Extracts named events, impact assertions, timestamps, and explicit mentions mapping them into evidence blocks. Must capture confidence values with raw excerpt pointers, explicitly setting default impact metrics to UNCALIBRATED.

### 9. Market Context Engine
Consolidates extracted knowledge into a cohesive temporal state, defining current market condition parameters (e.g., "RBI Rate Decision Day").

### 10. Calibration Engine
Examines extracted factors and runs them against historical replays. It defines the factor schema mapping uncalibrated values to `CALIBRATED` explicitly only when sufficient evidence exists.

### 11. Replay Validator
Runs offline validation measuring intelligence relevance against forward volatility, slippage impact, and expectancy changes. This provides the statistical evidence necessary for the Calibration Engine.

### 12. Evidence Store
An append-only historical log saving raw HTML/Markdown, parser version, extracted JSON, content hashes, and timestamp signatures to ensure fully reproducible audits.

### 13. Optional Knowledge Graph
A non-hallucinating graph connecting explicit entities via config or evidence-backed edges (e.g., `RBI -> Banking Sector -> BANKNIFTY`).

### 14. Optional Embedding Store
Vector store for semantic clustering and retrieval of historical advisory contexts (for use strictly in Replay validation or offline analysis).

### 15. TradeBot Advisory Context
The final adapter. Appends the validated, calibrated (or strictly labeled uncalibrated) payload to `candidate.advisory_context` during Phase-2 or candidate evaluation. It operates as purely passive metadata. No execution integration exists.
