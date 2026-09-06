"""Read-only runtime adapter for MARKET_STATE_ENGINE_V1.

The adapter consumes authoritative per-index features or the canonical market
snapshot envelope, publishes one current artifact plus an append-only JSONL
ledger, and never performs market-data fetching or execution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.market_state_engine_v1 import MarketStateDecision, classify_cross_index_consensus, classify_market_state

ARTIFACT_NAME = "market_state_engine_v1.json"
LEDGER_NAME = "market_state_engine_v1.jsonl"
INDEX_SYMBOLS = ("NIFTY", "BANKNIFTY", "SENSEX")


def feature_snapshots_from_market_snapshot(market_snapshot: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Map only explicitly present canonical fields; never synthesize authority."""
    snapshot = dict(market_snapshot or {})
    market_open = snapshot.get("market_open")
    symbols = snapshot.get("symbols") if isinstance(snapshot.get("symbols"), Mapping) else {}
    out: dict[str, dict[str, Any]] = {}
    for symbol in INDEX_SYMBOLS:
        row = symbols.get(symbol) if isinstance(symbols, Mapping) else None
        row = dict(row or {}) if isinstance(row, Mapping) else {}
        ohlc = dict(row.get("ohlc") or {}) if isinstance(row.get("ohlc"), Mapping) else {}
        regime = dict(row.get("regime") or {}) if isinstance(row.get("regime"), Mapping) else {}
        cross = dict(row.get("cross_asset") or {}) if isinstance(row.get("cross_asset"), Mapping) else {}
        feed = dict(row.get("feed_health") or {}) if isinstance(row.get("feed_health"), Mapping) else {}
        quote = dict(row.get("quote_truth") or {}) if isinstance(row.get("quote_truth"), Mapping) else {}
        features: dict[str, Any] = {
            "price": row.get("ltp", row.get("spot")),
            "vwap": row.get("vwap", regime.get("vwap")),
            "atr": row.get("atr", regime.get("atr")),
            "quote_age_sec": feed.get("quote_age_sec", feed.get("spot_ltp_age_sec", quote.get("age_sec"))),
            "feed_authority": feed.get("feed_ok", quote.get("authoritative")),
            "session_open": market_open,
            "ema_fast": regime.get("ema_fast"),
            "ema_slow": regime.get("ema_slow"),
            "ema_slope_atr": regime.get("ema_slope_atr"),
            "structure_score": regime.get("structure_score"),
            "momentum_score": regime.get("momentum_score"),
            "breadth": regime.get("breadth", regime.get("equal_breadth")),
            "weighted_breadth": regime.get("weighted_breadth"),
            "breadth_momentum": regime.get("breadth_momentum"),
            "open_location_score": regime.get("open_location_score"),
            "futures_confirmation_score": cross.get("futures_confirmation_score"),
            "orb_high": regime.get("orb_high"),
            "orb_low": regime.get("orb_low"),
            "swing_high": regime.get("swing_high"),
            "swing_low": regime.get("swing_low"),
            "support": regime.get("support", ohlc.get("low")),
            "resistance": regime.get("resistance", ohlc.get("high")),
        }
        out[symbol] = {key: value for key, value in features.items() if value is not None}
    return out


def evaluate_live_market_state(
    snapshots: Mapping[str, Mapping[str, Any]],
    *,
    previous_zones: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    prior = dict(previous_zones or {})
    decisions: dict[str, MarketStateDecision] = {}
    for symbol in INDEX_SYMBOLS:
        decisions[symbol] = classify_market_state(snapshots.get(symbol), symbol=symbol, previous_zone=prior.get(symbol))
    consensus = classify_cross_index_consensus(decisions)
    healthy = all(not decision.blockers for decision in decisions.values())
    return {
        "schema_version": 1,
        "source": "live_market_state_runtime_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS" if healthy else "BLOCKED",
        "regime_healthy": healthy,
        "indices": {symbol: decision.to_payload() for symbol, decision in decisions.items()},
        "cross_index": consensus,
        "read_only": True,
        "execution_capable": False,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
        "broker_order_calls": 0,
    }


def publish_live_market_state(
    output_root: str | Path,
    *,
    snapshots: Mapping[str, Mapping[str, Any]],
    session_id: str,
    source_sha: str,
    previous_zones: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not session_id or len(str(source_sha)) != 40:
        raise ValueError("market_state_runtime_identity_invalid")
    payload = evaluate_live_market_state(snapshots, previous_zones=previous_zones)
    payload["session_id"] = session_id
    payload["source_sha"] = source_sha
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / ARTIFACT_NAME
    temporary = artifact.with_name(artifact.name + ".tmp")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(artifact)
    with (root / LEDGER_NAME).open("a", encoding="utf-8") as handle:
        handle.write(encoded)
    return payload


def publish_from_market_snapshot(
    output_root: str | Path,
    *,
    market_snapshot: Mapping[str, Any] | None,
    session_id: str,
    source_sha: str,
    previous_zones: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return publish_live_market_state(
        output_root,
        snapshots=feature_snapshots_from_market_snapshot(market_snapshot),
        session_id=session_id,
        source_sha=source_sha,
        previous_zones=previous_zones,
    )


def previous_zones_from_payload(payload: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    indices = dict((payload or {}).get("indices") or {})
    for symbol, state in indices.items():
        zone = str(dict(state or {}).get("zone") or "").upper()
        if zone:
            out[str(symbol).upper()] = zone
    return out


__all__ = [
    "evaluate_live_market_state", "feature_snapshots_from_market_snapshot",
    "publish_from_market_snapshot", "publish_live_market_state", "previous_zones_from_payload",
]
