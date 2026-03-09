from __future__ import annotations

from types import SimpleNamespace

from core.survival_gates import SurvivalGates


def _trade(**overrides):
    payload = {
        "trade_id": "T-1",
        "symbol": "NIFTY",
        "qty": 2,
        "strategy": "TREND_VWAP",
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_survival_gates_blocks_on_loss_streak_and_emits_flatten_intent():
    emitted: list[tuple[str, dict]] = []
    incidents: list[tuple[str, str, dict]] = []

    def _emit(event_type: str, payload: dict):
        emitted.append((str(event_type), dict(payload)))

    def _incident(sev: str, code: str, context: dict):
        incidents.append((str(sev), str(code), dict(context)))
        return "inc-test-1"

    gates = SurvivalGates(
        max_daily_drawdown=-0.05,
        max_consecutive_losses=3,
        auto_flatten_on_breach=True,
        halt_entries_on_breach=True,
        breach_cooldown_sec=120.0,
        event_writer=_emit,
        incident_writer=_incident,
    )
    decision = gates.evaluate(
        trade=_trade(),
        portfolio={"loss_streak": 3, "daily_max_drawdown": -0.01},
        market_data={"ltp": 100.0, "atr": 1.0},
        now_ts=1_700_000_000.0,
    )

    assert decision.breach is True
    assert decision.allowed_entries is False
    assert "MAX_CONSECUTIVE_LOSSES_BREACH" in decision.reason_codes
    assert decision.auto_flatten_requested is True
    assert decision.incident_id == "inc-test-1"

    event_types = [row[0] for row in emitted]
    assert "survival_gate_breach" in event_types
    assert "flatten_requested" in event_types
    assert incidents and incidents[0][1] == "SURVIVAL_GATE_BREACH"


def test_survival_gates_applies_volatility_size_multiplier_without_breach():
    gates = SurvivalGates(
        max_daily_drawdown=-0.10,
        max_consecutive_losses=5,
        volatility_sizing_multiplier=0.4,
        volatility_trigger_pct=0.01,
        auto_flatten_on_breach=False,
        halt_entries_on_breach=True,
        event_writer=lambda *_a, **_k: None,
        incident_writer=lambda *_a, **_k: "ignored",
    )
    decision = gates.evaluate(
        trade=_trade(),
        portfolio={"loss_streak": 0, "daily_max_drawdown": -0.001},
        market_data={"ltp": 100.0, "atr": 2.0},
        now_ts=1_700_000_010.0,
    )
    assert decision.breach is False
    assert decision.allowed_entries is True
    assert decision.size_multiplier == 0.4
    assert decision.auto_flatten_requested is False
