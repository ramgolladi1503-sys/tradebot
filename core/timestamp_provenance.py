from __future__ import annotations
import math

AUTHORITIES = {"EXCHANGE_TIMESTAMP", "GOVERNED_RECEIVE_TIMESTAMP", "LOCAL_FALLBACK_TIMESTAMP", "UNKNOWN"}

def verify_tick_timestamp_provenance(record: dict) -> tuple[bool, str]:
    try:
        if not math.isfinite(float(record["last_price"])): return False, "invalid_price"
        selected, receive = float(record["timestamp_epoch"]), float(record["receive_timestamp_epoch"])
    except (KeyError, TypeError, ValueError): return False, "missing_timestamp"
    if not math.isfinite(selected) or not math.isfinite(receive): return False, "non_finite_timestamp"
    authority, fallback = record.get("timestamp_authority"), record.get("timestamp_fallback_used")
    source, source_epoch = record.get("timestamp_source_field"), record.get("source_timestamp_epoch")
    if authority not in AUTHORITIES: return False, "unknown_authority"
    if authority == "EXCHANGE_TIMESTAMP":
        if not source or source_epoch is None or bool(fallback) or abs(float(source_epoch) - selected) > 1e-9: return False, "exchange_metadata_inconsistent"
    elif authority == "GOVERNED_RECEIVE_TIMESTAMP":
        if source is not None or source_epoch is not None or not bool(fallback) or abs(receive - selected) > 1e-9: return False, "receive_metadata_inconsistent"
    return True, "ok"
