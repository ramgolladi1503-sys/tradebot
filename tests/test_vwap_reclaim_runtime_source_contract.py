from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.candidate_pool_orchestrator import get_default_candidate_generators
from core.movement_regime import MovementRegimeResult
from core.orchestrator import _snapshot_symbol_payload
from core.ranking_orchestrator import build_ranked_opportunity_report
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates
from tests.vwap_reclaim_test_support import vwap_reclaim_context

import core.market_data as market_data


IST = ZoneInfo("Asia/Kolkata")
SYMBOL = "NIFTY"


class _DummyNews:
    def get_shock(self):
        return {}

    def encode(self):
        return {}


class _DummyCross:
    def update(self, *_args, **_kwargs):
        return {"features": {}, "data_quality": {}}


class _DummyRegimeModel:
    def predict(self, _features):
        return {
            "primary_regime": "TREND",
            "regime_probs": {"TREND": 0.8, "RANGE": 0.2},
            "regime_entropy": 0.2,
            "unstable_regime_flag": False,
        }


def _regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.6,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.1,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.0,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )


def _causal_vwap(history: list[dict[str, object]]) -> float:
    running_tp_weight = 0.0
    running_volume = 0.0
    for bar in history:
        volume = bar.get("volume")
        if volume in (None, "", "None"):
            weight = 1.0
        else:
            weight = float(volume)
            if weight <= 0:
                weight = 1.0
        typical_price = (float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3.0
        running_tp_weight += typical_price * weight
        running_volume += weight
    return running_tp_weight / running_volume


def _bar(offset_minutes: int, open_: float, high: float, low: float, close: float, *, volume: float = 1000.0) -> dict[str, object]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST) + timedelta(minutes=offset_minutes)
    end = start + timedelta(minutes=1)
    return {
        "symbol": SYMBOL,
        "session_date": "2026-07-14",
        "timeframe": "1m",
        "bar_start_timestamp": start.isoformat(),
        "bar_end_timestamp": end.isoformat(),
        "ts": start,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source": "unit_test",
        "source_timestamp": end.isoformat(),
        "receipt_timestamp": (end + timedelta(seconds=1)).isoformat(),
        "is_complete": True,
    }


def _completed_history() -> list[dict[str, object]]:
    history = [_bar(i, 22539.0, 22541.0, 22539.0, 22540.0) for i in range(32)]
    history.extend(
        [
            _bar(32, 22510.0, 22550.0, 22470.0, 22480.0),
            _bar(33, 22535.0, 22560.0, 22510.0, 22550.0),
            _bar(34, 22575.0, 22590.0, 22570.0, 22580.0),
        ]
    )
    return history


def _option_chain() -> list[dict[str, object]]:
    return [
        {
            "strike": 22600.0,
            "type": "CE",
            "ltp": 120.0,
            "spread_pct": 0.8,
            "bid_qty": 600.0,
            "ask_qty": 600.0,
            "ltp_change": 10.0,
        },
        {
            "strike": 22600.0,
            "type": "PE",
            "ltp": 90.0,
            "spread_pct": 0.8,
            "bid_qty": 600.0,
            "ask_qty": 600.0,
            "ltp_change": 0.0,
        },
    ]


def _market_data_setup(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, object], float, float]:
    fixed_now = datetime(2026, 7, 14, 9, 50, tzinfo=IST)
    history = _completed_history()
    expected_vwap = _causal_vwap(history)
    final_close = float(history[-1]["close"])

    original_bars = deepcopy(market_data.ohlc_buffer._bars)
    market_data.ohlc_buffer._bars.clear()
    try:
        seed_result = market_data.ohlc_buffer.seed_bars(SYMBOL, history)
        assert seed_result["accepted"] is True
        assert seed_result["seeded_bars"] == len(history)

        monkeypatch.setattr(market_data.cfg, "SYMBOLS", [SYMBOL], raising=False)
        monkeypatch.setattr(market_data.cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
        monkeypatch.setattr(market_data.cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
        monkeypatch.setattr(market_data.cfg, "OHLC_MIN_BARS", 30, raising=False)
        monkeypatch.setattr(market_data.cfg, "EXECUTION_MODE", "PAPER", raising=False)
        monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
        monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
        monkeypatch.setattr(market_data, "_DATA_CACHE", {}, raising=False)
        monkeypatch.setattr(market_data, "_LTP_HISTORY", {}, raising=False)
        monkeypatch.setattr(market_data, "_DAYTYPE_LOCK", {}, raising=False)
        monkeypatch.setattr(market_data, "_DAYTYPE_LAST", {}, raising=False)
        monkeypatch.setattr(market_data, "_DAYTYPE_LAST_DAY", {}, raising=False)
        monkeypatch.setattr(market_data, "_DAYTYPE_LAST_LOG", {}, raising=False)
        monkeypatch.setattr(market_data, "_DAYTYPE_CONF_HISTORY", {}, raising=False)
        monkeypatch.setattr(market_data, "_REGIME_LAST_PRIMARY", {}, raising=False)
        monkeypatch.setattr(market_data, "_REGIME_TRANSITIONS", {}, raising=False)
        monkeypatch.setattr(market_data, "_INDICATOR_LAST_UPDATE_EPOCH", {}, raising=False)
        monkeypatch.setattr(market_data, "_NEWS_CAL", _DummyNews(), raising=False)
        monkeypatch.setattr(market_data, "_NEWS_TEXT", _DummyNews(), raising=False)
        monkeypatch.setattr(market_data, "_NEWS_ENCODER", _DummyNews(), raising=False)
        monkeypatch.setattr(market_data, "_CROSS_ASSET", _DummyCross(), raising=False)
        monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)

        def _fake_get_ltp(symbol: str) -> float:
            market_data._DATA_CACHE.setdefault(symbol, {})
            market_data._DATA_CACHE[symbol].update(
                {
                    "ltp_source": "live",
                    "ltp_ts_epoch": fixed_now.timestamp(),
                    "last_ltp": 22610.0,
                }
            )
            return 22610.0

        monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)
        monkeypatch.setattr(market_data, "get_index_quote_snapshot", lambda *_args, **_kwargs: {})
        monkeypatch.setattr(market_data, "_refresh_index_quote_from_rest", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            market_data,
            "resolve_index_quote",
            lambda **kwargs: {
                "quote_ok": True,
                "quote_source": "depth",
                "bid": float(kwargs.get("ltp") or 0.0) - 1.0,
                "ask": float(kwargs.get("ltp") or 0.0) + 1.0,
                "mid": float(kwargs.get("ltp") or 0.0),
                "last_price": float(kwargs.get("ltp") or 0.0),
            },
        )
        monkeypatch.setattr(market_data, "fetch_option_chain", lambda *args, **kwargs: _option_chain())
        monkeypatch.setattr(market_data, "_hydrate_live_option_chain_liquidity", lambda symbol, option_chain, **kwargs: list(option_chain))
        monkeypatch.setattr(market_data, "_option_chain_health", lambda *args, **kwargs: {"status": "OK", "quote_age_sec": 0.4})

        rows = market_data.fetch_live_market_data(allow_history_seed=False)
        row = next(item for item in rows if item.get("symbol") == SYMBOL)
        return row, expected_vwap, final_close
    finally:
        market_data.ohlc_buffer._bars = original_bars


def test_upstream_producer_emits_canonical_vwap_and_preserves_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    row, expected_vwap, final_close = _market_data_setup(monkeypatch)

    assert row["vwap"] == pytest.approx(expected_vwap)
    assert row["vwap"] != pytest.approx(final_close)
    assert row["completed_bar_history"][-1]["close"] == pytest.approx(final_close)
    assert row["completed_bar_history_provenance"]["status"] == "TRUTHFUL"
    assert row["completed_bar_history_provenance"]["source_component"] == "core.market_data.fetch_live_market_data"


def test_runtime_context_builder_consumes_canonical_vwap_and_blocks_close_fallback(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    row, expected_vwap, final_close = _market_data_setup(monkeypatch)
    warnings: list[str] = []
    symbol_payload = _snapshot_symbol_payload(row, warnings)

    ctx = _strategy_context_from_market_symbol(SYMBOL, symbol_payload)
    assert ctx.vwap == pytest.approx(expected_vwap)
    assert ctx.vwap != pytest.approx(final_close)
    assert symbol_payload["metadata"]["strategy_context_truth"]["vwap"] == pytest.approx(expected_vwap)
    assert symbol_payload["metadata"]["strategy_context_provenance"]["vwap"]["source_component"] == "core.market_data.fetch_live_market_data"

    missing_payload = deepcopy(symbol_payload)
    missing_payload["ohlc"]["close"] = final_close
    missing_payload["metadata"]["strategy_context_truth"].pop("vwap", None)
    missing_payload["metadata"]["strategy_context_provenance"].pop("vwap", None)
    missing_ctx = _strategy_context_from_market_symbol(SYMBOL, missing_payload)
    assert missing_ctx.vwap is None

    caplog.set_level("WARNING")
    candidates = generate_vwap_reclaim_rejection_candidates(missing_ctx, _regime())
    assert candidates == ()
    assert any(
        "event=STRATEGY_EVIDENCE_BLOCKED" in record.message
        and "runtime_strategy_id=vwap_reclaim_rejection_v1" in record.message
        and "missing_fields=vwap" in record.message
        for record in caplog.records
    )


def test_default_ranked_pipeline_uses_produced_truth_for_vwap_reclaim(monkeypatch: pytest.MonkeyPatch) -> None:
    row, expected_vwap, _ = _market_data_setup(monkeypatch)
    symbol_payload = _snapshot_symbol_payload(row, [])
    ctx = _strategy_context_from_market_symbol(SYMBOL, symbol_payload)
    regime = _regime()

    report = build_ranked_opportunity_report(
        ctx,
        regime,
        candidate_generators=get_default_candidate_generators(),
    )

    default_generators = tuple(get_default_candidate_generators())
    assert report.candidate_pool.generator_count == len(default_generators)
    assert report.candidate_pool.failed_generator_count == 0
    assert report.candidate_pool.candidate_count >= 1

    candidate = next((cand for cand in report.candidate_pool.candidates if cand.strategy_id == "vwap_reclaim_rejection_v1"), None)
    assert candidate is not None
    direct_candidate = generate_vwap_reclaim_rejection_candidates(
        vwap_reclaim_context(
            history=ctx.completed_bar_history,
            vwap=ctx.vwap,
            ts_epoch=ctx.ts_epoch,
            spot_ltp=ctx.spot_ltp,
            vwap_slope=ctx.vwap_slope,
            volume_z=ctx.volume_z,
            previous_spot_ltp=(ctx.metadata or {}).get("previous_spot_ltp"),
        ),
        regime,
    )[0]
    assert round(float(candidate.raw_score), 6) == round(float(direct_candidate.raw_score), 6)
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "VALIDATED_CANDIDATE"
    assert candidate.entry_trigger == "confirmed_vwap_reclaim_or_rejection"
    assert candidate.invalid_if == "price_crosses_back_through_vwap"
    assert candidate.evidence["temporal_evidence"]["vwap_provenance"] == "VWAP_AUTHORITATIVE"
    assert ctx.vwap == pytest.approx(expected_vwap)
