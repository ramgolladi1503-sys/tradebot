"""Current-session Kite instrument authority for the read-only observer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


REQUIRED_SYMBOLS = ("NIFTY", "BANKNIFTY")


def fetch_current_instruments(client: Any, *, exchanges: Iterable[str] = ("NSE", "NFO", "BFO")) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for exchange in exchanges:
        fetched = client.instruments(exchange)
        if not isinstance(fetched, list) or not fetched:
            raise RuntimeError(f"CURRENT_INSTRUMENT_FETCH_EMPTY:{exchange}")
        rows.extend(dict(row) for row in fetched if isinstance(row, Mapping))
    if not rows:
        raise RuntimeError("CURRENT_INSTRUMENT_AUTHORITY_EMPTY")
    return rows


def _canonical_rows(rows: list[dict[str, Any]]) -> bytes:
    return (json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str) + "\n").encode("utf-8")


def build_instrument_authority(
    *, rows: list[dict[str, Any]], session_date: str, source_sha: str, output_root: str | Path,
    capture_timestamp: str | None = None,
) -> dict[str, Any]:
    if not session_date or not source_sha or not rows:
        raise ValueError("current_instrument_authority_identity_missing")
    captured = capture_timestamp or datetime.now(timezone.utc).isoformat()
    raw_bytes = _canonical_rows(rows)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    raw_path = root / "instruments.raw.json"
    manifest_path = root / "instrument_authority_manifest.json"
    if raw_path.exists() or manifest_path.exists():
        raise FileExistsError("current_instrument_authority_already_exists")
    raw_path.write_bytes(raw_bytes)
    raw_sha = hashlib.sha256(raw_bytes).hexdigest()
    segments = sorted({str(row.get("exchange") or row.get("segment") or "").strip() for row in rows if row.get("exchange") or row.get("segment")})
    symbols = {str(row.get("name") or row.get("tradingsymbol") or "").upper() for row in rows}
    required = {symbol: symbol in symbols for symbol in REQUIRED_SYMBOLS}
    bfo = any(segment == "BFO" or segment.startswith("BFO-") for segment in segments)
    manifest = {
        "schema_version": 1, "session_date": session_date, "capture_timestamp": captured,
        "source_sha": source_sha, "raw_instrument_path": str(raw_path),
        "raw_instrument_sha256": raw_sha, "row_count": len(rows), "segments": segments,
        "nifty_authority": required["NIFTY"], "banknifty_authority": required["BANKNIFTY"],
        "sensex_bfo_authority": bfo,
        "broker_write_authority": False, "order_authority": False,
        "paper_authorized": False, "live_authorized": False, "verdict": "PASS",
    }
    if not all(required.values()):
        manifest["verdict"] = "BLOCKED_REQUIRED_UNDERLYING_MISSING"
        manifest["nifty_authority"] = required["NIFTY"]
        manifest["banknifty_authority"] = required["BANKNIFTY"]
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError("CURRENT_INSTRUMENT_REQUIRED_UNDERLYING_MISSING")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest
