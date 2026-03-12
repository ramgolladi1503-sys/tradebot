"""Migration note:
Deterministic PAPER replay harness for fixture-driven candidate generation tests.
"""

from __future__ import annotations
from core.paths import logs_dir

import argparse
from contextlib import contextmanager
import json
import random
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder
from core.fixture_validator import ensure_tradingsymbols, validate_fixture_payload
from core.reject_logger import append_reject_reasons
from core.time_utils import now_utc_epoch


class _ReplayPredictor:
    model_version = "replay"
    shadow_version = None

    def predict_confidence(self, _features):
        return 0.95


def _load_fixture(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture must be a JSON object")
    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list):
        raise ValueError("fixture missing snapshots list")
    return payload


def _patch_builder_for_replay(builder: TradeBuilder, rng: random.Random) -> None:
    builder._apply_lifecycle_gate = lambda strategy_name, mode="MAIN": (True, "ok")  # type: ignore[method-assign]
    builder._apply_decay_gate = lambda strategy_name, base_score=None, size_mult=1.0: (True, base_score, size_mult, None)  # type: ignore[method-assign]
    builder._validate_ml_features = lambda feats: (True, "ok")  # type: ignore[method-assign]
    builder._signal_for_symbol = lambda md, force_family=None: md.get("replay_signal")  # type: ignore[method-assign]


@contextmanager
def _temporary_cfg_overrides(overrides: dict[str, object]):
    original = {
        key: getattr(cfg, key, None) for key in overrides
    }
    try:
        for key, value in overrides.items():
            setattr(cfg, key, value)
        yield
    finally:
        for key, value in original.items():
            setattr(cfg, key, value)


@contextmanager
def _patched_replay_scoring(rng: random.Random):
    original = trade_builder_module.compute_trade_score
    trade_builder_module.compute_trade_score = lambda *args, **kwargs: {  # type: ignore[assignment]
        "score": 90.0 + round(rng.random() * 5.0, 2),
        "alignment": 1.0,
    }
    try:
        yield
    finally:
        trade_builder_module.compute_trade_score = original  # type: ignore[assignment]


def _normalize_snapshot(snapshot: dict, *, fixture_name: str, idx: int, now_epoch: float) -> dict:
    symbol = str(snapshot.get("symbol") or "NIFTY").upper()
    market_open = bool(snapshot.get("market_open", False))
    replay_signal_raw = snapshot.get("replay_signal")
    replay_signal = replay_signal_raw if isinstance(replay_signal_raw, dict) else None
    signal_direction = str((replay_signal or {}).get("direction") or "").upper()
    default_orb_bias = "NEUTRAL"
    if signal_direction == "BUY_CALL":
        default_orb_bias = "UP"
    elif signal_direction == "BUY_PUT":
        default_orb_bias = "DOWN"
    else:
        bias = str(snapshot.get("bias") or "").upper()
        if bias in {"BULLISH", "UP"}:
            default_orb_bias = "UP"
        elif bias in {"BEARISH", "DOWN"}:
            default_orb_bias = "DOWN"
    out = {
        "symbol": symbol,
        "segment": snapshot.get("segment", "NSE_FNO"),
        "market_open": market_open,
        "valid": bool(snapshot.get("valid", True)),
        "ltp": float(snapshot.get("ltp", 0.0) or 0.0),
        "vwap": float(snapshot.get("vwap", snapshot.get("ltp", 0.0)) or 0.0),
        "bias": snapshot.get("bias", "NEUTRAL"),
        "instrument": "OPT",
        "chain_source": snapshot.get("chain_source", "synthetic_offhours"),
        "quote_ok": snapshot.get("quote_ok", True),
        "bid": snapshot.get("bid"),
        "ask": snapshot.get("ask"),
        "ltp_source": snapshot.get("ltp_source", "live"),
        "ltp_ts_epoch": snapshot.get("ltp_ts_epoch", now_epoch),
        "timestamp": snapshot.get("timestamp", now_epoch + idx),
        "regime": snapshot.get("regime", "NEUTRAL"),
        "regime_day": snapshot.get("regime_day", snapshot.get("regime", "NEUTRAL")),
        "day_type": snapshot.get("day_type", "UNKNOWN"),
        "option_chain": list(snapshot.get("option_chain", []) or []),
        "replay_signal": replay_signal,
        "orb_bias": snapshot.get("orb_bias", default_orb_bias),
        "htf_dir": snapshot.get("htf_dir", "FLAT"),
        "market_context": {
            "execution_mode": "PAPER",
            "market_open": market_open,
            "segment": snapshot.get("segment", "NSE_FNO"),
        },
        "fixture_name": fixture_name,
    }
    return out


def _canonical_no_trade_reason(reason: str) -> str:
    text = str(reason or "").strip().lower()
    if text == "no_signal" or text.startswith("no_signal_"):
        return "no_signal"
    return text or "unknown"


def run_replay(fixture_path: Path, *, seed: int = 7) -> dict:
    fixture = _load_fixture(fixture_path)
    fixture_name = str(fixture.get("name") or fixture_path.stem)
    auto_symbols = bool(getattr(cfg, "REPLAY_FIXTURE_AUTO_SYMBOLS", True))
    if auto_symbols:
        ensure_tradingsymbols(fixture, fixture_name=fixture_name)
    else:
        errors = validate_fixture_payload(fixture)
        if errors:
            raise RuntimeError(f"Fixture missing tradingsymbols: {errors[:3]}")
    snapshots = list(fixture.get("snapshots") or [])
    expected_min_candidates = int(fixture.get("expected_min_candidates", 0))
    require_builder_path = bool(fixture.get("require_builder_path", False))

    rng = random.Random(seed)
    candidates = []
    rejects = []
    fallback_candidate_count = 0
    overrides = {
        "EXECUTION_MODE": "PAPER",
        "PAPER_STRICT_MODE": False,
        "PAPER_STRICT_QUOTES": False,
        "ALLOW_SYNTHETIC_CHAIN": True,
        "REQUIRE_LIVE_OPTION_QUOTES": False,
        "REQUIRE_LIVE_QUOTES": True,
    }
    with _temporary_cfg_overrides(overrides), _patched_replay_scoring(rng):
        builder = TradeBuilder(predictor=_ReplayPredictor())
        _patch_builder_for_replay(builder, rng=rng)
        now_epoch = now_utc_epoch()
        for idx, raw in enumerate(snapshots):
            md = _normalize_snapshot(raw if isinstance(raw, dict) else {}, fixture_name=fixture_name, idx=idx, now_epoch=now_epoch)
            trade = builder.build(md, quick_mode=False, debug_reasons=False, allow_fallbacks=False, allow_baseline=False)
            if trade is None:
                replay_signal = md.get("replay_signal")
                if isinstance(replay_signal, dict):
                    direction = str(replay_signal.get("direction") or "")
                    opt_type = "CE" if direction == "BUY_CALL" else ("PE" if direction == "BUY_PUT" else None)
                    chain = list(md.get("option_chain", []) or [])
                    selected_opt = None
                    if opt_type is not None:
                        selected_opt = next((opt for opt in chain if str(opt.get("type")).upper() == opt_type), None)
                    if selected_opt is None and chain:
                        selected_opt = chain[0]
                    if isinstance(selected_opt, dict):
                        intent = builder.trade_intent_flags(md, opt=selected_opt)
                        candidates.append(
                            {
                                "snapshot_index": idx,
                                "candidate_key": f"{md.get('symbol')}:{idx}:REPLAY_SYNTH",
                                "symbol": md.get("symbol"),
                                "strategy": "REPLAY_SYNTH",
                                "trade_score": float(replay_signal.get("score", 0.0) or 0.0) * 100.0,
                                "confidence": float(replay_signal.get("score", 0.0) or 0.0),
                                "planning_only": bool(intent["planning_only"]),
                                "execution_allowed": bool(intent["execution_allowed"]),
                                "reason": intent["execution_reason"],
                                "tradable": bool(intent["tradable"]),
                                "tradable_reasons_blocking": list(intent["tradable_reasons_blocking"]),
                                "source": "fixture_fallback",
                            }
                        )
                        fallback_candidate_count += 1
                        continue
                reject_ctx = dict(getattr(builder, "_reject_ctx", {}) or {})
                reason = str(reject_ctx.get("reason") or "no_trade_generated")
                append_reject_reasons(
                    symbol=md.get("symbol"),
                    strategy="REPLAY_SYNTH",
                    reasons=[reason],
                    mode="PAPER",
                    source="paper_replay",
                    extra={
                        "fixture": fixture_name,
                        "snapshot_index": idx,
                    },
                )
                rejects.append(
                    {
                        "snapshot_index": idx,
                        "symbol": md.get("symbol"),
                        "reason": reason,
                    }
                )
                continue
            candidates.append(
                {
                    "snapshot_index": idx,
                    "candidate_key": f"{trade.symbol}:{idx}:{trade.strategy}",
                    "symbol": trade.symbol,
                    "strategy": trade.strategy,
                    "trade_score": float(trade.trade_score or 0.0),
                    "confidence": float(trade.confidence or 0.0),
                    "planning_only": bool(getattr(trade, "planning_only", False)),
                    "execution_allowed": bool(getattr(trade, "execution_allowed", False)),
                    "reason": getattr(trade, "reason", None),
                    "tradable": bool(getattr(trade, "tradable", True)),
                    "tradable_reasons_blocking": list(getattr(trade, "tradable_reasons_blocking", []) or []),
                    "source": "trade_builder",
                }
            )

    top_reasons: dict[str, int] = {}
    for row in rejects:
        reason = _canonical_no_trade_reason(str(row.get("reason") or "unknown"))
        top_reasons[reason] = int(top_reasons.get(reason, 0)) + 1

    payload = {
        "fixture": str(fixture_path),
        "fixture_name": fixture_name,
        "seed": int(seed),
        "candidate_count": len(candidates),
        "fallback_candidate_count": int(fallback_candidate_count),
        "candidates": candidates,
        "rejects": rejects,
        "no_trade": len(candidates) == 0,
        "top_reject_reasons": top_reasons,
    }
    out = logs_dir() / f"paper_replay_{fixture_name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    if len(candidates) < expected_min_candidates:
        raise RuntimeError(
            f"Replay below expected candidates for {fixture_name}: "
            f"got={len(candidates)} expected_min={expected_min_candidates}"
        )
    if require_builder_path and fallback_candidate_count > 0:
        raise RuntimeError(
            f"Replay fallback used for {fixture_name} despite require_builder_path=true: "
            f"fallback_count={fallback_candidate_count}"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic PAPER replay from fixture.")
    parser.add_argument("--fixture", required=True, help="Path to fixture JSON")
    parser.add_argument("--seed", type=int, default=7, help="Deterministic replay seed")
    args = parser.parse_args()

    payload = run_replay(Path(args.fixture), seed=int(args.seed))
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
