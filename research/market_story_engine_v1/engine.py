from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .confirmations import option_confirmation, participation
from .contracts import Decision, DecisionRecord, LayerEvidence, MarketState
from .state import classify_state
from .structure import build_structure


@dataclass(frozen=True)
class EngineConfig:
    level_lookback: int = 12
    touch_lookback: int = 10
    compression_fast: int = 3
    compression_slow: int = 10
    level_tolerance_bps: float = 4.0
    acceptance_buffer_bps: float = 2.0
    min_room_bps: float = 12.0
    max_spread_pct: float = 0.035
    min_option_score: float = 0.60
    min_participation_score: float = 0.58
    min_structure_score: float = 0.58
    max_overextension_atr: float = 2.75


REQUIRED = {
    "underlying": {"timestamp", "open", "high", "low", "close"},
    "breadth": {
        "timestamp",
        "weighted_breadth",
        "equal_breadth",
        "top5_concentration",
        "sector_agreement",
    },
    "options": {
        "timestamp",
        "ce_bid",
        "ce_ask",
        "ce_last",
        "ce_volume",
        "pe_bid",
        "pe_ask",
        "pe_last",
        "pe_volume",
        "underlying_reference",
    },
}


def _validate(df: pd.DataFrame, name: str) -> pd.DataFrame:
    missing = REQUIRED[name].difference(df.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out.timestamp, utc=True)
    if out.timestamp.duplicated().any():
        raise ValueError(f"{name} contains duplicate timestamps")
    if not out.timestamp.is_monotonic_increasing:
        raise ValueError(f"{name} timestamps are not strictly increasing")
    return out.reset_index(drop=True)


class MarketStoryEngine:
    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()

    def run(
        self,
        underlying: pd.DataFrame,
        breadth: pd.DataFrame,
        options: pd.DataFrame,
    ) -> pd.DataFrame:
        u = _validate(underlying, "underlying")
        b = _validate(breadth, "breadth")
        o = _validate(options, "options")
        merged = pd.merge_asof(
            u,
            b,
            on="timestamp",
            direction="backward",
            tolerance=pd.Timedelta("75s"),
        )
        merged = pd.merge_asof(
            merged,
            o,
            on="timestamp",
            direction="backward",
            tolerance=pd.Timedelta("75s"),
        )
        records = [
            self._at(merged.iloc[: index + 1]).to_dict()
            for index in range(len(merged))
        ]
        return pd.DataFrame(records)

    def _at(self, history: pd.DataFrame) -> DecisionRecord:
        row = history.iloc[-1]
        warmup = max(
            self.config.level_lookback + 2,
            self.config.compression_slow + 2,
        )
        if len(history) < warmup:
            evidence = LayerEvidence(
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                MarketState.INSUFFICIENT.value,
                None,
                False,
            )
            return DecisionRecord(
                row.timestamp.isoformat(),
                Decision.WAIT.value,
                MarketState.INSUFFICIENT.value,
                0,
                None,
                None,
                None,
                ("WARMUP",),
                evidence,
            )
        structure = build_structure(history, self.config)
        state = classify_state(history, structure, self.config)
        part = participation(history)
        option = option_confirmation(history, self.config)
        return self._decide(row, structure, state, part, option)

    def _decide(
        self,
        row: pd.Series,
        structure: dict[str, object],
        state: MarketState,
        part: dict[str, object],
        option: dict[str, object],
    ) -> DecisionRecord:
        cfg = self.config
        reasons = list(option.get("reasons", ()))
        long_states = {
            MarketState.ACCEPTED_ABOVE,
            MarketState.RETEST_HOLD_UP,
            MarketState.EXPANSION_UP,
        }
        short_states = {
            MarketState.ACCEPTED_BELOW,
            MarketState.RETEST_HOLD_DOWN,
            MarketState.EXPANSION_DOWN,
        }
        setup_states = {
            MarketState.APPROACHING_RESISTANCE,
            MarketState.APPROACHING_SUPPORT,
            MarketState.BREAKOUT_ATTEMPT_UP,
            MarketState.BREAKOUT_ATTEMPT_DOWN,
            MarketState.REJECTION_UP,
            MarketState.REJECTION_DOWN,
            MarketState.BALANCED_RANGE,
        }
        complete = bool(part["complete"] and option["complete"])
        decision = Decision.REJECT
        confidence = 0.0
        level = None
        target = None

        if not complete:
            reasons.append("INDEPENDENT_CONFIRMATION_INCOMPLETE")
        elif state in long_states:
            if float(structure["room_up_bps"]) < cfg.min_room_bps:
                reasons.append("INSUFFICIENT_UPSIDE_ROOM")
            if bool(structure["overextended"]):
                reasons.append("OVEREXTENDED_UP_MOVE")
            if float(part["long"]) < cfg.min_participation_score:
                reasons.append("BREADTH_OR_PARTICIPATION_WEAK_LONG")
            if float(option["long"]) < cfg.min_option_score:
                reasons.append("CE_REPRICING_OR_LIQUIDITY_WEAK")
            if float(structure["long_score"]) < cfg.min_structure_score:
                reasons.append("STRUCTURE_QUALITY_WEAK_LONG")
            if not reasons:
                decision = Decision.BUY_CE
                confidence = min(
                    float(structure["long_score"]),
                    float(part["long"]),
                    float(option["long"]),
                )
                level = float(structure["resistance"])
                target = float(row.close) * (
                    1 + float(structure["room_up_bps"]) / 10000.0
                )
        elif state in short_states:
            if float(structure["room_down_bps"]) < cfg.min_room_bps:
                reasons.append("INSUFFICIENT_DOWNSIDE_ROOM")
            if bool(structure["overextended"]):
                reasons.append("OVEREXTENDED_DOWN_MOVE")
            if float(part["short"]) < cfg.min_participation_score:
                reasons.append("BREADTH_OR_PARTICIPATION_WEAK_SHORT")
            if float(option["short"]) < cfg.min_option_score:
                reasons.append("PE_REPRICING_OR_LIQUIDITY_WEAK")
            if float(structure["short_score"]) < cfg.min_structure_score:
                reasons.append("STRUCTURE_QUALITY_WEAK_SHORT")
            if not reasons:
                decision = Decision.BUY_PE
                confidence = min(
                    float(structure["short_score"]),
                    float(part["short"]),
                    float(option["short"]),
                )
                level = float(structure["support"])
                target = float(row.close) * (
                    1 - float(structure["room_down_bps"]) / 10000.0
                )
        elif state in setup_states:
            decision = Decision.WAIT
            confidence = max(
                float(structure["long_score"]),
                float(structure["short_score"]),
            )
            reasons.append("WAIT_FOR_ORDERED_ACCEPTANCE_AND_CONFIRMATION")
        else:
            reasons.append("STATE_NOT_BUYABLE")

        evidence = LayerEvidence(
            float(structure["long_score"]),
            float(structure["short_score"]),
            float(part["long"]),
            float(part["short"]),
            float(option["long"]),
            float(option["short"]),
            float(structure["room_up_bps"]),
            float(structure["room_down_bps"]),
            state.value,
            level,
            complete,
        )
        entry = (
            float(row.close)
            if decision in {Decision.BUY_CE, Decision.BUY_PE}
            else None
        )
        return DecisionRecord(
            row.timestamp.isoformat(),
            decision.value,
            state.value,
            round(confidence, 4),
            entry,
            level,
            target,
            tuple(sorted(set(reasons))),
            evidence,
        )
