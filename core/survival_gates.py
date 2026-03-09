from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from config import config as cfg
from core.events import append_event
from core.incidents import SEV1, SEV2, create_incident
from core.time_utils import now_utc_epoch


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


@dataclass(frozen=True)
class SurvivalGateDecision:
    allowed_entries: bool
    breach: bool
    reason_codes: list[str]
    size_multiplier: float
    auto_flatten_requested: bool
    incident_id: str | None
    context: dict[str, Any] = field(default_factory=dict)


class SurvivalGates:
    def __init__(
        self,
        *,
        max_daily_drawdown: float | None = None,
        max_consecutive_losses: int | None = None,
        volatility_sizing_multiplier: float | None = None,
        volatility_trigger_pct: float | None = None,
        auto_flatten_on_breach: bool | None = None,
        halt_entries_on_breach: bool | None = None,
        breach_cooldown_sec: float | None = None,
        event_writer: Callable[[str, dict[str, Any]], Any] | None = None,
        incident_writer: Callable[[str, str, dict[str, Any]], str] | None = None,
    ) -> None:
        self.enabled = bool(getattr(cfg, "SURVIVAL_GATES_ENABLED", True))
        self.max_daily_drawdown = _to_float(
            max_daily_drawdown,
            getattr(cfg, "MAX_DAILY_DRAWDOWN", -0.03),
        )
        self.max_consecutive_losses = max(
            1,
            _to_int(max_consecutive_losses, getattr(cfg, "MAX_CONSECUTIVE_LOSSES", 3)),
        )
        self.volatility_sizing_multiplier = max(
            0.0,
            min(
                1.0,
                _to_float(
                    volatility_sizing_multiplier,
                    getattr(cfg, "VOLATILITY_SIZING_MULTIPLIER", 0.5),
                ),
            ),
        )
        self.volatility_trigger_pct = max(
            0.0,
            _to_float(volatility_trigger_pct, getattr(cfg, "SURVIVAL_VOLATILITY_TRIGGER_PCT", 0.01)),
        )
        self.auto_flatten_on_breach = bool(
            getattr(cfg, "AUTO_FLATTEN_ON_BREACH", False)
            if auto_flatten_on_breach is None
            else auto_flatten_on_breach
        )
        self.halt_entries_on_breach = bool(
            getattr(cfg, "SURVIVAL_HALT_ENTRIES_ON_BREACH", True)
            if halt_entries_on_breach is None
            else halt_entries_on_breach
        )
        self.breach_cooldown_sec = max(
            1.0,
            _to_float(breach_cooldown_sec, getattr(cfg, "SURVIVAL_BREACH_COOLDOWN_SEC", 60.0)),
        )
        self._event_writer = event_writer or append_event
        self._incident_writer = incident_writer or create_incident
        self._last_breach_signature = ""
        self._last_breach_ts = 0.0

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._event_writer(str(event_type), dict(payload or {}))
        except Exception:
            pass

    def _raise_incident(self, reason_codes: list[str], context: dict[str, Any]) -> str | None:
        severity = SEV1 if "MAX_DAILY_DRAWDOWN_BREACH" in reason_codes else SEV2
        try:
            return str(self._incident_writer(severity, "SURVIVAL_GATE_BREACH", dict(context or {})))
        except Exception:
            return None

    @staticmethod
    def _extract_volatility_pct(market_data: dict[str, Any] | None) -> float:
        if not isinstance(market_data, dict):
            return 0.0
        direct = market_data.get("volatility_pct")
        if direct is not None:
            return max(0.0, _to_float(direct, 0.0))
        atr = _to_float(market_data.get("atr"), 0.0)
        ltp = _to_float(market_data.get("ltp"), 0.0)
        if atr > 0 and ltp > 0:
            return max(0.0, atr / ltp)
        return 0.0

    def evaluate(
        self,
        *,
        trade: Any = None,
        portfolio: dict[str, Any] | None = None,
        risk_state: Any = None,
        market_data: dict[str, Any] | None = None,
        now_ts: float | None = None,
    ) -> SurvivalGateDecision:
        ts_epoch = _to_float(now_ts, now_utc_epoch())
        symbol = str(getattr(trade, "symbol", "") or "").upper()
        trade_id = str(getattr(trade, "trade_id", "") or "")
        qty = _to_int(getattr(trade, "qty", 0), 0)

        if not self.enabled:
            return SurvivalGateDecision(
                allowed_entries=True,
                breach=False,
                reason_codes=[],
                size_multiplier=1.0,
                auto_flatten_requested=False,
                incident_id=None,
                context={"survival_gates_enabled": False},
            )

        portfolio_obj = dict(portfolio or {})
        drawdown = _to_float(
            portfolio_obj.get("daily_max_drawdown"),
            _to_float(getattr(risk_state, "daily_max_drawdown", 0.0), 0.0),
        )
        loss_streak = _to_int(
            portfolio_obj.get("loss_streak"),
            _to_int(getattr(risk_state, "loss_streak", 0), 0),
        )

        reason_codes: list[str] = []
        if drawdown <= self.max_daily_drawdown:
            reason_codes.append("MAX_DAILY_DRAWDOWN_BREACH")
        if loss_streak >= self.max_consecutive_losses:
            reason_codes.append("MAX_CONSECUTIVE_LOSSES_BREACH")

        breach = bool(reason_codes)
        size_multiplier = 1.0
        volatility_pct = self._extract_volatility_pct(market_data)
        if not breach and volatility_pct >= self.volatility_trigger_pct:
            size_multiplier = self.volatility_sizing_multiplier

        allowed_entries = not breach if self.halt_entries_on_breach else True
        auto_flatten_requested = bool(breach and self.auto_flatten_on_breach)

        context = {
            "symbol": symbol,
            "trade_id": trade_id,
            "qty": qty,
            "daily_max_drawdown": drawdown,
            "max_daily_drawdown_threshold": self.max_daily_drawdown,
            "loss_streak": loss_streak,
            "max_consecutive_losses_threshold": self.max_consecutive_losses,
            "volatility_pct": volatility_pct,
            "volatility_trigger_pct": self.volatility_trigger_pct,
            "size_multiplier": size_multiplier,
            "halt_entries_on_breach": self.halt_entries_on_breach,
            "auto_flatten_on_breach": self.auto_flatten_on_breach,
            "reason_codes": list(reason_codes),
            "ts_epoch": ts_epoch,
        }

        incident_id: str | None = None
        if breach:
            breach_signature = "|".join(sorted(reason_codes))
            cooldown_elapsed = (ts_epoch - self._last_breach_ts) >= self.breach_cooldown_sec
            should_emit = (breach_signature != self._last_breach_signature) or cooldown_elapsed
            if should_emit:
                self._emit("survival_gate_breach", context)
                incident_id = self._raise_incident(reason_codes, context)
                if auto_flatten_requested:
                    self._emit(
                        "flatten_requested",
                        {
                            "reason": "survival_gate_breach",
                            "desk_id": str(getattr(cfg, "DESK_ID", "DEFAULT")),
                            "trade_id": trade_id,
                            "symbol": symbol,
                            "qty": qty,
                            "scope": "ALL_OPEN_POSITIONS",
                            "reason_codes": list(reason_codes),
                            "ts_epoch": ts_epoch,
                        },
                    )
                self._last_breach_signature = breach_signature
                self._last_breach_ts = ts_epoch
            if incident_id:
                context["incident_id"] = incident_id

        return SurvivalGateDecision(
            allowed_entries=bool(allowed_entries),
            breach=bool(breach),
            reason_codes=list(reason_codes),
            size_multiplier=float(size_multiplier),
            auto_flatten_requested=bool(auto_flatten_requested),
            incident_id=incident_id,
            context=context,
        )
