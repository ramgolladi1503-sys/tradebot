from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaFamilyMatch:
    schema_family: str
    provider: str
    row_evidence: bool
    filename_evidence: bool
    manifest_evidence: bool
    current_master_enrichment: bool


def classify_schema_family(columns: set[str], logical_path: str) -> SchemaFamilyMatch:
    lower = {col.lower() for col in columns}
    provider = "upstox" if "upstox" in logical_path.lower() else "unknown"
    row_evidence = bool({"timestamp", "ts", "exchange_timestamp", "bid", "ask", "ltp", "open", "high", "low", "close"} & lower)
    filename_evidence = any(token in logical_path.lower() for token in ("nifty", "option", "quote", "depth", "expiry", "strike"))
    manifest_evidence = any(token in logical_path.lower() for token in ("manifest", "ledger", "summary", "proof"))
    current_master_enrichment = "runtime/upstox_instruments/complete.json" in logical_path.lower()
    if {"best_bid", "best_ask", "depth_json"} & lower:
        schema_family = "depth"
    elif {"bid", "ask", "ltp"} & lower:
        schema_family = "quote"
    elif "manifest" in logical_path.lower():
        schema_family = "manifest"
    else:
        schema_family = "unknown"
    return SchemaFamilyMatch(
        schema_family=schema_family,
        provider=provider,
        row_evidence=row_evidence,
        filename_evidence=filename_evidence,
        manifest_evidence=manifest_evidence,
        current_master_enrichment=current_master_enrichment,
    )

