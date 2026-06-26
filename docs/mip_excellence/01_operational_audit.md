# Phase 15: Operational Audit Report

## Latency Measurements
- **Startup Latency**: 3.71 ms
- **Fetch Latency (example.com)**: 263.59 ms
- **Parser Latency (HTML Normalization & Extractor)**: 4.70 ms
- **Storage Latency (SQLite Insert)**: 3.42 ms
- **Circuit Breaker Trip Latency (5 network failures)**: 23.01 ms

## Resource Measurements
- **Peak Memory Usage (During Fetch)**: 0.2432 MB

## Resilience Measurements
- **Circuit Breaker Tripped After**: 6 failures
- **Extraction Status**: success
